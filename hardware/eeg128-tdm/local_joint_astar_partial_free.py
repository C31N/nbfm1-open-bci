#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded, read-only partial-free three-net F.Cu joint A*.

A path is empty until that agent is dynamically bound to an allowed native-
clear entry anchor. Bound agents may advance while other heads remain None.
Every new physical segment is checked against immutable native copper AND
the complete already-built traces of other agents, never only concurrent
head positions. No board writes, zone changes, via creation or release.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import heapq
import itertools
import math
import time
from typing import Any, Callable, Mapping, Sequence

from shapely.geometry import LineString, Point

from probe_block2_elastic_joint_corridor import DIRS, FCuCorridorGrid

Node = tuple[int, int]
PITCH_MM = .300
TOL = 1e-8
NET_NAMES: tuple[str, str, str] = (
    "CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
Position = tuple[float, float]
Positions = Mapping[str, Position | None]
Headings = Mapping[str, int]
Targets = Mapping[str, Position]
EDTLookup = Callable[[Position], float]


@dataclass(frozen=True)
class PartialFreeWeights:
    """Calibrated SOFT penalties; never replace hard geometry checks."""
    min_step_cost: float = .02
    bind_cost: float = .12
    early_bind_bonus: float = .18
    late_bind_penalty_factor: float = 1.20
    late_bind_reference_mm: float = 12.0
    edt_proximity_weight: float = .10
    edt_reference_mm: float = .85
    pitch_harmony_weight: float = .20
    progress_sync_weight: float = .12
    turn_weight: float = .015
    unbound_heuristic_damp: float = .85
    heuristic_epsilon: float = 2.0
    frontier_unbound_bias: float = 6.0

    def __post_init__(self) -> None:
        values = (
            self.min_step_cost, self.bind_cost, self.early_bind_bonus,
            self.late_bind_penalty_factor, self.late_bind_reference_mm,
            self.edt_proximity_weight, self.edt_reference_mm,
            self.pitch_harmony_weight, self.progress_sync_weight,
            self.turn_weight, self.unbound_heuristic_damp,
            self.heuristic_epsilon, self.frontier_unbound_bias)
        if any(not math.isfinite(v) or v < 0. for v in values):
            raise ValueError("Nonfinite or negative PartialFreeWeights")
        if (self.min_step_cost < .02 or self.late_bind_reference_mm <= 0.
                or self.edt_reference_mm <= 0.
                or not 0. < self.unbound_heuristic_damp <= 1.
                or not 1. <= self.heuristic_epsilon <= 3.):
            raise ValueError("PartialFreeCostModel calibration out of bounds")


class PartialFreeCostModel:
    """Model-only ranking: caller MUST run every native geometry gate first.

    The early bind discount is clamped by min_step_cost, ensuring delta-g
    stays positive even when two of three heads have not moved. EDT is a
    soft obstacle-proximity score from already inflated native masks.
    """

    def __init__(self, weights: PartialFreeWeights | None = None) -> None:
        self.w = weights if weights is not None else PartialFreeWeights()

    @staticmethod
    def _dist(a: Position, b: Position) -> float:
        return math.dist(a, b)

    def heuristic(
        self,
        positions: Positions,
        targets: Targets,
        anchors: Mapping[str, Sequence[Position]],
    ) -> float:
        total = 0.
        for net, target in targets.items():
            pos = positions[net]
            if pos is not None:
                total += self._dist(pos, target)
            else:
                options = anchors[net]
                if not options:
                    raise ValueError("No source for unbound net")
                total += (self.w.unbound_heuristic_damp *
                          min(self._dist(anchor, target)
                              for anchor in options))
        return total

    def transition_components(
        self,
        prev_positions: Positions,
        next_positions: Positions,
        prev_headings: Headings,
        next_headings: Headings,
        targets: Targets,
        edt_lookup: EDTLookup,
    ) -> dict[str, float]:
        """Explain every finite soft cost term, with a positive final step."""
        displacement = 0.
        binding_count = 0
        for net, next_pos in next_positions.items():
            prev_pos = prev_positions[net]
            if prev_pos is not None and next_pos is not None:
                displacement += self._dist(prev_pos, next_pos)
            elif prev_pos is None and next_pos is not None:
                binding_count += 1
        newly_bound_third = (
            binding_count == 1
            and sum(p is not None for p in prev_positions.values()) == 2)
        third_binding_adjustment = 0.
        if newly_bound_third:
            # Reference progress is measured BEFORE binding net three.
            # Early: far from target => discount. Late: close => penalty.
            remaining = [
                self._dist(prev_positions[net], target)
                for net, target in targets.items()
                if prev_positions[net] is not None]
            mean_remaining = sum(remaining) / len(remaining)
            relative = min(1., max(0.,
                                    mean_remaining / self.w.late_bind_reference_mm))
            third_binding_adjustment = (
                -self.w.early_bind_bonus * relative
                + self.w.late_bind_penalty_factor * (1. - relative))
        edt_penalty = 0.
        positions = [p for p in next_positions.values() if p is not None]
        for p in positions:
            clearance = edt_lookup(p)
            if not math.isfinite(clearance):
                raise ValueError("Invalid native EDT sample")
            edt_penalty += self.w.edt_proximity_weight * max(
                0., self.w.edt_reference_mm - max(0., clearance)
            ) / self.w.edt_reference_mm

        # Penalize a WORSENING of the pitch deviation, not a repeatedly
        # charged unavoidable offset between already separated legal nets.
        # This preserves the exact preference for a 0.300-mm bundle
        # without exhausting the search on a constant distant pairing.
        pitch_penalty = 0.
        names = list(next_positions)
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                n1, n2 = names[a], names[b]
                q1, q2 = next_positions[n1], next_positions[n2]
                if q1 is None or q2 is None:
                    continue
                next_dev = abs(self._dist(q1, q2) - PITCH_MM)
                p1, p2 = prev_positions[n1], prev_positions[n2]
                prev_dev = (
                    abs(self._dist(p1, p2) - PITCH_MM)
                    if p1 is not None and p2 is not None else 0.)
                pitch_penalty += self.w.pitch_harmony_weight * max(
                    0., next_dev - prev_dev)
        # Synchronize net progress by discouraging NEW divergence.
        # Keeping a fixed feasible offset is never punished on every hop.
        remaining_next = [
            self._dist(p, targets[net])
            for net, p in next_positions.items() if p is not None]
        remaining_prev = [
            self._dist(p, targets[net])
            for net, p in prev_positions.items() if p is not None]
        next_range = (max(remaining_next) - min(remaining_next)
                      if len(remaining_next) >= 2 else 0.)
        prev_range = (max(remaining_prev) - min(remaining_prev)
                      if len(remaining_prev) >= 2 else 0.)
        progress_penalty = (self.w.progress_sync_weight *
                            max(0., next_range - prev_range))
        turning = self.w.turn_weight * sum(
            int(prev_headings[net] != next_headings[net])
            for net, p in next_positions.items()
            if p is not None and prev_positions[net] is not None)
        raw = (displacement + binding_count * self.w.bind_cost
               + third_binding_adjustment + edt_penalty +
               pitch_penalty + progress_penalty + turning)
        step = max(self.w.min_step_cost, raw)
        if not math.isfinite(step):
            raise ValueError("Invalid cost function result")
        return {
            "step_cost": step,
            "displacement_mm": displacement,
            "binding_cost": binding_count * self.w.bind_cost,
            "third_binding_adjustment": third_binding_adjustment,
            "edt_proximity_penalty": edt_penalty,
            "pitch_harmony_penalty": pitch_penalty,
            "progress_sync_penalty": progress_penalty,
            "turn_penalty": turning,
        }

    def transition_cost(
        self,
        prev_positions: Positions,
        next_positions: Positions,
        prev_headings: Headings,
        next_headings: Headings,
        targets: Targets,
        edt_lookup: EDTLookup,
    ) -> float:
        return self.transition_components(
            prev_positions, next_positions,
            prev_headings, next_headings, targets, edt_lookup
        )["step_cost"]


@dataclass(frozen=True)
class PartialFreeState:
    # Empty route means genuinely unbound; no virtual copper/zero anchor.
    paths: tuple[tuple[Node, ...], tuple[Node, ...], tuple[Node, ...]]

    @property
    def heads(self) -> tuple[Node | None, Node | None, Node | None]:
        return tuple(path[-1] if path else None for path in self.paths)


def partial_free_joint_astar(
    grid: FCuCorridorGrid,
    source_options: Sequence[Sequence[Node]],
    target_options: Sequence[Sequence[Node]],
    *,
    max_expansions: int = 1600,
    max_seconds: float = 4.0,
    hard_pitch_mm: float = PITCH_MM,
    anchor_pitch_mm: float = .440,
    max_route_nodes: int = 64,
) -> dict[str, Any]:
    """Interleave real None->anchor bindings and active per-net F.Cu moves.

    Search states include physical route history; merging states with the
    same heads but incompatible copper history would be unsound.
    A successful return is still a NO-RELEASE scratch-only candidate.
    """
    if (len(source_options) != 3 or len(target_options) != 3
            or any(not s for s in source_options)
            or any(not t for t in target_options)
            or not 1 <= max_expansions <= 4800
            or not .01 <= max_seconds <= 12.
            or max_route_nodes < 2 or max_route_nodes > 128
            or not math.isfinite(hard_pitch_mm)
            or hard_pitch_mm < PITCH_MM
            or not math.isfinite(anchor_pitch_mm)
            or anchor_pitch_mm < .440):
        raise ValueError("Invalid bounded partial-free native F.Cu request")

    source_sets = tuple(tuple(dict.fromkeys(s)) for s in source_options)
    target_sets = tuple(tuple(dict.fromkeys(s)) for s in target_options)
    # All explicitly bound source/target coordinates must be native-clear.
    # Invalid options are omitted, not silently moved to other copper.
    source_sets = tuple(tuple(p for p in row
                              if grid.is_point_drc_clear(i, p)
                              and not Point(grid.physical(p)).intersects(
                                  grid.shapes[i]))
                        for i, row in enumerate(source_sets))
    target_sets = tuple(tuple(p for p in row
                              if grid.is_point_drc_clear(i, p)
                              and not Point(grid.physical(p)).intersects(
                                  grid.shapes[i]))
                        for i, row in enumerate(target_sets))
    reject: Counter[str] = Counter()
    created = time.monotonic()
    diagnostic: dict[str, Any] = {
        "status": "PARTIAL_FREE_NODE_BUDGET_EXHAUSTED",
        "expansions": 0,
        "initial_heads": [None, None, None],
        "initial_unbound_nets": 3,
        "search_states_by_bound_count": [0, 0, 0, 0],
        "moves_while_other_nets_unbound": 0,
        "binding_actions_examined": 0,
        "binding_actions_valid": 0,
        "native_mask_prefilter_rejections": 0,
        "native_segment_rejections": 0,
        "density_penalty_applied": True,
        "weighted_heuristic_epsilon": 2.0,
        "cost_model": "PartialFreeCostModel-v1",
        "frontier_unbound_bias": 6.0,
        "third_binding_transition_attempts": 0,
        "third_binding_native_valid": 0,
        "third_binding_admitted": 0,
        "third_binding_expanded_roots": 0,
        "third_binding_survived_after_one_step": 0,
        "third_binding_survival_rate": 0.,
        "average_progress_sync_penalty": 0.,
        "average_progress_sync_penalty_after_third_binding": 0.,
        "rejections_by_bound_count": {},
        "completed_routes": 0,
        "hard_centreline_pitch_mm": hard_pitch_mm,
        "minimum_anchor_pitch_mm": anchor_pitch_mm,
        "native_DRC_still_required": True,
        "geometry_unsatisfiable_proven": False,
        "new_vias_added": 0,
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
    }
    if any(not row for row in (*source_sets, *target_sets)):
        diagnostic["status"] = "PARTIAL_FREE_NATIVE_ANCHORS_MASKED"
        diagnostic["reject_reasons"] = {"native_fixed_copper_or_mask": 1}
        return diagnostic

    @lru_cache(maxsize=2048)
    def density(agent: int, p: Node) -> float:
        """Soft search cost only; high-density but clear cells stay legal."""
        x, y = p
        if not grid.is_point_drc_clear(agent, p):
            return 1.
        mask = grid.masks[agent]
        region = mask[max(0, y - 2):min(grid.height, y + 3),
                      max(0, x - 2):min(grid.width, x + 3)]
        return float(region.sum()) / max(1, region.size)

    @lru_cache(maxsize=8000)
    def dist(a: Node, b: Node) -> float:
        return math.dist(grid.physical(a), grid.physical(b))

    cost_model = PartialFreeCostModel()
    # EDT only biases search. Native inflated mask and exact Shapely
    # continuous-segment collision checks below remain mandatory.
    grid.build_distance_field()
    if grid.edt_mm is None:
        raise RuntimeError("Native EDT missing")
    edt_fields = grid.edt_mm
    physical_targets = {
        NET_NAMES[i]: grid.physical(target_sets[i][0]) for i in range(3)}
    physical_anchors = {
        NET_NAMES[i]: tuple(grid.physical(p) for p in source_sets[i])
        for i in range(3)}

    @lru_cache(maxsize=8000)
    def state_positions(state: PartialFreeState) -> dict[str, Position | None]:
        return {NET_NAMES[i]: (grid.physical(path[-1]) if path else None)
                for i, path in enumerate(state.paths)}

    @lru_cache(maxsize=8000)
    def heuristic(state: PartialFreeState) -> float:
        # The calibrated None-net distance is intentionally damped in
        # PartialFreeCostModel. A separate FRONTIER-ONLY preference avoids
        # spending the entire node budget extending the first bound net.
        # It changes queue order, never transition cost or clearance.
        return (cost_model.heuristic(
            state_positions(state), physical_targets, physical_anchors)
            + cost_model.w.frontier_unbound_bias *
            sum(not path for path in state.paths))

    def route_heading(path: tuple[Node, ...]) -> int:
        if len(path) < 2:
            return 0
        delta = (path[-1][0] - path[-2][0],
                 path[-1][1] - path[-2][1])
        return DIRS.index(delta) if delta in DIRS else 0

    def score_transition(
        prev: PartialFreeState, nxt: PartialFreeState,
    ) -> dict[str, float]:
        previous = state_positions(prev)
        following = state_positions(nxt)
        prev_headings = {NET_NAMES[i]: route_heading(path)
                         for i, path in enumerate(prev.paths)}
        next_headings = {NET_NAMES[i]: route_heading(path)
                         for i, path in enumerate(nxt.paths)}

        def edt_sample(p: Position) -> float:
            # Sample the physically matching net's already-inflated EDT,
            # not a relaxed/averaged substitute for exact native clearance.
            for i, net in enumerate(NET_NAMES):
                if following[net] == p:
                    x = int(round((p[0] - grid.xs[0]) / grid.res))
                    y = int(round((p[1] - grid.ys[0]) / grid.res))
                    return float(edt_fields[i][y, x])
            raise ValueError("EDT sample for missing bound head")
        return cost_model.transition_components(
            previous, following, prev_headings, next_headings,
            physical_targets, edt_sample)

    rejection_by_binding: list[Counter[str]] = [Counter() for _ in range(4)]
    active_bind_count = 0
    sync_sum = 0.
    sync_count = 0
    post_third_sync_sum = 0.
    post_third_sync_count = 0

    def reject_reason(reason: str) -> None:
        reject[reason] += 1
        rejection_by_binding[active_bind_count][reason] += 1

    def existing_distance(
        agent: int, segment: Point | LineString,
        paths: tuple[tuple[Node, ...], ...],
    ) -> bool:
        for other, route in enumerate(paths):
            if other == agent or not route:
                continue
            coords = tuple(grid.physical(p) for p in route)
            wire = (Point(coords[0]) if len(coords) == 1
                    else LineString(coords))
            if segment.distance(wire) < hard_pitch_mm - TOL:
                reject_reason("continuous_segment_pitch")
                return False
        return True

    def entry_clear(
        agent: int, p: Node, state: PartialFreeState,
    ) -> bool:
        if not grid.is_point_drc_clear(agent, p):
            reject_reason("native_fixed_copper_or_mask")
            return False
        pt = Point(grid.physical(p))
        if pt.intersects(grid.shapes[agent]):
            reject_reason("native_fixed_copper_or_mask")
            return False
        for i, route in enumerate(state.paths):
            if route and dist(route[0], p) < anchor_pitch_mm - TOL:
                reject_reason("source_anchor_pitch")
                return False
        return existing_distance(agent, pt, state.paths)

    def finished(state: PartialFreeState) -> bool:
        if any(not route or len(route) < 2 or
               route[-1] not in target_sets[i]
               for i, route in enumerate(state.paths)):
            return False
        goals = [state.paths[i][-1] for i in range(3)]
        if any(dist(goals[i], goals[j]) < anchor_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reject_reason("target_anchor_pitch")
            return False
        # Redundant exact whole-history validation before a scratch return.
        wires = []
        for i, route in enumerate(state.paths):
            line = LineString([grid.physical(p) for p in route])
            if not line.is_valid or line.intersects(grid.shapes[i]):
                reject_reason("native_fixed_copper_or_mask")
                return False
            wires.append(line)
        if any(wires[i].distance(wires[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reject_reason("continuous_segment_pitch")
            return False
        return True

    start = PartialFreeState(((), (), ()))
    order = itertools.count()
    # Bounded weighted A* favours coordinated progress over combinatorial
    # prefixes. This influences search order ONLY, never geometric gates.
    epsilon = cost_model.w.heuristic_epsilon
    heap = [(epsilon * heuristic(start), 0., next(order), start)]
    best: dict[PartialFreeState, float] = {start: 0.}
    expansions = 0
    root_by_state: dict[PartialFreeState, PartialFreeState] = {}
    admitted_roots: set[PartialFreeState] = set()
    expanded_roots: set[PartialFreeState] = set()
    survived_roots: set[PartialFreeState] = set()

    def push(
        state: PartialFreeState, g: float,
        parent: PartialFreeState, components: dict[str, float],
    ) -> bool:
        nonlocal sync_sum, sync_count, post_third_sync_sum, post_third_sync_count
        if g + 1e-9 >= best.get(state, math.inf):
            return False
        best[state] = g
        count = sum(bool(path) for path in state.paths)
        prev_count = sum(bool(path) for path in parent.paths)
        if count == 3:
            if prev_count == 2:
                root_by_state[state] = state
                admitted_roots.add(state)
                diagnostic["third_binding_admitted"] += 1
            elif parent in root_by_state:
                root_by_state[state] = root_by_state[parent]
        sync_sum += components["progress_sync_penalty"]
        sync_count += 1
        if count == 3:
            post_third_sync_sum += components["progress_sync_penalty"]
            post_third_sync_count += 1
        heapq.heappush(heap, (g + epsilon * heuristic(state),
                              g, next(order), state))
        return True

    def update_telemetry() -> None:
        diagnostic["third_binding_expanded_roots"] = len(expanded_roots)
        diagnostic["third_binding_survived_after_one_step"] = (
            len(survived_roots))
        # Survived = a third-bind root with a descendant (at least one
        # subsequent exact-validated route step) actually popped from A*.
        # Denominator = unique native-valid third-bind states enqueued.
        diagnostic["third_binding_survival_rate"] = round(
            len(survived_roots) / max(1, len(admitted_roots)), 6)
        diagnostic["average_progress_sync_penalty"] = round(
            sync_sum / max(1, sync_count), 6)
        diagnostic["average_progress_sync_penalty_after_third_binding"] = round(
            post_third_sync_sum / max(1, post_third_sync_count), 6)
        diagnostic["rejections_by_bound_count"] = {
            str(i): dict(sorted(counter.items()))
            for i, counter in enumerate(rejection_by_binding)}

    while heap and expansions < max_expansions:
        if time.monotonic() - created >= max_seconds:
            diagnostic["status"] = "PARTIAL_FREE_WALL_BUDGET_EXHAUSTED"
            break
        _, g, _, state = heapq.heappop(heap)
        if g > best.get(state, math.inf) + 1e-9:
            continue
        expansions += 1
        bound = sum(bool(path) for path in state.paths)
        active_bind_count = bound
        diagnostic["search_states_by_bound_count"][bound] += 1
        if bound == 3 and state in root_by_state:
            root = root_by_state[state]
            expanded_roots.add(root)
            if state != root:
                survived_roots.add(root)
        if finished(state):
            update_telemetry()
            diagnostic.update({
                "status": "PARTIAL_FREE_THREE_LOCAL_ROUTES_PROPOSED",
                "expansions": expansions,
                "completed_routes": 3,
                "routes": state.paths,
                "selected_source_anchors": [path[0] for path in state.paths],
                "selected_target_anchors": [path[-1] for path in state.paths],
                "reject_reasons": dict(reject),
                "wall_seconds": round(time.monotonic() - created, 3),
            })
            return diagnostic
        for agent in range(3):
            route = state.paths[agent]
            if not route:
                # Actual partial-free activation, not a dummy fixed triplet.
                for p in source_sets[agent]:
                    diagnostic["binding_actions_examined"] += 1
                    if bound == 2:
                        diagnostic["third_binding_transition_attempts"] += 1
                    if not entry_clear(agent, p, state):
                        continue
                    diagnostic["binding_actions_valid"] += 1
                    if bound == 2:
                        diagnostic["third_binding_native_valid"] += 1
                    routes = list(state.paths)
                    routes[agent] = (p,)
                    candidate = PartialFreeState(tuple(routes))
                    # Geometry is checked first; only then compute the
                    # calibrated SOFT transition score.
                    terms = score_transition(state, candidate)
                    push(candidate,
                         g + terms["step_cost"] + .05 * density(agent, p),
                         state, terms)
                continue
            if len(route) >= max_route_nodes or (
                    route[-1] in target_sets[agent]):
                continue
            if bound < 3:
                diagnostic["moves_while_other_nets_unbound"] += 1
            a = route[-1]
            for dx, dy in DIRS:
                b = (a[0] + dx, a[1] + dy)
                # Cheap, immutable inflated raster gate BEFORE expensive
                # exact geometry or path-history Shapely checks.
                if not grid.is_point_drc_clear(agent, b):
                    reject_reason("native_fixed_copper_or_mask")
                    diagnostic["native_mask_prefilter_rejections"] += 1
                    continue
                if b in route:
                    continue
                if not grid.is_segment_drc_clear(agent, a, b):
                    reject_reason("native_fixed_copper_or_mask")
                    diagnostic["native_segment_rejections"] += 1
                    continue
                step = LineString((grid.physical(a), grid.physical(b)))
                if not existing_distance(agent, step, state.paths):
                    continue
                routes = list(state.paths)
                routes[agent] = (*route, b)
                # Clearance density only biases search; it never waives
                # or hard-blocks a physically native-clear passage.
                candidate = PartialFreeState(tuple(routes))
                terms = score_transition(state, candidate)
                cost = terms["step_cost"] + .05 * density(agent, b)
                push(candidate, g + cost, state, terms)

    if diagnostic["status"] != "PARTIAL_FREE_WALL_BUDGET_EXHAUSTED":
        diagnostic["status"] = (
            "PARTIAL_FREE_NODE_BUDGET_EXHAUSTED"
            if heap else "PARTIAL_FREE_FRONTIER_EXHAUSTED")
    update_telemetry()
    diagnostic["expansions"] = expansions
    diagnostic["reject_reasons"] = dict(reject)
    diagnostic["open_states_remaining"] = len(heap)
    diagnostic["wall_seconds"] = round(time.monotonic() - created, 3)
    return diagnostic

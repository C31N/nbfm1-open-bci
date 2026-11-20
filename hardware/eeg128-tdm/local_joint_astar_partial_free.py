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

from collections import Counter, deque
from dataclasses import dataclass
from functools import lru_cache
import heapq
import itertools
import math
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

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
    target_progress_credit_weight: float = .12
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
            self.target_progress_credit_weight,
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
        # Soft positive progress credit; does not change any hard gate.
        progress_mm = sum(
            max(0., self._dist(prev_positions[net], targets[net])
                - self._dist(p, targets[net]))
            for net, p in next_positions.items()
            if p is not None and prev_positions[net] is not None)
        progress_credit = self.w.target_progress_credit_weight * progress_mm
        raw = (displacement + binding_count * self.w.bind_cost
               + third_binding_adjustment + edt_penalty +
               pitch_penalty + progress_penalty + turning - progress_credit)
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
            "target_progress_credit": progress_credit,
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


PointMM = Position


@dataclass(frozen=True)
class ThreeNetEvasionConfig:
    """Strict bounded geometry-first evasion; never weaken PCB pitch."""
    step_mm: float = .250
    min_pitch_mm: float = PITCH_MM
    max_evasion_candidates: int = 32

    def __post_init__(self) -> None:
        if (not math.isfinite(self.step_mm) or self.step_mm <= 0.
                or not math.isfinite(self.min_pitch_mm)
                or self.min_pitch_mm < PITCH_MM
                or not 1 <= self.max_evasion_candidates <= 64):
            raise ValueError("Invalid strict ThreeNetEvasionConfig")


class ThreeNetEvasionGenerator:
    """Three-bound-net staged motion preflight; never bypass native checks.

    SYNC_GOAL -> SINGLE_EVADE -> PAIR_EVADE -> COUPLED_TURN
    -> STAGGERED_EVADE -> LATERAL_EVADE -> ASYMMETRIC_EVADE.
    HOLD members add no new copper; all moving members keep native gates.
    Native callbacks enforce masks, immutable copper and entire trace history;
    the caller MUST enforce new-to-new segments after snapping to its grid.
    """

    def __init__(
        self, *,
        net_order: Sequence[str],
        is_point_clear: Callable[[str, PointMM, float], bool | str],
        is_segment_clear: Callable[[str, PointMM, PointMM, float], bool | str],
        record_rejection: Callable[[str, int], None],
        config: ThreeNetEvasionConfig | None = None,
        is_joint_clear: Callable[[Mapping[str, PointMM]], bool | str] | None = None,
    ) -> None:
        if len(net_order) != 3 or len(set(net_order)) != 3:
            raise ValueError("Exactly three distinct nets required")
        self.net_order = tuple(net_order)
        self.is_point_clear = is_point_clear
        self.is_segment_clear = is_segment_clear
        self.is_joint_clear = is_joint_clear
        self.record_rejection = record_rejection
        self.config = config or ThreeNetEvasionConfig()

    @staticmethod
    def _goal_heading(position: PointMM, target: PointMM) -> int:
        dx, dy = target[0] - position[0], target[1] - position[1]
        if abs(dx) + abs(dy) < TOL:
            return 0
        return max(range(len(DIRS)), key=lambda h: (
            (dx * DIRS[h][0] + dy * DIRS[h][1]) /
            math.hypot(*DIRS[h])))

    @staticmethod
    def _step_point(position: PointMM, heading: int, step_mm: float) -> PointMM:
        dx, dy = DIRS[heading % len(DIRS)]
        magnitude = math.hypot(dx, dy)
        return (position[0] + step_mm * dx / magnitude,
                position[1] + step_mm * dy / magnitude)

    def generate_evasion_steps(
        self,
        positions: Mapping[str, PointMM | None],
        headings: Mapping[str, int | None],
        targets: Targets, *, explore_lateral: bool = True,
    ) -> Iterator[tuple[dict[str, PointMM], dict[str, int], str]]:
        if any(positions.get(n) is None or headings.get(n) is None
               for n in self.net_order):
            return
        original = {n: positions[n] for n in self.net_order}
        pitch = self.config.min_pitch_mm
        for a, b in itertools.combinations(self.net_order, 2):
            if math.dist(original[a], original[b]) < pitch - TOL:
                self.record_rejection("pair_pitch", 3)
                return
        # A goal member may HOLD while the other two advance.
        at_goal = {n for n in self.net_order
                   if math.dist(original[n], targets[n]) < TOL}
        if len(at_goal) == len(self.net_order):
            return
        goal = {n: self._goal_heading(original[n], targets[n])
                for n in self.net_order}
        stages: list[tuple[str, list[tuple[dict[str, int], str]]]] = [
            ("SYNC_GOAL", [(goal, "SYNC_GOAL")]),
            ("SINGLE_EVADE", []),
            ("PAIR_EVADE", []),
            ("COUPLED_TURN", []),
            ("STAGGERED_EVADE", []),
            ("LATERAL_EVADE", []),
            ("ASYMMETRIC_EVADE", []),
        ]
        for n in self.net_order:
            for shift in (-1, 1, -2, 2):
                h = dict(goal)
                h[n] = (h[n] + shift) % len(DIRS)
                stages[1][1].append((h, f"SINGLE_EVADE_{n}_{shift:+d}"))
        for a, b in itertools.combinations(self.net_order, 2):
            for da, db in ((-1, -1), (1, 1), (-1, 1), (1, -1),
                           (-2, -2), (2, 2)):
                h = dict(goal)
                h[a] = (h[a] + da) % len(DIRS)
                h[b] = (h[b] + db) % len(DIRS)
                stages[2][1].append((
                    h, f"PAIR_EVADE_{a}_{b}_{da:+d}_{db:+d}"))
        for shift in (-1, 1, -2, 2):
            h = {n: (goal[n] + shift) % len(DIRS)
                 for n in self.net_order}
            stages[3][1].append((h, f"COUPLED_TURN_{shift:+d}"))
        # A lagging track remains on its existing copper while two tracks
        # advance; 0/1/2 heading offsets form a bounded corner fanout.
        for held in self.net_order:
            moving = tuple(n for n in self.net_order if n != held)
            for stage_index, shifts in (
                    (4, ((0, 0), (-1, 0), (1, 0),
                         (0, -1), (0, 1), (-1, 1), (1, -1))),
                    (5, ((-2, 0), (2, 0), (0, -2), (0, 2),
                         (-2, -2), (2, 2)))):
                for da, db in shifts:
                    h = dict(goal)
                    h[held] = -1
                    h[moving[0]] = (goal[moving[0]] + da) % len(DIRS)
                    h[moving[1]] = (goal[moving[1]] + db) % len(DIRS)
                    name = ("STAGGERED_EVADE" if stage_index == 4
                            else "LATERAL_EVADE")
                    stages[stage_index][1].append((
                        h, f"{name}_{held}_{da:+d}_{db:+d}"))
        # Opposing turns make the 3-net fanout asymmetric, preserving
        # the physical order only if all later native gates validate it.
        for da, db, dc in ((-1, 0, 1), (1, 0, -1),
                           (-2, 0, 2), (2, 0, -2),
                           (-1, 1, 0), (1, -1, 0),
                           (0, -1, 1), (0, 1, -1)):
            offsets = (da, db, dc)
            h = {n: (goal[n] + offsets[i]) % len(DIRS)
                 for i, n in enumerate(self.net_order)}
            stages[6][1].append((
                h, f"ASYMMETRIC_EVADE_{da:+d}_{db:+d}_{dc:+d}"))

        accepted = 0
        visited: set[tuple[PointMM, ...]] = set()
        for _stage, proposals in stages:
            if (_stage in ("LATERAL_EVADE", "ASYMMETRIC_EVADE")
                    and not explore_lateral):
                continue
            valid_in_stage = 0
            for new_headings, tag in proposals:
                if accepted >= self.config.max_evasion_candidates:
                    return
                if any(new_headings[n] >= 0 for n in at_goal):
                    continue
                next_pos = {
                    n: (original[n] if new_headings[n] < 0 else
                        self._step_point(
                            original[n], new_headings[n], self.config.step_mm))
                    for n in self.net_order}
                if all(new_headings[n] < 0 for n in self.net_order):
                    continue
                key = tuple(next_pos[n] for n in self.net_order)
                if key in visited:
                    continue
                visited.add(key)
                if any(math.dist(next_pos[a], next_pos[b]) < pitch - TOL
                       for a, b in itertools.combinations(self.net_order, 2)):
                    self.record_rejection("pair_pitch", 3)
                    continue
                # These are only pre-snap candidate hints. The caller
                # repeats the hard continuous segment-to-segment pitch
                # gate with actual native-grid coordinates before A* push.
                denied = False
                for n in self.net_order:
                    if new_headings[n] < 0:
                        # No new segment on a held route; its history was
                        # previously validated and remains immutable.
                        continue
                    point_result = self.is_point_clear(n, next_pos[n], pitch)
                    if point_result is not True:
                        self.record_rejection(
                            point_result if isinstance(point_result, str)
                            else "evasion_point_blocked", 3)
                        denied = True
                        break
                    segment_result = self.is_segment_clear(
                        n, original[n], next_pos[n], pitch)
                    if segment_result is not True:
                        self.record_rejection(
                            segment_result if isinstance(segment_result, str)
                            else "evasion_segment_blocked", 3)
                        denied = True
                        break
                if denied:
                    continue
                if self.is_joint_clear is not None:
                    joint_result = self.is_joint_clear(next_pos)
                    if joint_result is not True:
                        self.record_rejection(
                            joint_result if isinstance(joint_result, str)
                            else "evasion_joint_blocked", 3)
                        continue
                accepted += 1
                valid_in_stage += 1
                yield next_pos, new_headings, tag
            # Early cheap success may stop; a COUPLED_TURN alone must not
            # hide staggers and asymmetric continuations at the bottleneck.
            if valid_in_stage and (
                    _stage in ("SYNC_GOAL", "SINGLE_EVADE", "PAIR_EVADE")
                    or (_stage == "STAGGERED_EVADE"
                        and not explore_lateral)):
                return


def _nearest_target_node(
    head: Node | None, targets: Sequence[Node],
    distance: Callable[[Node, Node], float],
) -> Node:
    """Deterministic nearest physically eligible anchor, stable on ties."""
    if not targets:
        raise ValueError("No eligible native target anchor")
    return targets[0] if head is None else min(
        targets, key=lambda candidate: distance(head, candidate))


def _evasion_fair_due(
    queued: bool, expansions: int, last_fair_expansion: int,
    interval: int = 8,
) -> bool:
    """Admit first valid evasion immediately, then at most once per interval.

    This is a scheduling preference only. It never changes path g costs,
    native geometry, branch gates, or the maximum expansion count.
    """
    if interval < 1:
        raise ValueError("Invalid evasion fairness interval")
    return queued and expansions - last_fair_expansion >= interval


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
        "third_binding_roots_with_goal_progress": 0,
        "third_binding_goal_progress_rate": 0.,
        "third_binding_best_goal_progress_mm": 0.,
        "third_binding_max_targets_reached": 0,
        "average_progress_sync_penalty": 0.,
        "average_progress_sync_penalty_after_third_binding": 0.,
        "rejections_by_bound_count": {},
        "three_net_evasion_fair_queue_pop_count": 0,
        "three_net_evasion_fair_queue_peak": 0,
        "three_net_evasion_fair_queue_stale_pops": 0,
        "three_net_evasion_first_admitted_expansion": None,
        "three_net_evasion_first_expanded_expansion": None,
        "three_net_evasion_first_wait_expansions": None,
        "three_net_evasion_average_expansion_ms": 0.,
        "three_net_evasion_max_expansion_ms": 0.,
        "three_net_evasion_first_expanded_probe": None,
        "three_net_evasion_deep_probe_states": 0,
        "three_net_choke_states": [],
        "three_net_choke_probe_version": "read_only_fcu_choke_v1",
        "three_net_evasion_stages_generated": {s: 0 for s in (
            "SYNC_GOAL", "SINGLE_EVADE", "PAIR_EVADE", "COUPLED_TURN",
            "STAGGERED_EVADE", "LATERAL_EVADE", "ASYMMETRIC_EVADE")},
        "three_net_evasion_stages_admitted": {s: 0 for s in (
            "SYNC_GOAL", "SINGLE_EVADE", "PAIR_EVADE", "COUPLED_TURN",
            "STAGGERED_EVADE", "LATERAL_EVADE", "ASYMMETRIC_EVADE")},
        "three_net_evasion_stages_expanded": {s: 0 for s in (
            "SYNC_GOAL", "SINGLE_EVADE", "PAIR_EVADE", "COUPLED_TURN",
            "STAGGERED_EVADE", "LATERAL_EVADE", "ASYMMETRIC_EVADE")},
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
    @lru_cache(maxsize=8000)
    def nearest_targets(state: PartialFreeState) -> dict[str, Position]:
        return {
            NET_NAMES[i]: grid.physical(_nearest_target_node(
                state.paths[i][-1] if state.paths[i] else None,
                target_sets[i], dist))
            for i in range(3)}
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
            state_positions(state), nearest_targets(state), physical_anchors)
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
            nearest_targets(prev), edt_sample)

    rejection_by_binding: list[Counter[str]] = [Counter() for _ in range(4)]
    active_bind_count = 0
    sync_sum = 0.
    sync_count = 0
    post_third_sync_sum = 0.
    post_third_sync_count = 0

    def reject_reason(reason: str) -> None:
        reject[reason] += 1
        rejection_by_binding[active_bind_count][reason] += 1

    @lru_cache(maxsize=8192)
    def immutable_route_geometry(route: tuple[Node, ...]) -> Point | LineString:
        # Physical route histories are immutable tuples. Reusing Shapely
        # geometries changes performance only, never native clearance.
        coords = tuple(grid.physical(p) for p in route)
        return Point(coords[0]) if len(coords) == 1 else LineString(coords)

    def existing_distance(
        agent: int, segment: Point | LineString,
        paths: tuple[tuple[Node, ...], ...], *, record: bool = True,
    ) -> bool:
        for other, route in enumerate(paths):
            if other == agent or not route:
                continue
            wire = immutable_route_geometry(route)
            if segment.distance(wire) < hard_pitch_mm - TOL:
                if record:
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
            line = immutable_route_geometry(route)
            if not line.is_valid or line.intersects(grid.shapes[i]):
                reject_reason("native_fixed_copper_or_mask")
                return False
            wires.append(line)
        if any(wires[i].distance(wires[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reject_reason("continuous_segment_pitch")
            return False
        return True

    def evasion_node(p: PointMM) -> Node:
        return (int(round((p[0] - float(grid.xs[0])) / grid.res)),
                int(round((p[1] - float(grid.ys[0])) / grid.res)))

    def evasion_point_clear(
        net: str, p: PointMM, _min_clear: float,
    ) -> bool | str:
        i = NET_NAMES.index(net)
        node = evasion_node(p)
        current = state.paths[i][-1]
        if (node in state.paths[i]
                or (node[0] - current[0], node[1] - current[1])
                not in DIRS):
            return "evasion_grid_snapping_or_self_revisit"
        if (not grid.is_point_drc_clear(i, node)
                or Point(grid.physical(node)).intersects(grid.shapes[i])):
            diagnostic["native_mask_prefilter_rejections"] += 1
            return "native_fixed_copper_or_mask"
        return True

    def evasion_segment_clear(
        net: str, a: PointMM, b: PointMM, _min_clear: float,
    ) -> bool | str:
        i = NET_NAMES.index(net)
        start_node, end_node = evasion_node(a), evasion_node(b)
        if (start_node != state.paths[i][-1]
                or (end_node[0] - start_node[0],
                    end_node[1] - start_node[1]) not in DIRS):
            return "evasion_non_adjacent_grid_step"
        if not grid.is_segment_drc_clear(i, start_node, end_node):
            diagnostic["native_segment_rejections"] += 1
            return "native_fixed_copper_or_mask"
        segment = LineString((grid.physical(start_node),
                              grid.physical(end_node)))
        if not existing_distance(i, segment, state.paths, record=False):
            return "continuous_segment_pitch"
        return True

    def evasion_rejection(reason: str, bound_count: int) -> None:
        if bound_count != 3 or active_bind_count != 3:
            raise RuntimeError("Three-net evasion outside three-bound state")
        reject_reason(reason)

    def evasion_joint_clear(proposed: Mapping[str, PointMM]) -> bool | str:
        nodes = [evasion_node(proposed[net]) for net in NET_NAMES]
        # HOLD means no new copper; treat that member as a physical
        # point when checking concurrent new-to-new segment pitch.
        segments = [
            (Point(grid.physical(nodes[i]))
             if nodes[i] == state.paths[i][-1]
             else LineString((grid.physical(state.paths[i][-1]),
                              grid.physical(nodes[i]))))
            for i in range(3)]
        if any(segments[i].distance(segments[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            return "continuous_segment_pitch"
        return True

    evasion_generator = ThreeNetEvasionGenerator(
        net_order=NET_NAMES,
        is_point_clear=evasion_point_clear,
        is_segment_clear=evasion_segment_clear,
        is_joint_clear=evasion_joint_clear,
        record_rejection=evasion_rejection,
        config=ThreeNetEvasionConfig(
            step_mm=grid.res, min_pitch_mm=hard_pitch_mm,
            max_evasion_candidates=32),
    )
    evasion_stage_for_state: dict[PartialFreeState, str] = {}
    evasion_parent_for_state: dict[PartialFreeState, PartialFreeState] = {}

    start = PartialFreeState(((), (), ()))
    order = itertools.count()
    # Bounded weighted A* favours coordinated progress over combinatorial
    # prefixes. This influences search order ONLY, never geometric gates.
    epsilon = cost_model.w.heuristic_epsilon
    heap = [(epsilon * heuristic(start), 0., next(order), start)]
    # Fairness lane permits a small quota of exact-native-valid three-net
    # evasion children to be expanded rather than starved by single moves.
    # Each candidate remains in weighted A*, with unchanged g and all gates.
    fair_queue: deque[tuple[float, PartialFreeState]] = deque()
    last_fair_expansion = -8
    expansion_cpu_wall = 0.
    max_expansion_wall = 0.
    expanded_cost: dict[PartialFreeState, float] = {}
    best: dict[PartialFreeState, float] = {start: 0.}
    expansions = 0
    root_by_state: dict[PartialFreeState, PartialFreeState] = {}
    admitted_roots: set[PartialFreeState] = set()
    expanded_roots: set[PartialFreeState] = set()
    survived_roots: set[PartialFreeState] = set()
    progress_roots: set[PartialFreeState] = set()
    best_goal_progress_mm = 0.
    max_targets_reached = 0
    # Retain only a tiny set of EXPANDED, fully bound states. No change
    # to best/heap/fairness, transition costs, or native gates.
    choke_samples: dict[str, tuple[float, float, PartialFreeState]] = {}

    def save_choke_sample(
        key: str, state: PartialFreeState, progress: float,
    ) -> None:
        total = target_distance_sum(state)
        previous = choke_samples.get(key)
        if (previous is None or progress > previous[0] + TOL
                or (abs(progress - previous[0]) <= TOL
                    and total < previous[1] - TOL)):
            choke_samples[key] = (progress, total, state)

    def target_distance_sum(state: PartialFreeState) -> float:
        # Only compare fully bound, physically routed states. This is
        # telemetry, never a validity shortcut or replacement for DRC.
        return sum(min(dist(route[-1], p) for p in target_sets[i])
                   for i, route in enumerate(state.paths))

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
        diagnostic["third_binding_roots_with_goal_progress"] = (
            len(progress_roots))
        diagnostic["third_binding_goal_progress_rate"] = round(
            len(progress_roots) / max(1, len(admitted_roots)), 6)
        diagnostic["third_binding_best_goal_progress_mm"] = round(
            best_goal_progress_mm, 6)
        diagnostic["third_binding_max_targets_reached"] = (
            max_targets_reached)
        diagnostic["average_progress_sync_penalty"] = round(
            sync_sum / max(1, sync_count), 6)
        diagnostic["average_progress_sync_penalty_after_third_binding"] = round(
            post_third_sync_sum / max(1, post_third_sync_count), 6)
        diagnostic["rejections_by_bound_count"] = {
            str(i): dict(sorted(counter.items()))
            for i, counter in enumerate(rejection_by_binding)}
        diagnostic["three_net_evasion_average_expansion_ms"] = round(
            1000. * expansion_cpu_wall / max(1, expansions), 4)
        diagnostic["three_net_evasion_max_expansion_ms"] = round(
            1000. * max_expansion_wall, 4)

    while (heap or fair_queue) and expansions < max_expansions:
        if time.monotonic() - created >= max_seconds:
            diagnostic["status"] = "PARTIAL_FREE_WALL_BUDGET_EXHAUSTED"
            break
        # The FIRST fair candidate is eligible on the next expansion,
        # independent of the global expansion modulo. Later fair picks
        # are rate-limited by the last real pick (1 per eight expansions).
        fairness_pop = _evasion_fair_due(
            bool(fair_queue), expansions, last_fair_expansion)
        if not heap and fair_queue:
            # Each fair entry also lives in A*: no heap means duplicates.
            # Never break the strict one-in-eight fairness-expansion limit.
            fair_queue.clear()
            break
        if fairness_pop:
            g, state = fair_queue.popleft()
        else:
            _, g, _, state = heapq.heappop(heap)
        if g > best.get(state, math.inf) + 1e-9:
            if fairness_pop:
                diagnostic["three_net_evasion_fair_queue_stale_pops"] += 1
            continue
        if g >= expanded_cost.get(state, math.inf) - 1e-9:
            if fairness_pop:
                diagnostic["three_net_evasion_fair_queue_stale_pops"] += 1
            continue
        tick = time.monotonic()
        expanded_cost[state] = g
        expansions += 1
        if fairness_pop:
            last_fair_expansion = expansions
            diagnostic["three_net_evasion_fair_queue_pop_count"] += 1
            if diagnostic["three_net_evasion_first_expanded_expansion"] is None:
                diagnostic["three_net_evasion_first_expanded_expansion"] = expansions
                first = diagnostic["three_net_evasion_first_admitted_expansion"]
                diagnostic["three_net_evasion_first_wait_expansions"] = (
                    expansions - first if first is not None else None)
        bound = sum(bool(path) for path in state.paths)
        active_bind_count = bound
        diagnostic["search_states_by_bound_count"][bound] += 1
        probe: dict[str, Any] | None = None
        rejection_before: Counter[str] | None = None
        if state in evasion_stage_for_state:
            stage = evasion_stage_for_state[state]
            diagnostic["three_net_evasion_stages_expanded"][stage] += 1
            if diagnostic["three_net_evasion_first_expanded_probe"] is None:
                parent = evasion_parent_for_state[state]
                before_mm = tuple(
                    min(dist(parent.paths[i][-1], t) for t in target_sets[i])
                    for i in range(3))
                after_mm = tuple(
                    min(dist(state.paths[i][-1], t) for t in target_sets[i])
                    for i in range(3))
                probe = {
                    "stage": stage, "expansion": expansions,
                    "target_distance_before_mm": [
                        round(v, 6) for v in before_mm],
                    "target_distance_after_mm": [
                        round(v, 6) for v in after_mm],
                    "target_progress_by_net_mm": [
                        round(a - b, 6)
                        for a, b in zip(before_mm, after_mm)],
                    "edt_mm_by_net": [
                        round(float(edt_fields[i][route[-1][1],
                                                     route[-1][0]]), 6)
                        for i, route in enumerate(state.paths)],
                    "admitted_followup_states": 0,
                    "native_followup_rejections": {},
                }
                diagnostic["three_net_evasion_first_expanded_probe"] = probe
                rejection_before = reject.copy()
        admitted_this_expansion = 0
        if bound == 3 and state in root_by_state:
            root = root_by_state[state]
            root_progress = (target_distance_sum(root)
                             - target_distance_sum(state))
            save_choke_sample("MAX_GOAL_PROGRESS", state, root_progress)
            stage_name = evasion_stage_for_state.get(state)
            if stage_name in ("STAGGERED_EVADE", "LATERAL_EVADE",
                              "COUPLED_TURN", "ASYMMETRIC_EVADE"):
                save_choke_sample(stage_name, state, root_progress)
            expanded_roots.add(root)
            if state != root:
                survived_roots.add(root)
                improvement = (target_distance_sum(root)
                               - target_distance_sum(state))
                if improvement > 1e-8:
                    progress_roots.add(root)
                    best_goal_progress_mm = max(
                        best_goal_progress_mm, improvement)
            max_targets_reached = max(max_targets_reached, sum(
                route[-1] in target_sets[i]
                for i, route in enumerate(state.paths)))
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
            expansion_cpu_wall += time.monotonic() - tick
            max_expansion_wall = max(
                max_expansion_wall, time.monotonic() - tick)
            update_telemetry()
            return diagnostic
        if (bound == 3
                and sum(route[-1] not in target_sets[i]
                        for i, route in enumerate(state.paths)) >= 2
                and all(len(route) < max_route_nodes
                        for route in state.paths)):
            positions = state_positions(state)
            headings = {NET_NAMES[i]: route_heading(route)
                        for i, route in enumerate(state.paths)}
            deep_probe = expansions % 16 == 0
            if deep_probe:
                diagnostic["three_net_evasion_deep_probe_states"] += 1
            for proposed, _new_headings, tag in (
                    evasion_generator.generate_evasion_steps(
                        positions, headings, nearest_targets(state),
                        explore_lateral=deep_probe)):
                stage = next(
                    name for name in diagnostic["three_net_evasion_stages_generated"]
                    if tag.startswith(name))
                diagnostic["three_net_evasion_stages_generated"][stage] += 1
                next_nodes = [evasion_node(proposed[n]) for n in NET_NAMES]
                if any(
                        next_nodes[i] != state.paths[i][-1] and (
                            next_nodes[i] in state.paths[i] or
                            (next_nodes[i][0] - state.paths[i][-1][0],
                             next_nodes[i][1] - state.paths[i][-1][1])
                            not in DIRS)
                        for i in range(3)):
                    reject_reason("evasion_grid_snapping_or_self_revisit")
                    continue
                # The generator has already called evasion_joint_clear
                # on these EXACT snapped grid segments. A second pairwise
                # Shapely distance calculation here is redundant; no
                # constraint is removed from the accepted transition.
                routes = tuple(
                    (state.paths[i] if next_nodes[i] == state.paths[i][-1]
                     else (*state.paths[i], next_nodes[i]))
                    for i in range(3))
                candidate = PartialFreeState(routes)
                terms = score_transition(state, candidate)
                cost = (terms["step_cost"] +
                        .05 * sum(density(i, next_nodes[i])
                                  for i in range(3)))
                if push(candidate, g + cost, state, terms):
                    admitted_this_expansion += 1
                    evasion_parent_for_state[candidate] = state
                    evasion_stage_for_state[candidate] = stage
                    diagnostic["three_net_evasion_stages_admitted"][stage] += 1
                    if diagnostic["three_net_evasion_first_admitted_expansion"] is None:
                        diagnostic["three_net_evasion_first_admitted_expansion"] = expansions
                    # Never waive the A* heap; fairness only adds a bounded
                    # alternate read path over an already native-valid state.
                    if len(fair_queue) < 32:
                        fair_queue.append((g + cost, candidate))
                        diagnostic["three_net_evasion_fair_queue_peak"] = max(
                            diagnostic["three_net_evasion_fair_queue_peak"],
                            len(fair_queue))
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
                    if push(candidate,
                            g + terms["step_cost"] + .05 * density(agent, p),
                            state, terms):
                        admitted_this_expansion += 1
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
                if push(candidate, g + cost, state, terms):
                    admitted_this_expansion += 1
        if probe is not None and rejection_before is not None:
            probe["admitted_followup_states"] = admitted_this_expansion
            probe["native_followup_rejections"] = {
                k: reject[k] - rejection_before[k]
                for k in sorted(reject)
                if reject[k] > rejection_before[k]}
        elapsed_expansion = time.monotonic() - tick
        expansion_cpu_wall += elapsed_expansion
        max_expansion_wall = max(max_expansion_wall, elapsed_expansion)

    # Diagnostic-only nearest-neighbour audit; never enqueue a move.
    # Every geometry gate uses the same native scratch masks/shapes and
    # full immutable route histories as the router.
    for label, (progress, total, sampled) in sorted(choke_samples.items()):
        heads: list[dict[str, Any]] = []
        probes: list[dict[str, Any]] = []
        for i, route in enumerate(sampled.paths):
            at = route[-1]
            current_mm = grid.physical(at)
            eta = (float(edt_fields[i][at[1], at[0]])
                   if grid.is_point_drc_clear(i, at) else 0.)
            heads.append({
                "net": NET_NAMES[i], "grid_xy": list(at),
                "xy_mm": [round(v, 6) for v in current_mm],
                "heading_index": route_heading(route),
                "heading_grid": list(DIRS[route_heading(route)]),
                "edt_native_mask_mm": round(eta, 6),
                "target_distance_mm": round(
                    min(dist(at, p) for p in target_sets[i]), 6),
                "route_grid": [list(node) for node in route],
            })
            for direction_index, (dx, dy) in enumerate(DIRS):
                nxt = (at[0] + dx, at[1] + dy)
                next_mm = (float(grid.xs[0] + nxt[0] * grid.res),
                           float(grid.ys[0] + nxt[1] * grid.res))
                in_bounds = (0 <= nxt[0] < grid.width
                             and 0 <= nxt[1] < grid.height)
                segment = LineString((current_mm, next_mm))
                point_clear = in_bounds and grid.is_point_drc_clear(i, nxt)
                segment_clear = (point_clear
                                 and grid.is_segment_drc_clear(i, at, nxt))
                pair_gap = min((
                    segment.distance(immutable_route_geometry(other))
                    for j, other in enumerate(sampled.paths)
                    if j != i and other), default=math.inf)
                shape_gap = float(segment.distance(grid.shapes[i]))
                if not in_bounds:
                    block = "OUTSIDE_RASTER_BOUNDS"
                elif nxt in route:
                    block = "ROUTE_SELF_REVISIT"
                elif not point_clear:
                    block = "HARD_NATIVE_MASK_OR_ROI"
                elif not segment_clear:
                    block = "HARD_NATIVE_FIXED_COPPER_SEGMENT"
                elif pair_gap < hard_pitch_mm - TOL:
                    block = "HARD_OTHER_NET_TRACE_PITCH"
                else:
                    block = "NATIVE_PRECHECK_CLEAR"
                probes.append({
                    "net": NET_NAMES[i], "heading_index": direction_index,
                    "direction_grid": [dx, dy],
                    "from_mm": [round(v, 6) for v in current_mm],
                    "to_mm": [round(v, 6) for v in next_mm],
                    "to_grid": list(nxt),
                    "classification": block,
                    "native_mask_clear": bool(point_clear),
                    "native_segment_clear": bool(segment_clear),
                    "nearest_other_route_centreline_mm": (
                        round(pair_gap, 6) if math.isfinite(pair_gap) else None),
                    "pair_pitch_deficit_mm": (
                        round(max(0., hard_pitch_mm - pair_gap), 6)
                        if math.isfinite(pair_gap) else 0.),
                    "distance_to_inflated_native_shape_mm": round(shape_gap, 6),
                    "destination_edt_mm": (
                        round(float(edt_fields[i][nxt[1], nxt[0]]), 6)
                        if in_bounds else None),
                })
        diagnostic["three_net_choke_states"].append({
            "sample_role": label,
            "progress_from_third_bind_root_mm": round(progress, 6),
            "remaining_target_distance_sum_mm": round(total, 6),
            "heads": heads, "direction_probes": probes,
        })

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

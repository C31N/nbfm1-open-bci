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
from typing import Any, Sequence

from shapely.geometry import LineString, Point

from probe_block2_elastic_joint_corridor import DIRS, FCuCorridorGrid

Node = tuple[int, int]
PITCH_MM = .300
TOL = 1e-8


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

    @lru_cache(maxsize=8000)
    def heuristic(state: PartialFreeState) -> float:
        total = 0.
        for i, path in enumerate(state.paths):
            if path:
                total += min(dist(path[-1], goal)
                             for goal in target_sets[i])
            else:
                total += min(dist(source, goal)
                             for source in source_sets[i]
                             for goal in target_sets[i])
                total += .12
        return total

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
                reject["continuous_segment_pitch"] += 1
                return False
        return True

    def entry_clear(
        agent: int, p: Node, state: PartialFreeState,
    ) -> bool:
        if not grid.is_point_drc_clear(agent, p):
            reject["native_fixed_copper_or_mask"] += 1
            return False
        pt = Point(grid.physical(p))
        if pt.intersects(grid.shapes[agent]):
            reject["native_fixed_copper_or_mask"] += 1
            return False
        for i, route in enumerate(state.paths):
            if route and dist(route[0], p) < anchor_pitch_mm - TOL:
                reject["source_anchor_pitch"] += 1
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
            reject["target_anchor_pitch"] += 1
            return False
        # Redundant exact whole-history validation before a scratch return.
        wires = []
        for i, route in enumerate(state.paths):
            line = LineString([grid.physical(p) for p in route])
            if not line.is_valid or line.intersects(grid.shapes[i]):
                reject["native_fixed_copper_or_mask"] += 1
                return False
            wires.append(line)
        if any(wires[i].distance(wires[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reject["continuous_segment_pitch"] += 1
            return False
        return True

    start = PartialFreeState(((), (), ()))
    order = itertools.count()
    # Bounded weighted A* favours coordinated progress over combinatorial
    # prefixes. This influences search order ONLY, never geometric gates.
    epsilon = 2.0
    heap = [(epsilon * heuristic(start), 0., next(order), start)]
    best: dict[PartialFreeState, float] = {start: 0.}
    expansions = 0

    def push(state: PartialFreeState, g: float) -> None:
        if g + 1e-9 >= best.get(state, math.inf):
            return
        best[state] = g
        heapq.heappush(heap, (g + epsilon * heuristic(state),
                              g, next(order), state))

    while heap and expansions < max_expansions:
        if time.monotonic() - created >= max_seconds:
            diagnostic["status"] = "PARTIAL_FREE_WALL_BUDGET_EXHAUSTED"
            break
        _, g, _, state = heapq.heappop(heap)
        if g > best.get(state, math.inf) + 1e-9:
            continue
        expansions += 1
        bound = sum(bool(path) for path in state.paths)
        diagnostic["search_states_by_bound_count"][bound] += 1
        if finished(state):
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
                    if not entry_clear(agent, p, state):
                        continue
                    diagnostic["binding_actions_valid"] += 1
                    routes = list(state.paths)
                    routes[agent] = (p,)
                    push(PartialFreeState(tuple(routes)),
                         g + .12 + .05 * density(agent, p))
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
                    reject["native_fixed_copper_or_mask"] += 1
                    diagnostic["native_mask_prefilter_rejections"] += 1
                    continue
                if b in route:
                    continue
                if not grid.is_segment_drc_clear(agent, a, b):
                    reject["native_fixed_copper_or_mask"] += 1
                    diagnostic["native_segment_rejections"] += 1
                    continue
                step = LineString((grid.physical(a), grid.physical(b)))
                if not existing_distance(agent, step, state.paths):
                    continue
                routes = list(state.paths)
                routes[agent] = (*route, b)
                # Clearance density only biases search; it never waives
                # or hard-blocks a physically native-clear passage.
                cost = dist(a, b) + .22 * density(agent, b)
                push(PartialFreeState(tuple(routes)), g + cost)

    if diagnostic["status"] != "PARTIAL_FREE_WALL_BUDGET_EXHAUSTED":
        diagnostic["status"] = (
            "PARTIAL_FREE_NODE_BUDGET_EXHAUSTED"
            if heap else "PARTIAL_FREE_FRONTIER_EXHAUSTED")
    diagnostic["expansions"] = expansions
    diagnostic["reject_reasons"] = dict(reject)
    diagnostic["open_states_remaining"] = len(heap)
    diagnostic["wall_seconds"] = round(time.monotonic() - created, 3)
    return diagnostic

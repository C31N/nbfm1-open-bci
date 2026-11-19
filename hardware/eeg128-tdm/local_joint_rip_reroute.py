#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Transactional reassembly of speculative outer F.Cu paths (no board writes).

Native copper/escape obstacles are supplied as per-net hard Shapely shapes.
Independently found source/target paths are NOT treated as frozen copper:
only solved joint segments are reserved; each outer flank is rerouted.
No scratch proposal is promoted without continuous whole-route validation.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Callable

from shapely.geometry import LineString

Node = tuple[int, int]
Paths = tuple[tuple[Node, ...], ...]
RouteOne = Callable[[int, Node, Node, list[LineString]], tuple[Node, ...] | None]
PITCH_MM = .300
TOL = 1e-8


def reassemble_speculative_outside(
    local_routes: Paths,
    starts: tuple[Node, Node, Node],
    goals: tuple[Node, Node, Node],
    exact_tips: tuple[Any, ...],
    native_shapes: tuple[Any, ...],
    xs: Any,
    ys: Any,
    route_one: RouteOne,
    *,
    pitch_mm: float = PITCH_MM,
) -> tuple[Paths | None, dict[str, Any]]:
    """Return a verified scratch candidate or implicit hard rollback to None.

    This function does not touch a PCB or change original path snapshots.
    The callback is expected to use the *unchanged* native masks/shapes and
    hard 0.300-mm reservations, with continuous edge validation. The final
    whole-route check is independent of the callback's search approximation.
    """
    if (len(local_routes) != 3 or len(starts) != 3 or len(goals) != 3
            or len(exact_tips) != 3 or len(native_shapes) != 3
            or not math.isfinite(pitch_mm) or pitch_mm < PITCH_MM):
        raise ValueError("Exactly three nets, hard clearance, and tips required")

    diag: dict[str, Any] = {
        "status": "LOCAL_JOINT_ROLLBACK",
        "stage": "speculative_outside_replan",
        "original_hypothetical_paths_discarded": True,
        "native_obstacles_unchanged": True,
        "locked_escapes_unchanged": True,
        "rollback_on_any_failure": True,
        "permutation_attempts": 0,
        "complete_candidates_checked": 0,
        "new_vias_added": 0,
        "native_DRC_still_required": True,
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
    }

    def physical(node: Node) -> tuple[float, float]:
        x, y = node
        if not (0 <= x < len(xs) and 0 <= y < len(ys)):
            raise ValueError("Local route contains off-grid node")
        return float(xs[x]), float(ys[y])

    def line(route: tuple[Node, ...], net: int, full: bool) -> LineString:
        pts = [physical(p) for p in route]
        if full:
            pts = [tuple(exact_tips[net][0]), *pts, tuple(exact_tips[net][1])]
        return LineString(pts)

    if any(len(path) < 2 for path in local_routes):
        diag["status"] = "LOCAL_JOINT_EMPTY_CANDIDATE"
        return None, diag
    local_lines = tuple(line(path, i, False)
                        for i, path in enumerate(local_routes))
    if any(not l.is_valid or l.intersects(native_shapes[i])
           for i, l in enumerate(local_lines)):
        diag["status"] = "LOCAL_JOINT_NATIVE_COLLISION"
        return None, diag
    if any(local_lines[i].distance(local_lines[j]) < pitch_mm - TOL
           for i in range(3) for j in range(i + 1, 3)):
        diag["status"] = "LOCAL_JOINT_PAIRWISE_COLLISION"
        return None, diag

    for order in itertools.permutations(range(3)):
        diag["permutation_attempts"] += 1
        assembled: dict[int, tuple[Node, ...]] = {}
        wires: dict[int, LineString] = {}
        for i in order:
            # Reserve ALL solved local segments, even for agents that have
            # not yet obtained their outer paths. Completed full wires
            # supersede those agents' local reservations.
            reserved = [wires.get(j, local_lines[j]) for j in range(3)
                        if j != i]
            prefix = route_one(i, starts[i], local_routes[i][0], reserved)
            if (prefix is None or not prefix or prefix[0] != starts[i]
                    or prefix[-1] != local_routes[i][0]):
                break
            # Prefix is the SAME net: it must not be buffered as an
            # obstacle for its own suffix. Other nets remain hard.
            suffix = route_one(i, local_routes[i][-1], goals[i], reserved)
            if (suffix is None or not suffix or
                    suffix[0] != local_routes[i][-1] or
                    suffix[-1] != goals[i]):
                break
            # Scratch-only commit for this permutation; all other attempts
            # are discarded atomically if any flank or DRC gate fails.
            joined = tuple(prefix[:-1]) + local_routes[i] + tuple(suffix[1:])
            candidate_wire = line(joined, i, True)
            if (not candidate_wire.is_valid or
                    candidate_wire.intersects(native_shapes[i]) or
                    any(candidate_wire.distance(wires.get(j, local_lines[j]))
                        < pitch_mm - TOL for j in range(3) if j != i)):
                break
            assembled[i] = joined
            wires[i] = candidate_wire
        if len(assembled) != 3:
            continue

        diag["complete_candidates_checked"] += 1
        complete = tuple(assembled[i] for i in range(3))
        if any(wires[i].distance(wires[j]) < pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            continue
        diag["status"] = "LOCAL_JOINT_SCRATCH_PROPOSAL_REVALIDATED"
        diag["minimum_complete_centreline_mm"] = round(min(
            wires[i].distance(wires[j])
            for i in range(3) for j in range(i + 1, 3)), 6)
        return complete, diag

    diag["status"] = "LOCAL_JOINT_OUTSIDE_REPLAN_EXHAUSTED"
    return None, diag

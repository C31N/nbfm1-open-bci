#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact one-hop entry/exit feasibility for bounded three-net joint A*.

Each candidate is read-only. The preflight only rejects anchor triplets when
NO simultaneous non-stationary transition exists. It never infers a complete
route from this necessary condition. Native per-net copper masks remain hard.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any

from shapely.geometry import LineString, Point

Node = tuple[int, int]
DIRECTIONS: tuple[Node, ...] = (
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1))
PATTERNS: tuple[tuple[int, int, int], ...] = (
    (1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1),
    (1, 1, 0), (0, 1, 1), (1, 0, 1))
HARD_PITCH_MM = .300
TOL = 1e-8


def preflight_joint_entry_exit(
    grid: Any,
    starts: tuple[Node, Node, Node],
    goals: tuple[Node, Node, Node],
    *,
    hard_pitch_mm: float = HARD_PITCH_MM,
) -> dict[str, Any]:
    """Find native-clear forward and reverse boundary steps.

    No candidate is accepted for hardware; a passing preflight only means
    joint A* is worth attempting. All legal moves are checked as continuous
    line segments, not just their endpoints. Never remove native shapes.
    """
    if len(starts) != 3 or len(goals) != 3 or (
            not math.isfinite(hard_pitch_mm) or
            hard_pitch_mm < HARD_PITCH_MM):
        raise ValueError("Three endpoints and hard pitch required")
    reasons: Counter[str] = Counter()

    def legal(
        a: tuple[Node, Node, Node],
        b: tuple[Node, Node, Node],
    ) -> bool:
        if any(not grid.is_point_drc_clear(i, p)
               for i, p in enumerate(a)) or any(
                   not grid.is_point_drc_clear(i, p)
                   for i, p in enumerate(b)):
            reasons["native_fixed_copper_or_mask"] += 1
            return False
        pts = [grid.physical(p) for p in b]
        if any(math.dist(pts[i], pts[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reasons["pairwise_point_pitch"] += 1
            return False
        lines = [
            LineString((grid.physical(p), grid.physical(q)))
            if p != q else Point(grid.physical(p))
            for p, q in zip(a, b)
        ]
        if any(lines[i].distance(lines[j]) < hard_pitch_mm - TOL
               for i in range(3) for j in range(i + 1, 3)):
            reasons["continuous_segment_pitch"] += 1
            return False
        if any(not grid.is_segment_drc_clear(i, a[i], b[i])
               for i in range(3)):
            reasons["native_fixed_copper_or_mask"] += 1
            return False
        return True

    def moves(
        anchors: tuple[Node, Node, Node],
        reverse: bool,
    ) -> int:
        found = 0
        for dx, dy in DIRECTIONS:
            for pattern in PATTERNS:
                adjacent = tuple(
                    (p[0] + (dx * m), p[1] + (dy * m))
                    for p, m in zip(anchors, pattern))
                step_clear = (
                    legal(adjacent, anchors) if reverse
                    else legal(anchors, adjacent))
                if step_clear:
                    found += 1
        return found

    source_moves = moves(starts, False)
    goal_moves = moves(goals, True)
    status = (
        "JOINT_ANCHOR_FIRST_STEP_FEASIBLE"
        if source_moves and goal_moves
        else "JOINT_ANCHOR_FIRST_STEP_BLOCKED")
    return {
        "status": status,
        "source_legal_moves": source_moves,
        "target_reverse_legal_moves": goal_moves,
        "reject_reasons": dict(sorted(reasons.items())),
        "hard_centreline_pitch_mm": HARD_PITCH_MM,
        "native_exact_segment_gate": True,
        "geometry_unsatisfiable_proven": False,
        "native_DRC_still_required": True,
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
        "new_vias_added": 0,
    }

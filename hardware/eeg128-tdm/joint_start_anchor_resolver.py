#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Conservative, read-only local F.Cu boundary anchor selection.

All prefix/suffix path segments outside the selected window remain frozen.
Never infer that independently valid routes are mutually valid. The resolver
does not alter KiCad, create vias, relax native masks, or release fabrication.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any

from shapely.geometry import LineString, Point

Node = tuple[int, int]
PITCH_MM = .300
TOL = 1e-8


@dataclass(frozen=True)
class AnchorResolution:
    status: str
    starts: tuple[int, int, int] | None
    targets: tuple[int, int, int] | None
    audited_combinations: int
    reason: str
    original_source_pitch_mm: float
    original_target_pitch_mm: float
    outside_paths_speculative: bool = False
    candidate_pairs: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = ()

    def as_diagnostic(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "start_indices": list(self.starts) if self.starts is not None else None,
            "target_indices": list(self.targets) if self.targets is not None else None,
            "audited_combinations": self.audited_combinations,
            "eligible_candidate_count": len(self.candidate_pairs),
            "candidate_anchor_indices": [
                {"start": list(start), "target": list(target)}
                for start, target in self.candidate_pairs
            ],
            "reason": self.reason,
            "original_source_pitch_mm": self.original_source_pitch_mm,
            "original_target_pitch_mm": self.original_target_pitch_mm,
            "partial_free_net_is_diagnostic_only": True,
            "fixed_outside_paths_preserved": not self.outside_paths_speculative,
            "speculative_outside_replan_required": self.outside_paths_speculative,
            "locked_escape_ripup_permitted": False,
            "new_vias_added": 0,
            "accepted": False,
            "routing_completed": False,
            "fabrication_release": False,
        }


def resolve_window_anchors(
    paths: tuple[tuple[Node, ...], ...],
    spans: tuple[tuple[int, int], ...],
    masks: tuple[Any, ...] | list[Any],
    shapes: tuple[Any, ...] | list[Any],
    xs: Any,
    ys: Any,
    window: Any,
    *,
    max_shift_nodes: int = 5,
    max_side_triplets: int = 24,
    pitch_mm: float = PITCH_MM,
    speculative_outside: bool = False,
    max_solutions: int = 1,
    min_anchor_pitch_mm: float = PITCH_MM,
) -> AnchorResolution:
    """Search bounded source/target anchor triplets without board mutation.

    With speculative_outside=True, individually computed prefix/suffix paths
    are discarded rather than mistaken for immutable copper. That mode
    returns tentative anchors ONLY; every outer segment must be independently
    rerouted and the complete three-net candidate revalidated before use.
    Actual copper remains constrained by the supplied native masks/shapes.

    Endpoint movement is only *along an independently verified existing
    path*. No off-path projection, clearance waiver, or endpoint invention.
    Returned positions are a candidate for an independently checked local
    joint solver, never a completed PCB route.
    """
    if (len(paths) != 3 or len(spans) != 3 or len(masks) != 3 or
            len(shapes) != 3 or max_shift_nodes < 0 or
            not 0 < max_side_triplets <= 128 or
            not math.isfinite(pitch_mm) or pitch_mm < PITCH_MM or
            not 1 <= max_solutions <= 12 or
            not math.isfinite(min_anchor_pitch_mm) or
            min_anchor_pitch_mm < PITCH_MM):
        raise ValueError("Invalid bounded three-net anchor request")

    import numpy as np

    ny, nx = len(ys), len(xs)
    raster = tuple(np.asarray(m, dtype=bool) for m in masks)
    if any(m.shape != (ny, nx) for m in raster):
        raise ValueError("Anchor mask / grid dimension mismatch")

    def coord(p: Node) -> tuple[float, float]:
        x, y = p
        if not (0 <= x < nx and 0 <= y < ny):
            raise ValueError("Anchor path contains off-grid node")
        return float(xs[x]), float(ys[y])

    for route, (first, last) in zip(paths, spans):
        if not (0 < first < last < len(route) - 1):
            raise ValueError("Frozen endpoint span not strictly interior")
        for p in route:
            coord(p)

    def point_free(net: int, index: int) -> bool:
        node = paths[net][index]
        x, y = coord(node)
        return (window.contains((x, y))
                and not raster[net][node[1], node[0]]
                and not Point(x, y).intersects(shapes[net]))

    def min_pitch(indices: tuple[int, int, int]) -> float:
        pts = [coord(paths[i][indices[i]]) for i in range(3)]
        return min(math.dist(pts[i], pts[j])
                   for i in range(3) for j in range(i + 1, 3))

    original_s = tuple(span[0] for span in spans)
    original_t = tuple(span[1] for span in spans)
    start_options: list[list[int]] = []
    target_options: list[list[int]] = []
    for i, (a, b) in enumerate(spans):
        starts = [k for k in range(a, min(a + max_shift_nodes, b - 1) + 1)
                  if point_free(i, k)]
        goals = [k for k in range(b, max(b - max_shift_nodes, a + 1) - 1, -1)
                 if point_free(i, k)]
        start_options.append(starts)
        target_options.append(goals)

    def outcome(status: str, why: str, checked: int = 0,
                starts: tuple[int, int, int] | None = None,
                targets: tuple[int, int, int] | None = None,
                pairs: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (),
                ) -> AnchorResolution:
        return AnchorResolution(
            status, starts, targets, checked, why,
            round(min_pitch(original_s), 6),
            round(min_pitch(original_t), 6),
            outside_paths_speculative=speculative_outside,
            candidate_pairs=pairs)

    if any(not row for row in start_options + target_options):
        return outcome(
            "partial_free_net", "No mask-clear window anchor for all three nets")

    def side_candidates(
        options: list[list[int]], orig: tuple[int, int, int],
    ) -> list[tuple[int, int, int]]:
        candidates = [tuple(comb) for comb in itertools.product(*options)
                      if min_pitch(tuple(comb)) >= max(
                          pitch_mm, min_anchor_pitch_mm) - TOL]
        candidates.sort(key=lambda c: (
            sum(abs(c[i] - orig[i]) for i in range(3)), c))
        return candidates[:max_side_triplets]

    source_candidates = side_candidates(start_options, original_s)
    target_candidates = side_candidates(target_options, original_t)
    if not source_candidates or not target_candidates:
        return outcome(
            "MIDPOINT_JOINT_START_ANCHORS_INVALID",
            "No simultaneous centreline-pitch-compliant triplet")

    checked = 0
    candidates: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    # A prefix / suffix is immutable copper for the proposed local solve.
    # Collision across *different* nets disqualifies the entire attempt.
    ranked_pairs = sorted(
        ((si, ti, start, target)
         for si, start in enumerate(source_candidates)
         for ti, target in enumerate(target_candidates)),
        key=lambda entry: (
            max(entry[0], entry[1]), entry[0] + entry[1],
            entry[0], entry[1]))
    for _, _, start, target in ranked_pairs:
        if any(start[i] >= target[i] for i in range(3)):
            continue
        checked += 1
        if speculative_outside:
            candidates.append((start, target))
            if len(candidates) >= max_solutions:
                return outcome(
                    "speculative_joint_entry_exit",
                    "Native mask-clear anchors only; outside reroute mandatory",
                    checked, candidates[0][0], candidates[0][1],
                    tuple(candidates))
            continue
        frozen = []
        for i, route in enumerate(paths):
            for part in (route[:start[i] + 1], route[target[i]:]):
                if len(part) >= 2:
                    frozen.append((i, LineString([coord(p) for p in part])))
        if any(first.distance(second) < pitch_mm - TOL
               for k, (net, first) in enumerate(frozen)
               for other_net, second in frozen[k + 1:]
               if net != other_net):
            continue
        # A chosen anchor may not touch any foreign frozen wire.
        endpoints = ((i, coord(paths[i][start[i]]),
                      coord(paths[i][target[i]]))
                     for i in range(3))
        if any(Point(p).distance(line) < pitch_mm - TOL
               for i, source, goal in endpoints
               for p in (source, goal)
               for net, line in frozen if net != i):
            continue
        status = ("direct_window_entry"
                  if start == original_s and target == original_t
                  else "shifted_along_path")
        candidates.append((start, target))
        if len(candidates) >= max_solutions:
            return outcome(
                status, "Frozen outside segments collision-free",
                checked, candidates[0][0], candidates[0][1],
                tuple(candidates))

    if candidates:
        start, target = candidates[0]
        return outcome(
            "speculative_joint_entry_exit" if speculative_outside
            else "shifted_along_path",
            "Bounded anchor candidates collected", checked,
            start, target, tuple(candidates))

    return outcome(
        "MIDPOINT_JOINT_START_ANCHORS_INVALID",
        "All bounded triplets collide with frozen foreign copper",
        checked)

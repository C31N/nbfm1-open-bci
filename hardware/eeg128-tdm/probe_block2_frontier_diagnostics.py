#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only diagnosis of a failed 7.2-mm F.Cu three-net search frontier.

Grid-mask reachability is a diagnostic approximation, NOT a manufacturability
proof: it does not establish that angled grid edges, endpoint stubs, or
competing rubber-band trees meet KiCad's native design rules.
"""
from __future__ import annotations

from collections import deque
import math
import re
from typing import Any

STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1),
         (1, 1), (1, -1), (-1, 1), (-1, -1))


def sampled_reachability(
    xs: Any, ys: Any, blocked: Any,
    start: tuple[float, float], goal: tuple[float, float],
    *, max_visited: int = 44000,
) -> dict[str, Any]:
    """Bounded 8-neighbour grid-mask BFS, no copper or via modifications."""
    nx, ny = len(xs), len(ys)
    if nx < 2 or ny < 2 or blocked.shape != (ny, nx):
        raise ValueError("Invalid native frontier grid dimensions")
    if nx * ny > 180000 or not 1 <= max_visited <= 44000:
        raise ValueError("Unbounded frontier request")
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    def point(node: tuple[int, int]) -> tuple[float, float]:
        return float(xs[node[0]]), float(ys[node[1]])
    def seed(pt: tuple[float, float]) -> tuple[int, int] | None:
        ix = round((pt[0] - float(xs[0])) / dx)
        iy = round((pt[1] - float(ys[0])) / dy)
        candidates = ((x, y) for y in range(max(0, iy-7), min(ny, iy+8))
                      for x in range(max(0, ix-7), min(nx, ix+8))
                      if not bool(blocked[y, x]))
        return min(candidates, key=lambda n: math.dist(point(n), pt),
                   default=None)
    a, b = seed(start), seed(goal)
    out: dict[str, Any] = {
        "status": "sampled_grid_diagnosis_only",
        "start_mask_seed": list(a) if a is not None else None,
        "goal_mask_seed": list(b) if b is not None else None,
        "visited_nodes": 0,
        "search_cap_reached": False,
        "same_sampled_free_component": False,
        "frontier_points_mm": [],
        "not_a_cutset_or_DRC_proof": True,
    }
    if a is None or b is None:
        out["status"] = "sampled_endpoint_seed_unavailable"
        return out
    seen = {a}
    pending = deque([a])
    while pending and len(seen) < max_visited:
        node = pending.popleft()
        for mx, my in STEPS:
            x, y = node[0] + mx, node[1] + my
            if (not 0 <= x < nx or not 0 <= y < ny
                    or bool(blocked[y, x])):
                continue
            if mx and my and (bool(blocked[node[1], x])
                              or bool(blocked[y, node[0]])):
                continue
            nxt = (x, y)
            if nxt not in seen:
                seen.add(nxt)
                pending.append(nxt)
    out["visited_nodes"] = len(seen)
    out["search_cap_reached"] = bool(pending)
    out["same_sampled_free_component"] = b in seen
    # Rank frontier by proximity to the blocked target endpoint. Spread the
    # samples to distinct locations to avoid reporting one pixel repeatedly.
    nearest = sorted(seen, key=lambda n: math.dist(point(n), goal))
    front: list[tuple[float, float]] = []
    for node in nearest[:2000]:
        p = point(node)
        if all(math.dist(p, prev) >= .55 for prev in front):
            front.append(p)
        if len(front) >= 8:
            break
    out["frontier_points_mm"] = [
        [round(p[0], 5), round(p[1], 5)] for p in front]
    out["closest_reachable_to_goal_mm"] = (
        round(math.dist(front[0], goal), 6) if front else None)
    return out


def inspect_failed_frontier(
    board: Any, net: str,
    endpoints: dict[str, tuple[tuple[float, float],
                               tuple[float, float]]],
    earlier: dict[str, list[tuple[float, float]]],
    xs: Any, ys: Any, blocked: Any, window: Any,
    hard_detours: Any,
) -> dict[str, Any]:
    """Identify real KiCad UUID candidates near the sampled search frontier."""
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    from route_targeted_closure import pad_copper_shape, xy

    if net not in endpoints or not net.startswith("CH"):
        raise ValueError("Invalid target net for native corridor probe")
    source, target = endpoints[net]
    sampled = sampled_reachability(xs, ys, blocked, source, target)
    front = sampled["frontier_points_mm"]
    result = {
        **sampled,
        "target_net": net,
        "known_previous_nets": sorted(earlier),
        "window_bounds_mm": [round(v, 5) for v in window.bounds],
        "frontier_near_window_edge_mm": None,
        "frontier_near_hard_detour_mm": None,
        "nearest_fixed_copper_UUID_candidates": [],
        "UUID_candidates_are_not_proven_causes": True,
        "manufacturing_clearance_unchanged": True,
        "source_board_modified": False,
    }
    if not front:
        return result
    margin = min(
        min(p[0]-window.bounds[0], window.bounds[2]-p[0],
            p[1]-window.bounds[1], window.bounds[3]-p[1])
        for p in front
    )
    result["frontier_near_window_edge_mm"] = round(float(margin), 6)
    if hard_detours is not None:
        result["frontier_near_hard_detour_mm"] = round(
            min(Point(p).distance(hard_detours) for p in front), 6)

    region = unary_union([Point(p).buffer(.95) for p in front])
    candidates: list[dict[str, Any]] = []
    def add(shape: Any, obj: Any, kind: str, ref: str = "",
            number: str = "") -> None:
        if obj.GetNetname() == net or not shape.intersects(region):
            return
        distance = min(float(Point(p).distance(shape)) for p in front)
        if distance > .95:
            return
        name = obj.GetNetname()
        ch = re.match(r"CH(\d{3})_", name)
        candidates.append({
            "uuid": obj.m_Uuid.AsString(),
            "net": name, "kind": kind,
            "footprint": ref, "pad": number,
            "distance_to_frontier_copper_mm": round(distance, 6),
            "block1": bool(ch and int(ch.group(1)) < 16),
            "protected_named_net": name in (
                "VCM", "MUX_EN", "MUX_S2", "MUX_S3",
                "CH038_P_MUX", "3V3A"),
        })

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            bounds = pad.GetBoundingBox()
            b = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                    pcbnew.ToMM(bounds.GetRight()),
                    pcbnew.ToMM(bounds.GetBottom()))
            if b.intersects(region):
                add(pad_copper_shape(pad, pcbnew.F_Cu), pad, "pad",
                    footprint.GetReference(), pad.GetNumber())
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
            kind = "through_via"
        elif track.GetLayer() != pcbnew.F_Cu:
            continue
        elif isinstance(track, pcbnew.PCB_ARC):
            b = track.GetBoundingBox()
            shape = box(pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
                        pcbnew.ToMM(b.GetRight()),
                        pcbnew.ToMM(b.GetBottom()))
            kind = "arc_conservative_bbox"
        else:
            shape = LineString(
                [xy(track.GetStart()), xy(track.GetEnd())]
            ).buffer(pcbnew.ToMM(track.GetWidth()) / 2)
            kind = "track"
        if shape.intersects(region):
            add(shape, track, kind)
    candidates.sort(key=lambda row: (
        row["distance_to_frontier_copper_mm"], row["uuid"]))
    result["nearest_fixed_copper_UUID_candidates"] = candidates[:20]
    result["candidates_examined_near_frontier"] = len(candidates)
    result["previous_path_distance_to_frontier_mm"] = {
        name: round(min(Point(p).distance(LineString(path))
                        for p in front), 6)
        for name, path in earlier.items() if len(path) >= 2
    }
    return result

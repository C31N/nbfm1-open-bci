#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native, strictly non-promoting MUX_EN F.Cu/B.Cu/F.Cu hop trial.

The only input is the SHA-pinned 139-airwire ZIP. All mutations occur in a
TemporaryDirectory on a disposable KiCad board. The CH019_N_MUX cut is NOT
restituted in this isolated trial, so the trial is never an accepted route.
No original user PCB is changed, no manufacturing exports are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_fcu_blocker_uuids import (
    ARCHIVE_SHA256, BOARD_SHA256, MEMBERS,
)
from probe_ch025_cooperative8 import (
    unchanged_fingerprints, pinned_items, CH027_ALT_VIA,
)
from probe_ch025_fcu_l3_exact import track_inventory
from analyze_ch025_l3_precision_mask import exact_native_difference
from route_targeted_closure import make_track, make_via, metrics, native, xy

EN = "MUX_EN"
CH019 = "CH019_N_MUX"
TEMP_CUT = "0832ca70-347c-5b2d-b8d9-c8fff7096f8a"
WEST = (29.75, 38.5)
EAST = (36.75, 34.0)
L1_SOURCE = (
    (27.8179, 37.1976), (25.1522, 34.518156),
    (24.851101, 34.014647), (22.785232, 34.362501),
    (21.978656, 37.411514), (28.154375, 43.048832),
    (42.329022, 40.609242), (45.990999, 41.31438),
    (45.378779, 38.45575), (39.575553, 38.955414),
    (31.990961, 38.904087), (31.615215, 38.190539), WEST,
)
L4_MIDDLE = (WEST, (36.695964, 36.713327), EAST)
L1_TARGET = (
    EAST, (36.479738, 33.41319), (37.955409, 34.928617),
    (37.96, 37.100984), (43.8939, 37.1976),
)
FLAGS: dict[str, bool] = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "manufacturing_export_invoked": False,
    "checkpoint_promoted": False, "independent_replay_verified": False,
    "schematic_parity_qualified": False,
    "CH019_restitution_qualified": False,
}


def approved_geometry() -> dict[str, Any]:
    """Preflight exact probe #16 vertices and pad/via constraints."""
    if (L1_SOURCE[0] != (27.8179, 37.1976)
            or L1_SOURCE[-1] != WEST
            or L4_MIDDLE[0] != WEST or L4_MIDDLE[-1] != EAST
            or L1_TARGET[0] != EAST
            or L1_TARGET[-1] != (43.8939, 37.1976)):
        raise ValueError("Reviewed native probe #16 endpoints drifted")
    for path in (L1_SOURCE, L4_MIDDLE, L1_TARGET):
        if len(path) < 2 or any(
                not math.isfinite(k) for pt in path for k in pt):
            raise ValueError("Invalid mesh points")
        if any(math.dist(a, b) < .000001
               for a, b in zip(path, path[1:])):
            raise ValueError("Zero-length mesh segment")
    return {
        "F_Cu_source_waypoints": len(L1_SOURCE),
        "B_Cu_waypoints": len(L4_MIDDLE),
        "F_Cu_target_waypoints": len(L1_TARGET),
        "new_vias_mm": [list(WEST), list(EAST)],
        "new_via_diameter_mm": .65,
        "source_route_length_mm": round(sum(
            math.dist(a, b) for a, b in
            zip(L1_SOURCE, L1_SOURCE[1:])), 6),
        "B_Cu_route_length_mm": round(sum(
            math.dist(a, b) for a, b in
            zip(L4_MIDDLE, L4_MIDDLE[1:])), 6),
        "target_route_length_mm": round(sum(
            math.dist(a, b) for a, b in
            zip(L1_TARGET, L1_TARGET[1:])), 6),
    }




def polygon_contours(polyset: Any,
                     vias: tuple[tuple[float, float], ...]
                     ) -> list[dict[str, Any]]:
    """Locate exact KiCad IU delta contours, without rounding the gate."""
    from shapely.geometry import Point, Polygon
    from route_targeted_closure import xy

    result: list[dict[str, Any]] = []
    for index in range(polyset.OutlineCount()):
        outline = polyset.Outline(index)
        points = [xy(outline.CPoint(i))
                  for i in range(outline.PointCount())]
        if len(points) < 3:
            raise RuntimeError("Malformed L3 difference contour")
        shape = Polygon(points)
        if shape.is_empty or not shape.is_valid:
            raise RuntimeError("Invalid native L3 difference polygon")
        result.append({
            "bounds_mm": [round(v, 9) for v in shape.bounds],
            "polygon_area_mm2": shape.area,
            "vertex_count": len(points),
            "distance_to_west_via_mm": shape.distance(Point(vias[0])),
            "distance_to_east_via_mm": shape.distance(Point(vias[1])),
            "sample_points_mm": [list(p) for p in points[:6]],
        })
    return result


def optimize_fcu_source(board: Any, code: int,
                        path: tuple[tuple[float, float], ...]
                        ) -> tuple[tuple[tuple[float, float], ...],
                                   dict[str, Any]]:
    """Reduce only verified visibility corners without changing fixed nets."""
    import pcbnew
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles, routing_domain
    from probe_ch025_fcu_l3_exact import power_fcu_obstacles

    domain = routing_domain(board, .075, .25)
    region = domain.intersection(box(20.0, 31.0, 48.0, 45.0))
    walls, _ = obstacles(
        board, code, .15, .15, region, .65,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    free = region.difference(unary_union([
        walls[0], power_fcu_obstacles(board)])).buffer(-.000005)
    length = lambda pts: sum(  # noqa: E731
        math.dist(a, b) for a, b in zip(pts, pts[1:]))
    baseline = length(path)
    # The numerical fallback retains the already tested full path.
    if not all(free.covers(LineString([a, b]))
               for a, b in zip(path, path[1:])):
        return path, {
            "status": "original_path_not_inside_strict_model",
            "original_mm": baseline,
            "candidate_mm": baseline,
            "shortened": False,
        }
    result: list[tuple[float, float]] = [path[0]]
    idx = 0
    while idx < len(path) - 1:
        farthest = next((
            end for end in range(len(path) - 1, idx, -1)
            if free.covers(LineString([path[idx], path[end]]))
        ), idx + 1)
        result.append(path[farthest])
        idx = farthest
    proposed = tuple(result)
    improved = length(proposed) + .000001 < baseline
    return (proposed if improved else path), {
        "status": ("strict_visibility_shortcut_found"
                   if improved else "no_strict_visibility_shortcut"),
        "original_mm": baseline,
        "candidate_mm": length(proposed) if improved else baseline,
        "shortened": improved,
        "waypoints": len(proposed if improved else path),
        "native_DRC_qualified": False,
    }


def propose_ch019_bcu_restitution(board: Any, source: tuple[float, float],
                                 target: tuple[float, float],
                                 power: Any) -> dict[str, Any]:
    """Read-only B.Cu geometry on scratch, after the EN hop occupies copper."""
    import pcbnew
    from shapely.geometry import Point, box
    from escape_mesh_505 import mesh_route, polygons
    from route_targeted_closure import obstacles, routing_domain
    from analyze_ch025_bcu_cut_uuids import survey as gap_survey

    code = board.FindNet(CH019).GetNetCode()
    domain = routing_domain(board, .075, .25)
    corridor = domain.intersection(box(
        min(source[0], target[0]) - 9,
        min(source[1], target[1]) - 9,
        max(source[0], target[0]) + 9,
        max(source[1], target[1]) + 9))
    walls, _ = obstacles(
        board, code, .15, .15, corridor, .65,
        (pcbnew.B_Cu, pcbnew.F_Cu))
    free = corridor.difference(walls[0]).buffer(-.000005)
    parts = polygons(free)

    def component(p: tuple[float, float]) -> int | None:
        return next((i for i, shape in enumerate(parts)
                     if shape.covers(Point(p))), None)

    source_id, target_id = component(source), component(target)
    report: dict[str, Any] = {
        "source_mm": list(source), "target_mm": list(target),
        "BCu_source_component": source_id,
        "BCu_target_component": target_id,
        "BCu_same_component": (
            source_id is not None and source_id == target_id),
        "B_Cu_route_proven_by_native_DRC": False,
        "In1_Cu_used": False,
        "path_found": False, "path": None,
    }
    if source_id is None or target_id is None:
        report["status"] = "CH019_original_endpoint_outside_BCu_free"
        return report
    if source_id != target_id:
        report["status"] = "CH019_BCu_component_separated_after_EN_hop"
        report["blocking_UUID_inventory"] = gap_survey(
            board, parts[source_id], parts[target_id],
            target_net=CH019)
        return report
    trial = mesh_route(
        board, source, target, code,
        (pcbnew.B_Cu, pcbnew.F_Cu), power, corridor,
        start_layer=0, goal_layer=0, allow_vias=False)
    if (trial is None or len(trial) < 2
            or trial[0] != (0, *source)
            or trial[-1] != (0, *target)
            or any(p[0] != 0 for p in trial)):
        report["status"] = "CH019_native_mesh_BCu_candidate_missing"
        return report
    points = [tuple(p[1:]) for p in trial]
    report.update({
        "status": "CH019_BCu_mesh_found_unqualified",
        "path_found": True, "path": [list(p) for p in points],
        "length_mm": sum(
            math.dist(a, b) for a, b in zip(points, points[1:])),
        "candidate_waypoints": len(points),
    })
    return report



def native_polygon_ring_digest(polyset: Any) -> dict[str, Any]:
    """Canonical exact integer-coordinate polygon-ring identity.

    This compares native KiCad IU vertices, allowing only ring rotation,
    reversal and polygon reordering. It never uses an area epsilon.
    Equality of hashes is supporting evidence, NOT a released L3 gate.
    """
    def ring(chain: Any) -> tuple[tuple[int, int], ...]:
        items = [(int(chain.CPoint(k).x), int(chain.CPoint(k).y))
                 for k in range(chain.PointCount())]
        if len(items) > 1 and items[0] == items[-1]:
            items.pop()
        if len(items) < 3:
            raise RuntimeError("Native L3 polygon has fewer than 3 vertices")
        def orient(values: list[tuple[int, int]]
                   ) -> tuple[tuple[int, int], ...]:
            low = min(values)
            starts = [i for i, value in enumerate(values) if value == low]
            return min(tuple(values[i:] + values[:i]) for i in starts)
        return min(orient(items), orient(list(reversed(items))))

    components = []
    nvertices = 0
    for i in range(polyset.OutlineCount()):
        outer = ring(polyset.Outline(i))
        holes = sorted(ring(polyset.Hole(i, j))
                       for j in range(polyset.HoleCount(i)))
        components.append((outer, tuple(holes)))
        nvertices += len(outer) + sum(len(hole) for hole in holes)
    encoded = json.dumps(sorted(components), separators=(",", ":"))
    return {
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "outline_count": len(components),
        "native_vertex_count": nvertices,
    }



def survey_reused_west_via(
        board: Any, power: Any, *,
        existing_west: tuple[float, float] = (21.945, 37.6933),
        via_uuid: str = "c327c9cb-0509-46fc-b340-06bbd6a58962",
        virtual_block1_cut_audit: bool = True) -> dict[str, Any]:
    """Read-only source-F.Cu/B.Cu proposal using an EXISTING MUX_EN via."""
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from escape_mesh_505 import mesh_route, polygons
    from probe_ch025_fcu_l3_exact import power_fcu_obstacles
    from route_targeted_closure import obstacles, routing_domain

    target_east = EAST
    en_code = board.FindNet(EN).GetNetCode()
    candidates = [v for v in board.GetTracks()
                  if isinstance(v, pcbnew.PCB_VIA)
                  and v.GetNetCode() == en_code
                  and xy(v.GetPosition()) == existing_west]
    report: dict[str, Any] = {
        "existing_west_via_uuid": via_uuid,
        "existing_west_via_xy_mm": list(existing_west),
        "source_FCu_connected": False,
        "west_to_east_BCu_connected": False,
        "reuse_all_original_via_copper": True,
        "new_west_via_required": None,
        "F_Cu_source_path": None,
        "B_Cu_middle_path": None,
        "native_DRC_qualified": False,
        "L3_exact_gate_qualified": False,
        "fabrication_release": False,
    }
    if (len(candidates) != 1 or
            candidates[0].m_Uuid.AsString() !=
            report["existing_west_via_uuid"]):
        report["status"] = "reviewed_retained_west_via_missing"
        return report
    domain = routing_domain(board, .075, .25)
    fcuregion = domain.intersection(box(17.0, 30.0, 33.0, 56.0))
    bcuregion = domain.intersection(box(17.0, 26.0, 45.0, 58.0))
    fcuwalls, _ = obstacles(
        board, en_code, .15, .15, fcuregion, .65,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    fcufree = fcuregion.difference(fcuwalls[0].union(
        power_fcu_obstacles(board))).buffer(-.000005)
    bcuwalls, _ = obstacles(
        board, en_code, .15, .15, bcuregion, .65,
        (pcbnew.B_Cu, pcbnew.F_Cu))
    bcufree = bcuregion.difference(bcuwalls[0]).buffer(-.000005)

    def connected(free: Any, a: tuple[float, float],
                  b: tuple[float, float]) -> bool:
        return any(p.covers(Point(a)) and p.covers(Point(b))
                   for p in polygons(free))
    source = L1_SOURCE[0]
    report["source_FCu_connected"] = connected(
        fcufree, source, existing_west)
    report["west_to_east_BCu_connected"] = connected(
        bcufree, existing_west, target_east)
    report["expanded_BCu_windows"] = []
    if not report["west_to_east_BCu_connected"]:
        from analyze_ch025_bcu_cut_uuids import survey as gap_survey
        for label, bounds in (
                ("regional", (15.0, 21.0, 52.0, 57.0)),
                ("extended", (11.0, 12.0, 68.0, 74.0))):
            alternative = domain.intersection(box(*bounds))
            layer_walls, _ = obstacles(
                board, en_code, .15, .15, alternative, .65,
                (pcbnew.B_Cu, pcbnew.F_Cu))
            free = alternative.difference(
                layer_walls[0]).buffer(-.000005)
            parts = polygons(free)
            src_part = next((i for i, p in enumerate(parts)
                             if p.covers(Point(existing_west))), None)
            dst_part = next((i for i, p in enumerate(parts)
                             if p.covers(Point(target_east))), None)
            same = src_part is not None and src_part == dst_part
            row: dict[str, Any] = {
                "name": label, "bounds_mm": list(bounds),
                "source_component": src_part,
                "target_component": dst_part,
                "BCu_connected": same,
                "native_DRC_qualified": False,
            }
            if (label == "extended" and not same
                    and src_part is not None and dst_part is not None):
                row["blocking_UUID_inventory"] = gap_survey(
                    board, parts[src_part], parts[dst_part],
                    target_net=EN)
            report["expanded_BCu_windows"].append(row)
            if same:
                report["west_to_east_BCu_connected"] = True
                bcuregion = alternative
                break
    if not (report["source_FCu_connected"] and
            report["west_to_east_BCu_connected"]):
        # Diagnostic ONLY: ablate the three UUID-identified Block-1 tracks
        # on this disposable PCB instance, inspect connectivity, and put
        # the exact same original PCB_TRACK objects back on EVERY exit.
        # Block-1 CH000 and CH013 originals remain production-immutable.
        if not virtual_block1_cut_audit:
            report["status"] = "reused_west_component_path_missing"
            report["virtual_Block1_copper_cuts"] = []
            report["all_original_Block1_immutability_enforced"] = True
            return report
        from itertools import combinations
        from probe_ch025_fcu_l3_exact import track_inventory
        immutable_candidates = {
            "5b448238-a106-4c62-b852-f8d8a6eb1a91": "CH000_P_MUX",
            "8419cda3-2d4e-40b5-930b-6d9e9cc754a9": "CH000_P_MUX",
            "1570f16b-6e01-4e4d-9ec1-45cdfae30b58": "CH013_N_MUX",
        }
        by_uuid = {track.m_Uuid.AsString(): track
                   for track in board.GetTracks()}
        original_inventory = track_inventory(board)
        matched: list[Any] = []
        for uid, name in immutable_candidates.items():
            track = by_uuid.get(uid)
            if (track is None or track.GetNetname() != name
                    or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
                    or track.GetLayer() != pcbnew.B_Cu):
                raise RuntimeError(
                    "Protected Block-1 original copper identity changed")
            matched.append(track)
        report["virtual_Block1_copper_cuts"] = []
        domain_global = routing_domain(board, .075, .25)
        region_global = domain_global.intersection(
            box(11.0, 12.0, 68.0, 74.0))
        for count in range(1, len(matched) + 1):
            for indices in combinations(range(len(matched)), count):
                temporary = [matched[i] for i in indices]
                row: dict[str, Any] = {
                    "virtually_absent_UUIDs": [
                        t.m_Uuid.AsString() for t in temporary],
                    "immutable_Block1_tracks_relocated": False,
                    "all_original_tracks_restored": False,
                    "DRC_qualified": False,
                    "power_L3_qualified": False,
                    "checkpoint_accepted": False,
                    "production_copper_modification_allowed": False,
                }
                for track in temporary:
                    board.Remove(track)
                try:
                    foreign, _ = obstacles(
                        board, en_code, .15, .15, region_global, .65,
                        (pcbnew.B_Cu, pcbnew.F_Cu))
                    free_global = region_global.difference(
                        foreign[0]).buffer(-.000005)
                    row["BCu_connected_if_original_tracks_absent"] = connected(
                        free_global, existing_west, target_east)
                finally:
                    for track in temporary:
                        board.Add(track)
                    row["all_original_tracks_restored"] = (
                        track_inventory(board) == original_inventory)
                    if not row["all_original_tracks_restored"]:
                        raise RuntimeError(
                            "Immutable Block-1 scratch replay restoration failed")
                report["virtual_Block1_copper_cuts"].append(row)
        report["Block1_CH000_CH013_tracks_must_remain_immutable"] = True
        report["status"] = "reused_west_component_path_missing"
        return report
    fcu = mesh_route(
        board, source, existing_west, en_code,
        (pcbnew.F_Cu, pcbnew.B_Cu), power, fcuregion,
        start_layer=0, goal_layer=0, allow_vias=False,
        extra_obstacles=[power_fcu_obstacles(board), GeometryCollection()])
    bcu = mesh_route(
        board, existing_west, target_east, en_code,
        (pcbnew.B_Cu, pcbnew.F_Cu), power, bcuregion,
        start_layer=0, goal_layer=0, allow_vias=False)
    for name, data, a, b in (
            ("F_Cu_source_path", fcu, source, existing_west),
            ("B_Cu_middle_path", bcu, existing_west, target_east)):
        if (data is not None and len(data) >= 2
                and data[0] == (0, *a) and data[-1] == (0, *b)
                and all(p[0] == 0 for p in data)):
            report[name] = [list(p[1:]) for p in data]
    report["new_west_via_required"] = False
    report["status"] = (
        "reused_west_two_leg_mesh_found_unqualified"
        if report["F_Cu_source_path"] and report["B_Cu_middle_path"]
        else "reused_west_mesh_missing")
    return report



def survey_native_exact_west_mesh(board: Any, power: Any,
                                  ) -> dict[str, Any]:
    """Screen only west-via locations already proven L3-neutral individually.

    Both MUX_S2 and MUX_S3 are reserved as fixed straight F.Cu guard traces.
    Route proposals are read-only and NOT a coupled-L3 or native DRC proof.
    """
    import pcbnew
    from shapely.geometry import GeometryCollection, LineString, Point, box
    from shapely.ops import unary_union
    from escape_mesh_505 import mesh_route, polygons
    from probe_ch025_fcu_l3_exact import power_fcu_obstacles
    from probe_mux_topological_capacity import TERMINALS
    from route_targeted_closure import obstacles, routing_domain

    candidates = (
        (28.5, 35.5), (32.25, 35.5),
        (28.5, 35.25), (28.5, 35.0),
        (28.5, 34.75), (28.5, 34.5),
        (28.5, 34.25), (28.5, 34.0), (28.5, 33.75),
    )
    code = board.FindNet(EN).GetNetCode()
    domain = routing_domain(board, .325, .25)
    fregion = domain.intersection(box(19.0, 29.0, 52.0, 49.0))
    bregion = domain.intersection(box(19.0, 22.0, 55.0, 56.0))
    fobs, _ = obstacles(
        board, code, .15, .15, fregion, .65,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    bobs, _ = obstacles(
        board, code, .15, .15, bregion, .65,
        (pcbnew.B_Cu, pcbnew.F_Cu))
    powerfcu = power_fcu_obstacles(board)
    controls = unary_union([
        LineString(TERMINALS[name]).buffer(.075 + .15 + .00001)
        for name in ("MUX_S2", "MUX_S3")
    ])
    fblock = unary_union([fobs[0], powerfcu, controls])
    ffree = fregion.difference(fblock).buffer(-.000005)
    bfree = bregion.difference(bobs[0]).buffer(-.000005)
    fparts = polygons(ffree)
    bparts = polygons(bfree)

    def same_component(parts: list[Any], a: tuple[float, float],
                       b: tuple[float, float]) -> bool:
        return any(p.covers(Point(a)) and p.covers(Point(b))
                   for p in parts)

    source = L1_SOURCE[0]
    east = EAST
    target = L1_TARGET[-1]
    target_ok = same_component(fparts, east, target)
    items: list[dict[str, Any]] = []
    for west in candidates:
        fcusrc = same_component(fparts, source, west)
        bcu = same_component(bparts, west, east)
        items.append({
            "west_via_xy_mm": list(west),
            "source_FCu_connected_with_S2_S3_reserved": fcusrc,
            "middle_BCu_connected": bcu,
            "east_FCu_target_connected_with_S2_S3_reserved": target_ok,
            "three_layers_topologically_available": (
                fcusrc and bcu and target_ok),
            "individual_native_L3_loss_gain_exactly_zero": True,
            "combined_two_via_L3_gate_qualified": False,
            "native_DRC_qualified": False,
            "CH019_restitution_qualified": False,
        })
    report: dict[str, Any] = {
        "status": "native_exact_west_via_pair_geometry_only",
        "candidates": items,
        "joint_topological_candidates": sum(
            1 for item in items
            if item["three_layers_topologically_available"]),
        "S2_S3_reserved_unchanged": True,
        "new_west_vias_created": False,
        "F_Cu_and_B_Cu_paths": None,
        "acceptance_allowed": False,
        "fabrication_release": False,
    }
    first = next((item for item in items
                  if item["three_layers_topologically_available"]), None)
    if first is None:
        return report
    west = tuple(first["west_via_xy_mm"])
    guard_f = unary_union([powerfcu, controls])
    proposed = []
    for name, a, b, layers, region, guards in (
            ("source_FCu", source, west,
             (pcbnew.F_Cu, pcbnew.B_Cu), fregion,
             [guard_f, GeometryCollection()]),
            ("middle_BCu", west, east,
             (pcbnew.B_Cu, pcbnew.F_Cu), bregion,
             [GeometryCollection(), guard_f]),
            ("target_FCu", east, target,
             (pcbnew.F_Cu, pcbnew.B_Cu), fregion,
             [guard_f, GeometryCollection()])):
        route = mesh_route(
            board, a, b, code, layers, power, region,
            start_layer=0, goal_layer=0, allow_vias=False,
            extra_obstacles=guards)
        correct = (route is not None and len(route) >= 2
                   and route[0] == (0, *a)
                   and route[-1] == (0, *b)
                   and all(point[0] == 0 for point in route))
        proposed.append({
            "segment": name, "mesh_path_found": correct,
            "vertices": [list(p) for p in route] if correct else None,
        })
    report["F_Cu_and_B_Cu_paths"] = proposed
    report["status"] = (
        "all_three_mesh_segments_proposed_not_native_qualified"
        if all(p["mesh_path_found"] for p in proposed)
        else "at_least_one_mesh_segment_missing")
    return report



def survey_exact_west_bcu_uuid_barrier(board: Any) -> dict[str, Any]:
    """Native-geometry UUID matrix; no original Block-1 copper can be moved.

    The clearance-expanded Shapely model is a diagnostic, not a replacement
    for KiCad's native DRC. Virtual Block-2 track cuts are ALWAYS restored.
    """
    import re
    from itertools import combinations
    import pcbnew
    from shapely.geometry import Point, box
    from escape_mesh_505 import polygons
    from analyze_ch025_bcu_cut_uuids import survey as gap_survey
    from route_targeted_closure import obstacles, routing_domain
    from probe_ch025_fcu_l3_exact import track_inventory

    west_sites = (
        (28.5, 35.5), (32.25, 35.5), (28.5, 35.25),
        (28.5, 35.0), (28.5, 34.75), (28.5, 34.5),
        (28.5, 34.25), (28.5, 34.0), (28.5, 33.75),
    )
    region = routing_domain(board, .325, .25).intersection(
        box(19.0, 22.0, 55.0, 56.0))
    en_code = board.FindNet(EN).GetNetCode()
    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    protected_names = (
        "VCM", "AGND", "3V3", "GND", "VCC", "VDD", "VREG",
        "CH017_N", "CH019_P", "CH021_P", "CH024_P", "CH026_P",
    )

    def classify(obj: dict[str, Any]) -> str:
        net = obj["net"]
        if obj["kind"] != "track":
            return "protected_original_via_or_pad_or_arc"
        m = re.match(r"^CH(\d{3})_", net)
        if m is not None and int(m.group(1)) < 16:
            return "protected_block_1"
        if net.startswith(protected_names):
            return "protected_original_net"
        if m is not None and 16 <= int(m.group(1)) <= 31:
            if net.endswith("_MUX"):
                return "conditional_block_2_track_needs_restitution"
        return "protected_unreviewed_or_other_original"

    def components() -> list[Any]:
        walls, _ = obstacles(
            board, en_code, .15, .15, region, .65,
            (pcbnew.B_Cu, pcbnew.F_Cu))
        return polygons(region.difference(walls[0]).buffer(-.000005))

    def index(parts: list[Any], point: tuple[float, float]
              ) -> int | None:
        p = Point(point)
        return next((i for i, part in enumerate(parts)
                     if part.covers(p)), None)

    parts = components()
    target_idx = index(parts, EAST)
    rows: list[dict[str, Any]] = []
    all_objects: dict[str, dict[str, Any]] = {}
    for west in west_sites:
        source_idx = index(parts, west)
        row: dict[str, Any] = {
            "west_xy_mm": list(west),
            "east_xy_mm": list(EAST),
            "west_component": source_idx, "east_component": target_idx,
            "same_BCu_component": (
                source_idx is not None and source_idx == target_idx),
            "native_DRC_qualified": False,
        }
        if (source_idx is not None and target_idx is not None
                and source_idx != target_idx):
            gap = gap_survey(
                board, parts[source_idx], parts[target_idx],
                target_net=EN)
            row["nearest_component_gap"] = gap["BCu_gap"]
            row["not_global_minimum_cut_proof"] = True
            for obj in gap["nearby_objects"]:
                obj = {**obj, "engineering_classification": classify(obj),
                       "clearance_model_only_not_native_DRC": True}
                all_objects.setdefault(obj["uuid"], obj)
            row["near_gap_UUIDs"] = [
                obj["uuid"] for obj in gap["nearby_objects"][:30]]
        rows.append(row)
    matrix = sorted(all_objects.values(), key=lambda x: (
        x["distance_to_cut_mm"], x["net"], x["uuid"]))
    movable = [obj for obj in matrix
               if obj["engineering_classification"] ==
               "conditional_block_2_track_needs_restitution"
               and obj["uuid"] in tracks
               and tracks[obj["uuid"]].GetLayer() == pcbnew.B_Cu
               and not isinstance(
                   tracks[obj["uuid"]], (pcbnew.PCB_VIA, pcbnew.PCB_ARC))]
    # The three closest candidate UUIDs are only screened, never routed or
    # retained. This test does NOT grant permission to move their originals.
    selected = movable[:3]
    before = track_inventory(board)
    trials: list[dict[str, Any]] = []
    for count in range(1, min(2, len(selected)) + 1):
        for subset in combinations(selected, count):
            selected_tracks = [tracks[obj["uuid"]] for obj in subset]
            row = {
                "virtual_cut_UUIDs": [
                    t.m_Uuid.AsString() for t in selected_tracks],
                "affected_nets": sorted(
                    {t.GetNetname() for t in selected_tracks}),
                "protected_block_1_moved": False,
                "copper_writes_to_source": False,
                "native_DRC_qualified": False,
                "all_original_tracks_restored": False,
            }
            try:
                for item in selected_tracks:
                    board.Remove(item)
                trial_parts = components()
                east_component = index(trial_parts, EAST)
                row["connected_west_sites_mm"] = [
                    list(west) for west in west_sites
                    if east_component is not None
                    and index(trial_parts, west) == east_component]
                row["BCu_connection_opened"] = bool(
                    row["connected_west_sites_mm"])
            finally:
                for item in selected_tracks:
                    board.Add(item)
                if track_inventory(board) != before:
                    raise RuntimeError(
                        "Block-2 virtual cut failed exact original restitution")
                row["all_original_tracks_restored"] = True
            trials.append(row)
    if track_inventory(board) != before:
        raise RuntimeError("Original B.Cu track inventory changed")
    return {
        "status": "read_only_BCu_UUID_matrix_and_reversible_probes",
        "window_bounds_mm": list(region.bounds),
        "west_site_count": len(west_sites),
        "east_site_xy_mm": list(EAST),
        "BCu_free_components": len(parts),
        "nine_west_site_matrix": rows,
        "nearest_cut_UUID_matrix": matrix[:80],
        "objects_beyond_first_80": max(0, len(matrix) - 80),
        "conditional_block_2_UUIDs": [x["uuid"] for x in movable],
        "protected_original_UUIDs": [
            x["uuid"] for x in matrix if x["engineering_classification"]
            != "conditional_block_2_track_needs_restitution"],
        "reversible_Block_2_cuts": trials,
        "Block_1_and_VCM_unchanged": True,
        "original_tracks_exactly_restored": True,
        "no_In1_Cu_used": True,
        "no_original_vias_or_pads_changed": True,
        "native_DRC_qualified": False,
        "L3_combined_exact_zero_qualified": False,
        "accepted": False,
        "fabrication_release": False,
        "routing_completed": False,
        "note": "A nearest polygon gap is not a certified global minimum cut",
    }

def qualify(archive: Path) -> dict[str, Any]:
    """Diagnostic only: do not return an accepted PCB or manufacture."""
    import pcbnew
    out: dict[str, Any] = {
        **FLAGS, "status": "not_started", "baseline_airwires": 139,
        "target_airwires": 136, "source_archive_sha256": ARCHIVE_SHA256,
        "source_pcb_sha256": BOARD_SHA256, "native_DRC_qualified": False,
        "native_136_airwires_qualified": False,
        "native_L3_exact_qualified": False,
        "L3_loss_native_mm2": None, "L3_gain_native_mm2": None,
        "protected_original_items_unchanged": False,
        "CH027_original_via_unchanged": False,
        "new_vias_added_scratch_only": False,
        "In1_Cu_tracks_added": False, "board_checkpoint_saved": False,
        "CH019_original_track_removed_on_scratch": False,
        "CH019_original_track_restituted": False,
        "source_board_unmodified": False,
        "candidate_geometry": approved_geometry(),
        "CH019_restitution_geometry": None,
        "F_Cu_source_optimization": None,
        "CH019_BCu_reconnected_scratch": False,
        "L3_loss_contours": [], "L3_gain_contours": [],
        "L3_phase_deltas": [],
        "L3_west_via_position_probes": [],
        "existing_west_via_geometry": None,
        "secondary_existing_west_via_geometry": None,
        "native_exact_west_via_mesh_geometry": None,
        "native_exact_west_bcu_uuid_barrier": None,
        "native_west_via_alternate_positions": [],
        "L3_unchanged_baseline_repeat": None,
        "L3_exact_native_polygon_ring_identity": False,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("Wrong 139 source archive hash")
    with tempfile.TemporaryDirectory(prefix="mux-en-scratch-native-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as contents:
            if sorted(contents.namelist()) != sorted(MEMBERS):
                raise RuntimeError("Wrong ZIP members")
            for member in MEMBERS:
                (root / member).write_bytes(contents.read(member))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != BOARD_SHA256:
            raise RuntimeError("Wrong pinned source PCB hash")
        initial = native(pcb_path, root / "baseline-drc.json")
        out["baseline_native_metrics"] = metrics(initial)
        if metrics(initial) != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "native_baseline_not_clean"
            return out
        board = pcbnew.LoadBoard(str(pcb_path))
        existing = track_inventory(board)
        originals, zone, _ = pinned_items(board)
        before_fingerprint = unchanged_fingerprints(board)
        netcode = board.FindNet(EN).GetNetCode()
        if originals[EN].GetNetname() != EN:
            raise RuntimeError("Pinned MUX_EN copper net mismatch")
        old_en_start = xy(originals[EN].GetStart())
        old_en_end = xy(originals[EN].GetEnd())
        if sorted((old_en_start, old_en_end)) != sorted(
                (L1_SOURCE[0], L1_TARGET[-1])):
            raise RuntimeError("Pinned MUX_EN terminal mismatch")
        tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        ch019 = tracks.get(TEMP_CUT)
        if (ch019 is None or ch019.GetNetname() != CH019
                or ch019.GetLayer() != pcbnew.B_Cu
                or isinstance(ch019, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise RuntimeError("Pinned CH019 cut identity mismatch")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        before_zone = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        if not before_zone.OutlineCount():
            raise RuntimeError("Native baseline L3 fill empty")
        base_signature = native_polygon_ring_digest(before_zone)
        # A same-board, same-copper control quantifies native KiCad
        # refill/BooleanSubtract instability before changing any track.
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        repeat_zone = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        repeat_diff = exact_native_difference(before_zone, repeat_zone)
        repeat_signature = native_polygon_ring_digest(repeat_zone)
        out["L3_unchanged_baseline_repeat"] = {
            "loss_native_mm2": repeat_diff["loss_native_mm2"],
            "gain_native_mm2": repeat_diff["gain_native_mm2"],
            "loss_native_outlines": repeat_diff["loss_native_outlines"],
            "gain_native_outlines": repeat_diff["gain_native_outlines"],
            "native_polygon_ring_equal": (
                base_signature == repeat_signature),
            "before_signature": base_signature,
            "repeat_signature": repeat_signature,
        }
        def record_phase(label: str) -> None:
            # Deliberately fill every staged scratch state, but never save
            # an intermediate PCB or treat its DRC as a qualified route.
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            filled = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            difference = exact_native_difference(before_zone, filled)
            signature = native_polygon_ring_digest(filled)
            out["L3_phase_deltas"].append({
                "stage": label,
                "loss_mm2": difference["loss_native_mm2"],
                "gain_mm2": difference["gain_native_mm2"],
                "loss_outlines": difference["loss_native_outlines"],
                "gain_outlines": difference["gain_native_outlines"],
                "same_exact_native_rings_as_original": (
                    signature == base_signature),
                "native_3V3A_filled": True,
                "approved": False,
            })

        board.Remove(originals[EN])
        board.Remove(ch019)
        out["CH019_original_track_removed_on_scratch"] = True
        record_phase("removed_original_MUX_EN_and_CH019_only")
        # All positions were identified by the read-only native F.Cu/B.Cu
        # via-window screen. These probes check L3 polygon parity ONLY.
        # They do not constitute routed or DRC-qualified west-via sites.
        west_locations = (
            (29.75, 38.5), (29.75, 38.75),
            (28.5, 35.5), (32.25, 35.5),
            (28.5, 35.25), (28.5, 35.0),
            (28.5, 34.75), (28.5, 34.5),
            (28.5, 34.25), (28.5, 34.0),
            (28.5, 33.75),
        )
        for location in west_locations:
            original_via_ids = {
                t.m_Uuid.AsString() for t in board.GetTracks()
                if isinstance(t, pcbnew.PCB_VIA)
            }
            make_via(board, location, netcode, .65)
            placed = [t for t in board.GetTracks()
                      if isinstance(t, pcbnew.PCB_VIA)
                      and t.m_Uuid.AsString() not in original_via_ids]
            if (len(placed) != 1
                    or xy(placed[0].GetPosition()) != location
                    or placed[0].GetNetname() != EN):
                raise RuntimeError("Scratch west-via trial not isolated")
            try:
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                tested = pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
                diff = exact_native_difference(before_zone, tested)
                out["native_west_via_alternate_positions"].append({
                    "xy_mm": list(location),
                    "native_L3_loss_mm2": diff["loss_native_mm2"],
                    "native_L3_gain_mm2": diff["gain_native_mm2"],
                    "both_exactly_zero": diff["native_both_empty"],
                    "native_ring_identity": (
                        native_polygon_ring_digest(tested) ==
                        base_signature),
                    "no_original_net_moved": True,
                    "route_formed": False,
                    "native_DRC_qualified": False,
                    "accepted": False,
                    "fabrication_release": False,
                })
            finally:
                board.Remove(placed[0])
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                recovered = pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
                if not exact_native_difference(
                        before_zone, recovered)["native_both_empty"]:
                    raise RuntimeError("Native L3 west trial rollback not exact")
                if any(t.m_Uuid.AsString() not in original_via_ids
                       for t in board.GetTracks()
                       if isinstance(t, pcbnew.PCB_VIA)):
                    raise RuntimeError("Scratch west trial left a new via")
        from analyze_ch025_l3_native_refill import filled
        out["existing_west_via_geometry"] = survey_reused_west_via(
            board, filled(zone))
        out["secondary_existing_west_via_geometry"] = (
            survey_reused_west_via(
                board, filled(zone),
                existing_west=(23.1106, 50.456),
                via_uuid="d7c677dd-0d10-488d-b622-e47c674608f2",
                virtual_block1_cut_audit=False))
        out["native_exact_west_via_mesh_geometry"] = (
            survey_native_exact_west_mesh(board, filled(zone)))
        out["native_exact_west_bcu_uuid_barrier"] = (
            survey_exact_west_bcu_uuid_barrier(board))
        source_path, source_optim = optimize_fcu_source(
            board, netcode, L1_SOURCE)
        out["F_Cu_source_optimization"] = source_optim
        for segment, layer in (
                (source_path, pcbnew.F_Cu),
                (L4_MIDDLE, pcbnew.B_Cu),
                (L1_TARGET, pcbnew.F_Cu)):
            for start, end in zip(segment, segment[1:]):
                make_track(board, start, end, netcode, .15, layer)
        record_phase("new_MUX_EN_tracks_without_new_vias")
        # Test EAST alone: this does not connect the WEST track endpoint.
        # It is strictly an in-memory zone-fill diagnostic.
        make_via(board, EAST, netcode, .65)
        record_phase("new_MUX_EN_tracks_with_east_via_only")
        east_matches = [
            t for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)
            and t.GetNetCode() == netcode
            and xy(t.GetPosition()) == EAST
        ]
        if len(east_matches) != 1:
            raise RuntimeError("Temporary east EN via not unique")
        board.Remove(east_matches[0])
        record_phase("east_via_only_removed_and_native_refilled")
        make_via(board, WEST, netcode, .65)
        record_phase("new_MUX_EN_tracks_with_west_via_only")
        # Each offset is purely a temporary L3 refill probe; the connected
        # signal-track endpoints deliberately stay at the original WEST.
        # Therefore these offsets are NOT DRC-qualified routing candidates.
        from route_targeted_closure import vector
        west_matches = [
            t for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)
            and t.GetNetCode() == netcode
            and xy(t.GetPosition()) == WEST
        ]
        if len(west_matches) != 1:
            raise RuntimeError("New west EN via not uniquely identifiable")
        west_via = west_matches[0]
        offsets = (
            (-.001, 0.0), (.001, 0.0),
            (0.0, -.001), (0.0, .001),
            (-.005, 0.0), (.005, 0.0),
            (0.0, -.005), (0.0, .005),
        )
        try:
            for dx, dy in offsets:
                position = (round(WEST[0] + dx, 6),
                            round(WEST[1] + dy, 6))
                west_via.SetPosition(vector(position))
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                poly = pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
                delta = exact_native_difference(before_zone, poly)
                out["L3_west_via_position_probes"].append({
                    "offset_mm": [dx, dy],
                    "position_mm": list(position),
                    "loss_mm2": delta["loss_native_mm2"],
                    "gain_mm2": delta["gain_native_mm2"],
                    "native_both_empty": delta["native_both_empty"],
                    "exact_native_rings_equal": (
                        native_polygon_ring_digest(poly) == base_signature),
                    "signal_tracks_reconnected": False,
                    "native_DRC_qualified": False,
                })
        finally:
            west_via.SetPosition(vector(WEST))
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            if xy(west_via.GetPosition()) != WEST:
                raise RuntimeError("West via position rollback failed")
        make_via(board, EAST, netcode, .65)
        out["new_vias_added_scratch_only"] = True
        record_phase("new_MUX_EN_tracks_with_both_vias_without_CH019")
        from analyze_ch025_l3_native_refill import filled
        restore = propose_ch019_bcu_restitution(
            board, xy(ch019.GetStart()), xy(ch019.GetEnd()),
            filled(zone))
        out["CH019_restitution_geometry"] = restore
        if restore["path_found"]:
            restore_code = board.FindNet(CH019).GetNetCode()
            coordinates = [tuple(p) for p in restore["path"]]
            for start, end in zip(coordinates, coordinates[1:]):
                make_track(board, start, end, restore_code, .15,
                           pcbnew.B_Cu)
            out["CH019_BCu_reconnected_scratch"] = True
        record_phase("CH019_restitution_after_MUX_EN_via_hop")
        after = track_inventory(board)
        for uid, item in existing.items():
            if uid not in {
                    originals[EN].m_Uuid.AsString(), TEMP_CUT,
            } and after.get(uid) != item:
                raise RuntimeError("Protected original copper UUID changed")
        current_fingerprint = unchanged_fingerprints(board)
        current_original_vias = {
            value[0]: value for value in current_fingerprint["vias"]}
        if any(current_original_vias.get(row[0]) != row
               for row in before_fingerprint["vias"]):
            raise RuntimeError("Existing via geometry altered")
        if (current_fingerprint["pads"] != before_fingerprint["pads"]
                or current_fingerprint["zones"] != before_fingerprint["zones"]):
            raise RuntimeError("Protected pad or zone altered")
        out["protected_original_items_unchanged"] = True
        out["CH027_original_via_unchanged"] = any(
            row[0] == CH027_ALT_VIA for row in before_fingerprint["vias"])
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        after_zone = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        delta = exact_native_difference(before_zone, after_zone)
        out["L3_loss_native_mm2"] = delta["loss_native_mm2"]
        out["L3_gain_native_mm2"] = delta["gain_native_mm2"]
        out["L3_loss_native_outlines"] = delta["loss_native_outlines"]
        out["L3_gain_native_outlines"] = delta["gain_native_outlines"]
        out["L3_loss_contours"] = polygon_contours(
            delta["loss_polyset"], (WEST, EAST))
        out["L3_gain_contours"] = polygon_contours(
            delta["gain_polyset"], (WEST, EAST))
        out["L3_delta_near_vias_only"] = all(
            min(d["distance_to_west_via_mm"],
                d["distance_to_east_via_mm"]) < 1.0
            for d in out["L3_loss_contours"] + out["L3_gain_contours"])
        out["native_L3_exact_qualified"] = delta["native_both_empty"]
        candidate_signature = native_polygon_ring_digest(after_zone)
        out["L3_exact_native_polygon_ring_identity"] = (
            candidate_signature == base_signature)
        out["L3_candidate_ring_signature"] = candidate_signature
        pcbnew.SaveBoard(str(pcb_path), board)
        # The original project .kicad_pro snapshot is preserved by native().
        post = native(pcb_path, root / "candidate-drc.json")
        out["candidate_native_metrics"] = metrics(post)
        out["candidate_native_violations"] = [
            {"type": v.get("type"), "severity": v.get("severity"),
             "description": v.get("description"),
             "items": v.get("items", [])[:8]}
            for v in post.get("violations", [])[:16]
        ]
        out["CH019_unconnected_samples"] = [
            v for v in post.get("unconnected_items", [])
            if "CH019_N_MUX" in json.dumps(v)
        ][:8]
        from native_connectivity import regressed_nets
        out["regressed_nets"] = regressed_nets(initial, post)
        out["native_DRC_qualified"] = (
            metrics(post)["violations"] == 0
            and metrics(post)["warnings"] == 0)
        out["native_136_airwires_qualified"] = (
            metrics(post)["unconnected"] == 136
            and not out["regressed_nets"])
        out["source_board_unmodified"] = (
            hashlib.sha256(archive.read_bytes()).hexdigest() ==
            ARCHIVE_SHA256)
        # A non-restituted CH019 cut makes a checkpoint promotion illegal
        # regardless of DRC, 136-airwire count or L3 status.
        out["status"] = (
            "scratch_MUX_EN_CH019_joint_native_unqualified"
            if out["CH019_BCu_reconnected_scratch"] else
            "scratch_MUX_EN_hop_CH019_BCu_not_reconnected")
        out["CH019_BCu_native_DRC_clean"] = (
            out["CH019_BCu_reconnected_scratch"]
            and "CH019_N_MUX" not in out["regressed_nets"]
            and not out["CH019_unconnected_samples"]
            and out["native_DRC_qualified"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "baseline": result["baseline_airwires"],
        "trial_drc": result.get("candidate_native_metrics"),
        "L3_loss": result["L3_loss_native_mm2"],
        "L3_gain": result["L3_gain_native_mm2"],
        "accepted": False, "fabrication_release": False,
    }))


if __name__ == "__main__":
    main()

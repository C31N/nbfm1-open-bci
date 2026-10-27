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

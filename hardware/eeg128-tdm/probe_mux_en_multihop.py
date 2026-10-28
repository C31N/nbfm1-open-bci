#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed native topology survey for MUX_EN BCu -> FCu -> BCu bridge.

Read-only original source. In-memory copy removes ONLY the reviewed EN and
CH019 scratch tracks, restoring exact UUID inventories on every exit.
A free-space connection is never a native-DRC or manufacturing approval.
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
from probe_ch025_cooperative8 import pinned_items, unchanged_fingerprints
from probe_ch025_fcu_l3_exact import track_inventory, power_fcu_obstacles
from analyze_ch025_l3_precision_mask import exact_native_difference
from route_targeted_closure import (
    obstacles, routing_domain, make_via,
)
from probe_mux_topological_capacity import TERMINALS

WEST = (28.5, 33.75)
EAST = (36.75, 34.0)
CUT = "0832ca70-347c-5b2d-b8d9-c8fff7096f8a"
EN = "MUX_EN"
FLAGS = {
    "accepted": False,
    "routing_completed": False,
    "fabrication_release": False,
    "manufacturing_files": False,
    "checkpoint_promoted": False,
    "native_DRC_qualified": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
    "In1_Cu_used": False,
}


def grid_candidates(board: Any, *, bounds: tuple[float, float, float, float] = (25.0, 28.5, 44.0, 43.0), sample_step: float = .25) -> dict[str, Any]:
    """Build two native BCu components and their shared reachable FCu island."""
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from shapely.ops import unary_union
    from shapely.prepared import prep
    from escape_mesh_505 import polygons

    en = board.FindNet(EN).GetNetCode()
    area = routing_domain(board, .325, .25).intersection(
        box(*bounds))
    layers = (pcbnew.F_Cu, pcbnew.B_Cu)
    trace_walls, via_obstacles = obstacles(
        board, en, .15, .15, area, .65, layers)
    power_fcu = power_fcu_obstacles(board)
    s2s3 = unary_union([
        LineString(TERMINALS[name]).buffer(.075 + .15 + .00001)
        for name in ("MUX_S2", "MUX_S3")
    ])
    # Existing traces require 0.15-mm signals + 0.15-mm spacing.
    # Through-via 0.65-mm copper requires an ADDITIONAL 0.25-mm
    # centreline offset relative to a 0.15-mm trace.
    free_fcu = area.difference(unary_union([
        trace_walls[0], s2s3, power_fcu])).buffer(-.000005)
    free_bcu = area.difference(trace_walls[1]).buffer(-.000005)
    fcu_parts = polygons(free_fcu)
    bcu_parts = polygons(free_bcu)

    def identify(parts: list[Any], point: tuple[float, float]
                 ) -> int | None:
        p = Point(point)
        return next((i for i, poly in enumerate(parts)
                     if poly.covers(p)), None)

    source_bcu = identify(bcu_parts, WEST)
    target_bcu = identify(bcu_parts, EAST)
    out: dict[str, Any] = {
        "search_area_bounds_mm": list(area.bounds),
        "west_xy_mm": list(WEST), "east_xy_mm": list(EAST),
        "sample_step_mm": sample_step,
        "fcu_free_components": len(fcu_parts),
        "bcu_free_components": len(bcu_parts),
        "west_bcu_component": source_bcu,
        "east_bcu_component": target_bcu,
        "S2_S3_strict_FCu_copper_reserved": True,
        "VCM_Block1_all_original_unchanged": True,
        "candidate_via_pairs": [],
        "candidate_pair_count_before_cap": 0,
        "mutual_FCu_BCu_via_sites_west": 0,
        "mutual_FCu_BCu_via_sites_east": 0,
        "geometric_multihop_possible": False,
        "native_DRC_qualified": False,
        "combined_L3_exact_gate_qualified": False,
        "notes": "Conservative 0.65mm via footprint, no In1.Cu",
    }
    if source_bcu is None or target_bcu is None:
        out["status"] = "original_west_or_east_absent_from_BCu_free_space"
        return out

    # A valid through-hole needs simultaneously available BCu and FCu,
    # no foreign via/pad collision, and at least 0.505mm spacing from
    # power copper on FCu. L3 exact native fill is checked separately.
    all_new_via_free = free_fcu.buffer(-.25).intersection(
        free_bcu.buffer(-.25)).difference(
            unary_union([
                via_obstacles,
                power_fcu.buffer(.25),
                s2s3.buffer(.25),
            ])).buffer(-.000005)
    allowed = prep(all_new_via_free)
    per_fcu: dict[int, dict[str, list[tuple[float, float]]]] = {}
    count = 0
    for iy in range(int((bounds[3] - bounds[1]) / sample_step)):
        y = round(bounds[1] + sample_step / 2 + iy * sample_step, 6)
        for ix in range(int((bounds[2] - bounds[0]) / sample_step)):
            x = round(bounds[0] + sample_step / 2 + ix * sample_step, 6)
            point = (x, y)
            if not allowed.covers(Point(point)):
                continue
            f_index = identify(fcu_parts, point)
            b_index = identify(bcu_parts, point)
            if f_index is None or b_index not in (source_bcu, target_bcu):
                continue
            if b_index == source_bcu and math.dist(point, WEST) < .9:
                continue
            if b_index == target_bcu and math.dist(point, EAST) < .9:
                continue
            which = "west" if b_index == source_bcu else "east"
            per_fcu.setdefault(f_index, {"west": [], "east": []}
                               )[which].append(point)
            count += 1
    out["sampled_legal_FCu_BCu_via_centres"] = count
    out["mutual_FCu_BCu_via_sites_west"] = sum(
        len(x["west"]) for x in per_fcu.values())
    out["mutual_FCu_BCu_via_sites_east"] = sum(
        len(x["east"]) for x in per_fcu.values())
    shared = [k for k, v in per_fcu.items()
              if v["west"] and v["east"]]
    out["common_FCu_component_ids"] = shared
    candidates: list[dict[str, Any]] = []
    for f_index in shared:
        west_sites = sorted(per_fcu[f_index]["west"],
                            key=lambda p: math.dist(p, WEST))[:30]
        east_sites = sorted(per_fcu[f_index]["east"],
                            key=lambda p: math.dist(p, EAST))[:30]
        for wa in west_sites:
            for eb in east_sites:
                if math.dist(wa, eb) < .8:
                    continue
                score = (math.dist(WEST, wa) + math.dist(wa, eb)
                         + math.dist(eb, EAST))
                candidates.append({
                    "via_1_xy_mm": list(wa),
                    "via_2_xy_mm": list(eb),
                    "shared_FCu_free_component": f_index,
                    "west_BCu_component": source_bcu,
                    "east_BCu_component": target_bcu,
                    "straight_line_lower_bound_mm": round(score, 6),
                    "L3_individual_vias_qualified": False,
                    "L3_combined_gate_qualified": False,
                    "all_three_copper_paths_DRC_qualified": False,
                })
    # Polygon-intersection search is independent of grid alignment: a
    # 0.5-mm raster can miss sub-millimetre via windows. Both landing
    # patches must share one truly connected FCu polygon.
    west_patch = all_new_via_free.intersection(bcu_parts[source_bcu])
    east_patch = all_new_via_free.intersection(bcu_parts[target_bcu])
    out["west_via_candidate_area_mm2"] = west_patch.area
    out["east_via_candidate_area_mm2"] = east_patch.area
    out["shared_FCu_components_from_exact_polygon_overlay"] = []
    out["shared_FCu_overlay_pair_diagnostics"] = []
    for f_index, component in enumerate(fcu_parts):
        w_patch = west_patch.intersection(component).buffer(-.005)
        e_patch = east_patch.intersection(component).buffer(-.005)
        if w_patch.area <= 1e-9 or e_patch.area <= 1e-9:
            continue
        out["shared_FCu_components_from_exact_polygon_overlay"].append(
            f_index)
        wpt, ept = w_patch.representative_point(), e_patch.representative_point()
        wa = (round(wpt.x, 6), round(wpt.y, 6))
        eb = (round(ept.x, 6), round(ept.y, 6))
        min_via_centre_distance = .80001
        result = {
            "fcu_component": f_index,
            "west_bridge_xy_mm": list(wa),
            "east_bridge_xy_mm": list(eb),
            "from_main_west_via_mm": math.dist(wa, WEST),
            "from_main_east_via_mm": math.dist(eb, EAST),
            "between_bridge_vias_mm": math.dist(wa, eb),
            "west_patch_area_mm2": w_patch.area,
            "east_patch_area_mm2": e_patch.area,
            "both_covers_legal_via_region": (
                allowed.covers(Point(wa)) and
                allowed.covers(Point(eb))),
        }
        out["shared_FCu_overlay_pair_diagnostics"].append(result)
        if (result["from_main_west_via_mm"] < min_via_centre_distance
                or result["from_main_east_via_mm"] <
                min_via_centre_distance
                or result["between_bridge_vias_mm"] <
                min_via_centre_distance
                or not result["both_covers_legal_via_region"]):
            continue
        if any(c["via_1_xy_mm"] == list(wa) and
               c["via_2_xy_mm"] == list(eb) for c in candidates):
            continue
        candidates.append({
            "via_1_xy_mm": list(wa),
            "via_2_xy_mm": list(eb),
            "shared_FCu_free_component": f_index,
            "west_BCu_component": source_bcu,
            "east_BCu_component": target_bcu,
            "straight_line_lower_bound_mm": round(
                math.dist(WEST, wa) + math.dist(wa, eb)
                + math.dist(eb, EAST), 6),
            "L3_individual_vias_qualified": False,
            "L3_combined_gate_qualified": False,
            "all_three_copper_paths_DRC_qualified": False,
            "found_by_exact_polygon_overlay": True,
            "survey_priority": 0,
        })
        # The representative B via is topologically valid, but its
        # native L3 refill may be nonzero. Search alternate B centres
        # throughout the SAME FCu polygon and east BCu component.
        x0, y0, x1, y1 = e_patch.bounds
        alternate_b: list[tuple[float, float]] = []
        interval = .25
        for ix in range(int(math.ceil((x1 - x0) / interval))):
            x = round(x0 + (ix + .5) * interval, 6)
            for iy in range(int(math.ceil((y1 - y0) / interval))):
                y = round(y0 + (iy + .5) * interval, 6)
                p = (x, y)
                if (math.dist(p, EAST) <= min_via_centre_distance
                        or math.dist(p, wa) <= min_via_centre_distance
                        or not e_patch.covers(Point(p))
                        or not allowed.covers(Point(p))):
                    continue
                alternate_b.append(p)
        alternate_b.sort(key=lambda p: (math.dist(p, EAST), p))
        result["number_of_alternative_B_sites_0p25mm"] = len(
            alternate_b)
        number = min(17, len(alternate_b))
        if number:
            indexes = sorted({
                int(round(rank * (len(alternate_b) - 1) /
                          max(1, number - 1))) for rank in range(number)
            })
            for priority, index in enumerate(indexes, start=1):
                alternate = alternate_b[index]
                if alternate == eb:
                    continue
                candidates.append({
                    "via_1_xy_mm": list(wa),
                    "via_2_xy_mm": list(alternate),
                    "shared_FCu_free_component": f_index,
                    "west_BCu_component": source_bcu,
                    "east_BCu_component": target_bcu,
                    "straight_line_lower_bound_mm": round(
                        math.dist(WEST, wa) + math.dist(wa, alternate)
                        + math.dist(alternate, EAST), 6),
                    "L3_individual_vias_qualified": False,
                    "L3_combined_gate_qualified": False,
                    "all_three_copper_paths_DRC_qualified": False,
                    "found_by_exact_polygon_overlay": True,
                    "alternative_inner_B_position": True,
                    "survey_priority": priority,
                })
    candidates.sort(key=lambda c: (
        c.get("survey_priority", 0),
        c["straight_line_lower_bound_mm"], c["via_1_xy_mm"],
        c["via_2_xy_mm"]))
    out["candidate_pair_count_before_cap"] = len(candidates)
    out["candidate_via_pairs"] = candidates[:20]
    out["geometric_multihop_possible"] = len(candidates) > 0
    out["status"] = (
        "native_polygon_FCu_bridge_candidates_unqualified"
        if candidates else "no_common_FCu_bridge_via_sites_in_tested_window")
    return out


def run(archive: Path) -> dict[str, Any]:
    import pcbnew

    output: dict[str, Any] = {
        **FLAGS, "status": "not_started",
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_pcb_sha256": BOARD_SHA256,
        "source_PCB_untouched": False,
        "original_track_inventory_restored": False,
        "protected_original_fingerprint_unchanged": False,
        "native_L3_control_exact_zero": False,
        "native_139_baseline_qualified": False,
        "new_vias_reversible": False,
        "topology": None, "local_topology": None,
        "global_window_used": False, "native_L3_pair_trials": [],
        "native_L3_individual_via_stage_trials": [],
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("KiCad 8.0.9 required")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("Pinned 139 archive mismatch")
    with tempfile.TemporaryDirectory(prefix="mux-en-multihop-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as z:
            if sorted(z.namelist()) != sorted(MEMBERS):
                raise RuntimeError("Unexpected source ZIP members")
            for member in MEMBERS:
                (root / member).write_bytes(z.read(member))
        board_path = root / MEMBERS[0]
        if hashlib.sha256(board_path.read_bytes()).hexdigest() != BOARD_SHA256:
            raise RuntimeError("Pinned board SHA changed")
        board = pcbnew.LoadBoard(str(board_path))
        originals, zone, _ = pinned_items(board)
        initial = track_inventory(board)
        fingerprint = unchanged_fingerprints(board)
        en = board.FindNet(EN).GetNetCode()
        original_en = originals[EN]
        ch019 = next((t for t in board.GetTracks()
                      if t.m_Uuid.AsString() == CUT
                      and t.GetNetname() == "CH019_N_MUX"
                      and t.GetLayer() == pcbnew.B_Cu), None)
        if ch019 is None:
            raise RuntimeError("Pinned CH019 reviewed cut not found")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        before_l3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        control = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        output["native_L3_control_exact_zero"] = (
            exact_native_difference(before_l3, control)["native_both_empty"])
        if not output["native_L3_control_exact_zero"]:
            raise RuntimeError("Native unchanged 3V3A refill drifted")
        board.Remove(original_en)
        board.Remove(ch019)
        try:
            output["local_topology"] = grid_candidates(board)
            output["topology"] = output["local_topology"]
            if not output["topology"]["geometric_multihop_possible"]:
                # Extend FCu around reserved S2/S3 endpoints without
                # moving any original VCM or Block-1 copper.
                output["topology"] = grid_candidates(
                    board, bounds=(18.0, 21.0, 55.0, 65.0),
                    sample_step=.5)
                output["global_window_used"] = True
            proposals = output["topology"]["candidate_via_pairs"][:20]
            if proposals:
                first = proposals[0]
                inner_a = tuple(first["via_1_xy_mm"])
                inner_b = tuple(first["via_2_xy_mm"])
                for stage, sites in (
                    ("original_outer_WEST_EAST_only", (WEST, EAST)),
                    ("outer_WEST_EAST_plus_inner_A",
                     (WEST, EAST, inner_a)),
                    ("outer_WEST_EAST_plus_inner_B",
                     (WEST, EAST, inner_b)),
                ):
                    baseline_uuids = {
                        t.m_Uuid.AsString() for t in board.GetTracks()
                        if isinstance(t, pcbnew.PCB_VIA)
                    }
                    created = []
                    try:
                        for site in sites:
                            make_via(board, site, en, .65)
                            new = [
                                t for t in board.GetTracks()
                                if isinstance(t, pcbnew.PCB_VIA)
                                and t.m_Uuid.AsString() not in baseline_uuids
                                and t not in created]
                            if len(new) != 1:
                                raise RuntimeError(
                                    "Staged scratch via identity drift")
                            created.append(new[0])
                        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                        snapshot = pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                        difference = exact_native_difference(
                            before_l3, snapshot)
                        output["native_L3_individual_via_stage_trials"].append({
                            "stage": stage,
                            "sites_mm": [list(pos) for pos in sites],
                            "loss_native_mm2": difference["loss_native_mm2"],
                            "gain_native_mm2": difference["gain_native_mm2"],
                            "exact_native_both_empty": (
                                difference["native_both_empty"]),
                            "native_DRC_qualified": False,
                        })
                    finally:
                        for via in created:
                            board.Remove(via)
                        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                        recovered = pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                        if not exact_native_difference(
                                before_l3, recovered)["native_both_empty"]:
                            raise RuntimeError(
                                "Staged scratch 3V3A rollback not exact")
                        if {t.m_Uuid.AsString() for t in board.GetTracks()
                                if isinstance(t, pcbnew.PCB_VIA)} != (
                                baseline_uuids):
                            raise RuntimeError(
                                "Staged scratch Via UUID rollback failed")
            for item in proposals:
                # Test the FOUR new vias TOGETHER; independently clean
                # sites do not imply that combined L3 zone stays unchanged.
                sites = (WEST, EAST,
                         tuple(item["via_1_xy_mm"]),
                         tuple(item["via_2_xy_mm"]))
                existing = {t.m_Uuid.AsString() for t in board.GetTracks()
                            if isinstance(t, pcbnew.PCB_VIA)}
                created = []
                try:
                    for site in sites:
                        make_via(board, site, en, .65)
                        current = [
                            t for t in board.GetTracks()
                            if isinstance(t, pcbnew.PCB_VIA)
                            and t.m_Uuid.AsString() not in existing
                            and t not in created]
                        if len(current) != 1:
                            raise RuntimeError("New scratch via not unique")
                        created.append(current[0])
                    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                    after = pcbnew.SHAPE_POLY_SET(
                        zone.GetFilledPolysList(pcbnew.In2_Cu))
                    delta = exact_native_difference(before_l3, after)
                    output["native_L3_pair_trials"].append({
                        "west_mid_vias_mm": [list(p) for p in sites],
                        "native_L3_loss_mm2": delta["loss_native_mm2"],
                        "native_L3_gain_mm2": delta["gain_native_mm2"],
                        "both_native_difference_sets_empty": (
                            delta["native_both_empty"]),
                        "protected_items_unmoved": True,
                        "native_DRC_qualified": False,
                    })
                finally:
                    for via in created:
                        board.Remove(via)
                    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                    back = pcbnew.SHAPE_POLY_SET(
                        zone.GetFilledPolysList(pcbnew.In2_Cu))
                    if not exact_native_difference(
                            before_l3, back)["native_both_empty"]:
                        raise RuntimeError("L3 area not restored after trial")
                    if {t.m_Uuid.AsString() for t in board.GetTracks()
                            if isinstance(t, pcbnew.PCB_VIA)} != existing:
                        raise RuntimeError("Scratch vias not restored")
            output["new_vias_reversible"] = True
        finally:
            board.Add(original_en)
            board.Add(ch019)
            if track_inventory(board) != initial:
                raise RuntimeError("Source track inventory not restored")
            if unchanged_fingerprints(board) != fingerprint:
                raise RuntimeError("Protected source footprint/via/zone drift")
            output["original_track_inventory_restored"] = True
            output["protected_original_fingerprint_unchanged"] = True
        output["source_PCB_untouched"] = (
            hashlib.sha256(board_path.read_bytes()).hexdigest() ==
            BOARD_SHA256
            and hashlib.sha256(archive.read_bytes()).hexdigest() ==
            ARCHIVE_SHA256)
        # SHA-pinned source identity is verified, but this isolated workflow
        # does not run a fresh native DRC against the source board.
        output["baseline_source_hash_verified"] = True
        output["status"] = "diagnostic_only_no_checkpoint_promotion"
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "proposals": result["topology"]["candidate_pair_count_before_cap"],
        "L3_pair_trials": len(result["native_L3_pair_trials"]),
        "accepted": False, "fabrication_release": False,
    }))

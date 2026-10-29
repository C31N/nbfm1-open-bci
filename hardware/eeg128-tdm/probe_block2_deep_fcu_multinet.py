#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed, native three-net Block2 F.Cu corridor displacement survey.

Inventory the FULL bounding-box of eight actually open Block2 MUX airwires.
Temporarily remove only UUID-verified Block2 F.Cu tracks. Test coupled
three-net connectivity, route only when every target has an open F.Cu
component path, restitute EVERY victim and verify native KiCad 8.0.9.
This is diagnostic engineering: never release manufacturing files or
promote a 136 PCB before schematic parity and independent byte replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from native_connectivity import airwire_counts, regressed_nets
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_ch025_fcu_l3_exact import (
    ZONE, power_fcu_obstacles, track_inventory,
)
from probe_ch025_neutral_via_sites import (
    every_zero, polygon_delta, polygon_snapshot,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from probe_real_mux_fcu_block2_ripup import same_free_component
from route_targeted_closure import (
    add_path, metrics, native, routing_domain, search, xy,
)

OPEN = (
    "CH018_P_MUX", "CH020_N_MUX", "CH020_P_MUX",
    "CH024_N_MUX", "CH024_P_MUX", "CH028_N_MUX",
    "CH029_N_MUX", "CH030_N_MUX",
)
COHORTS = {
    "N28N29N30": ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX"),
    "N20P20N24": ("CH020_N_MUX", "CH020_P_MUX", "CH024_N_MUX"),
    "P18P24N30": ("CH018_P_MUX", "CH024_P_MUX", "CH030_N_MUX"),
}
NEVER_RIP = frozenset({
    "VCM", "VCM_RAW", "AGND", "MUX_EN", "3V3A",
    "CH025_N_MUX", "CH027_N_MUX", "CH022_N_ELECTRODE",
})
LOCK = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False,
    "new_vias_added": 0, "In1_Cu_used": False,
}

def movable(net: str) -> bool:
    return (
        bool(re.fullmatch(r"CH0(?:1[6-9]|2[0-9]|3[01])_[NP]_MUX", net))
        or net in ("MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3")
    ) and net not in NEVER_RIP and net not in OPEN

def native_open_positions(report: dict[str, Any]) -> dict[str, list[tuple[float,float]]]:
    counts = airwire_counts(report)
    if any(counts.get(name, 0) != 1 for name in OPEN):
        raise RuntimeError("The eight source MUX nets are no longer singly open")
    output = {}
    for net in OPEN:
        matched = [
            row for row in report["unconnected_items"]
            if any("[" + net + "]" in x.get("description", "")
                   for x in row.get("items", []))]
        if len(matched) != 1 or len(matched[0]["items"]) != 2:
            raise RuntimeError("Unexpected native airwire topology: " + net)
        if any("on F.Cu" not in x.get("description", "")
               for x in matched[0]["items"]):
            raise RuntimeError("Unreviewed non-FCu open endpoint: " + net)
        output[net] = [
            (float(x["pos"]["x"]), float(x["pos"]["y"]))
            for x in matched[0]["items"]]
    return output

def run(candidate: Path, cohort: str, output: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union

    if cohort not in COHORTS or not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Unsupported cohort or unpinned KiCad version")
    targets = COHORTS[cohort]
    report: dict[str, Any] = {
        **LOCK, "cohort": cohort, "targets": list(targets),
        "status": "starting", "baseline_DRC": None,
        "all_bbox_FCu_inventory": [], "trials": [],
        "qualified_136": False, "all_originals_restituted": False,
        "In1_exact_after_rollback": False,
        "L3_exact_after_rollback": False,
        "source_archive_unchanged": False,
        "no_protected_net_copper_moved": False,
    }

    def progress(stage: str) -> None:
        report["last_completed_stage"] = stage
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")

    original_zip_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    progress("source_sha_verification_started")
    with tempfile.TemporaryDirectory(prefix="Block2-deep-FCu-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(candidate) as source:
            if set(source.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Source ZIP not approved")
            meta = json.loads(source.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if meta.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 source archive drift")
            for flag in ("accepted", "routing_completed",
                         "fabrication_release",
                         "routing_replay_byteidentical_verified"):
                if meta.get(flag) is not False:
                    raise RuntimeError("Source engineering release flags drifted")
            for member in MEMBERS:
                (root / member).write_bytes(source.read(member))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Pinned MUX_EN source PCB SHA changed")
        baseline = native(pcb_path, root / "before.json")
        if metrics(baseline) != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("139/0/0 native baseline drifted")
        report["baseline_DRC"] = metrics(baseline)
        positions = native_open_positions(baseline)
        progress("native_all_eight_open_MUX_endpoints_confirmed")
        board = pcbnew.LoadBoard(str(pcb_path))
        original_tracks = track_inventory(board)
        original_protected = unchanged_fingerprints(board)
        original_vias = {
            item.m_Uuid.AsString() for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)}
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        z = next((zone for zone in board.Zones()
                  if zone.m_Uuid.AsString() == ZONE
                  and zone.GetNetname() == "3V3A"
                  and zone.IsOnLayer(pcbnew.In2_Cu)), None)
        if z is None:
            raise RuntimeError("Source 3V3A protected filled zone missing")
        base_L3 = pcbnew.SHAPE_POLY_SET(
            z.GetFilledPolysList(pcbnew.In2_Cu))
        base_In1 = polygon_snapshot(board, pcbnew.In1_Cu)
        all_xy = [p for pair in positions.values() for p in pair]
        bbox = box(
            min(p[0] for p in all_xy) - 2.5,
            min(p[1] for p in all_xy) - 2.5,
            max(p[0] for p in all_xy) + 2.5,
            max(p[1] for p in all_xy) + 2.5)
        region = routing_domain(board, .075, .25).intersection(bbox)
        if region.is_empty:
            raise RuntimeError("Empty full Block2 routing domain")
        report["full_eight_net_bbox_mm"] = [
            round(v, 6) for v in region.bounds]
        candidate_lines = {
            name: LineString(positions[name]) for name in OPEN}
        selected_lines = {
            name: candidate_lines[name] for name in targets}
        source_tracks = {
            item.m_Uuid.AsString(): item for item in board.GetTracks()}
        inventory = []
        for uid, item in source_tracks.items():
            if isinstance(item, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
                continue
            if item.GetLayer() != pcbnew.F_Cu:
                continue
            trace = LineString((
                xy(item.GetStart()), xy(item.GetEnd())))
            if not trace.intersects(bbox):
                continue
            name = item.GetNetname()
            allowed = movable(name)
            distances = {
                target: round(trace.distance(line), 6)
                for target, line in selected_lines.items()}
            entry = {
                "uuid": uid, "net": name, "layer": "F.Cu",
                "from_mm": list(xy(item.GetStart())),
                "to_mm": list(xy(item.GetEnd())),
                "width_mm": pcbnew.ToMM(item.GetWidth()),
                "micro_ripup_eligible": allowed,
                "immutable": not allowed,
                "distance_to_each_target_airwire_mm": distances,
                "distance_to_nearest_target_mm": min(distances.values()),
                "crosses_target_swept_1mm": min(distances.values()) <= 1.0,
                "source_original_unchanged": True,
            }
            inventory.append(entry)
        inventory.sort(key=lambda item: (
            not item["micro_ripup_eligible"],
            item["distance_to_nearest_target_mm"], item["net"],
            item["uuid"]))
        report["all_bbox_FCu_inventory"] = inventory
        report["full_bbox_FCu_tracks"] = len(inventory)
        report["full_bbox_eligible_Block2_tracks"] = sum(
            item["micro_ripup_eligible"] for item in inventory)
        report["full_bbox_immutable_tracks"] = sum(
            item["immutable"] for item in inventory)
        report["full_bbox_eligible_nets"] = sorted({
            item["net"] for item in inventory
            if item["micro_ripup_eligible"]})
        eligible = [
            item for item in inventory
            if item["micro_ripup_eligible"]]
        progress("whole_eight_target_bbox_UUID_inventory_complete")
        # Diversity-first schedule: preserve different Block2 net escapes,
        # then expand the cut along all three actual open airwires.
        priority = []
        seen = set()
        for item in eligible:
            if (item["net"] not in seen
                    and item["distance_to_nearest_target_mm"] <= 1.5):
                seen.add(item["net"])
                priority.append(item["uuid"])
        priority += [
            item["uuid"] for item in eligible
            if item["uuid"] not in priority
            and item["distance_to_nearest_target_mm"] <= 2.5]
        priority += [
            item["uuid"] for item in eligible
            if item["uuid"] not in priority]
        report["deep_cut_order_UUIDs"] = priority
        guard = power_fcu_obstacles(board)
        report["pre_cut_topology"] = {
            name: same_free_component(
                board, pts[0], pts[1],
                board.FindNet(name).GetNetCode(), region, guard)
            for name, pts in positions.items() if name in targets}
        progress("original_three_net_FCu_components_recorded")
        global_end = time.monotonic() + 210
        for cut_size in (16, 32):
            subset = tuple(priority[:min(cut_size, len(priority))])
            if not subset or (report["trials"] and
                              subset == tuple(report["trials"][-1]["removed_UUIDs"])):
                continue
            row: dict[str, Any] = {
                "removed_UUIDs": list(subset),
                "removed_nets": sorted({
                    source_tracks[uid].GetNetname() for uid in subset}),
                "all_three_free_components_connected": False,
                "target_net_routed": [],
                "victim_restitution": [],
                "native_DRC": None,
                "candidate_136_qualified": False,
                "restored_originals": False,
                "native_In1_exact": False, "native_L3_exact": False,
                "new_vias": 0,
            }
            report["trials"].append(row)
            report["active_deep_cut_size"] = len(subset)
            if time.monotonic() >= global_end:
                row["not_executed_reason"] = "bounded_global_deadline"
                break
            for uid in subset:
                if uid not in source_tracks or not movable(
                        source_tracks[uid].GetNetname()):
                    raise RuntimeError("Unreviewed track in deep cut")
                board.Remove(source_tracks[uid])
            before_new = {item.m_Uuid.AsString() for item in board.GetTracks()}
            reinserted = set()
            try:
                if unchanged_fingerprints(board) != original_protected:
                    raise RuntimeError("Protected pads/zones/vias changed")
                progress("deep_cut_native_protected_items_unchanged")
                row["after_cut_components"] = {
                    name: same_free_component(
                        board, positions[name][0], positions[name][1],
                        board.FindNet(name).GetNetCode(), region, guard)
                    for name in targets}
                row["all_three_free_components_connected"] = all(
                    v["same_component"] for v in
                    row["after_cut_components"].values())
                progress("deep_cut_three_target_FCu_component_screen_complete")
                if not row["all_three_free_components_connected"]:
                    row["status"] = "deep_cut_still_topologically_partitioned"
                    continue
                success = True
                for name in targets:
                    if time.monotonic() >= global_end:
                        success = False
                        row["target_failure"] = "global_deadline"
                        break
                    points = positions[name]
                    code = board.FindNet(name).GetNetCode()
                    report["active_target"] = name
                    progress("bounded_three_target_Astar_in_progress")
                    proposal = search(
                        board, points[0], points[1], code,
                        .15, .15, False, 5.0,
                        step=.22, max_nodes=27000,
                        deadline=min(time.monotonic()+18, global_end),
                        start_layer=0, goal_layer=0,
                        layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    if (proposal is None or len(proposal) < 2
                            or any(k[0] != 0 for k in proposal)):
                        success = False
                        row["target_failure"] = name
                        break
                    add_path(board, proposal, code, .15,
                             layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    row["target_net_routed"].append(name)
                    progress("three_target_one_segment_added")
                if not success:
                    row["status"] = "joint_three_target_Astar_incomplete"
                    continue
                # Each victim is restored, by reroute or by reinstating
                # original copper; native DRC vetoes collisions in either.
                for uid in subset:
                    item = source_tracks[uid]
                    code = item.GetNetCode()
                    progress("victim_restitution_in_progress")
                    proposal = None
                    if time.monotonic() + 1 < global_end:
                        proposal = search(
                            board, xy(item.GetStart()), xy(item.GetEnd()),
                            code, .15, .15, False, 2.5,
                            step=.25, max_nodes=16000,
                            deadline=min(time.monotonic()+8, global_end),
                            start_layer=0, goal_layer=0,
                            layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    if (proposal is not None and len(proposal) >= 2
                            and all(k[0] == 0 for k in proposal)):
                        add_path(board, proposal, code, .15,
                                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        strategy = "new_FCu_trace"
                    else:
                        board.Add(item)
                        reinserted.add(uid)
                        strategy = "exact_original_reinserted_needs_DRC"
                    row["victim_restitution"].append({
                        "uuid": uid, "net": item.GetNetname(),
                        "strategy": strategy})
                    progress("single_victim_restituted")
                if any(track_inventory(board).get(k) != v
                       for k, v in original_tracks.items()
                       if k not in subset):
                    raise RuntimeError("Unselected original copper changed")
                if unchanged_fingerprints(board) != original_protected:
                    raise RuntimeError("Protected original copper changed")
                added_vias = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if isinstance(item, pcbnew.PCB_VIA)}
                if added_vias != original_vias:
                    raise RuntimeError("No-via invariant violated")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                delta = exact_native_difference(
                    base_L3, pcbnew.SHAPE_POLY_SET(
                        z.GetFilledPolysList(pcbnew.In2_Cu)))
                row["candidate_L3_loss_mm2"] = delta["loss_native_mm2"]
                row["candidate_L3_gain_mm2"] = delta["gain_native_mm2"]
                row["candidate_L3_exact_zero"] = delta["native_both_empty"]
                row["candidate_In1_exact_zero"] = every_zero(polygon_delta(
                    base_In1, polygon_snapshot(board, pcbnew.In1_Cu)))
                progress("cumulative_native_In1_and_3V3A_area_gates_checked")
                if not (row["candidate_L3_exact_zero"]
                        and row["candidate_In1_exact_zero"]):
                    row["status"] = "power_exact_zero_candidate_rejected"
                    continue
                scratch_dir = root / f"joint-{cut_size}"
                scratch_dir.mkdir()
                for member in MEMBERS[1:]:
                    shutil.copyfile(root / member, scratch_dir / member)
                scratch = scratch_dir / MEMBERS[0]
                pcbnew.SaveBoard(str(scratch), board)
                post = native(scratch, root / f"post-{cut_size}.json")
                row["native_DRC"] = metrics(post)
                row["native_target_open"] = {
                    name: airwire_counts(post).get(name, 0)
                    for name in targets}
                row["net_regressions"] = regressed_nets(baseline, post)
                row["candidate_136_qualified"] = (
                    row["native_DRC"] == {
                        "violations": 0, "warnings": 0,
                        "unconnected": 136}
                    and all(count == 0
                            for count in row["native_target_open"].values())
                    and not row["net_regressions"])
                row["status"] = (
                    "native_136_drc_candidate_only_not_replay_qualified"
                    if row["candidate_136_qualified"]
                    else "joint_136_native_DRC_or_connectivity_rejected")
                progress("native_three_net_136_DRC_result_persisted")
                report["qualified_136"] |= row["candidate_136_qualified"]
            finally:
                # Exact rollback of any added tracks and original victim UUIDs.
                for item in list(board.GetTracks()):
                    if item.m_Uuid.AsString() not in before_new:
                        board.Remove(item)
                for uid in subset:
                    if uid in reinserted:
                        board.Remove(source_tracks[uid])
                    board.Add(source_tracks[uid])
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                row["restored_originals"] = (
                    track_inventory(board) == original_tracks
                    and unchanged_fingerprints(board) == original_protected
                    and {
                        item.m_Uuid.AsString() for item in board.GetTracks()
                        if isinstance(item, pcbnew.PCB_VIA)} == original_vias)
                row["native_L3_exact"] = exact_native_difference(
                    base_L3, pcbnew.SHAPE_POLY_SET(
                        z.GetFilledPolysList(pcbnew.In2_Cu))
                )["native_both_empty"]
                row["native_In1_exact"] = every_zero(polygon_delta(
                    base_In1, polygon_snapshot(board, pcbnew.In1_Cu)))
                if not (row["restored_originals"]
                        and row["native_L3_exact"] and row["native_In1_exact"]):
                    raise RuntimeError("Fail-closed rollback or zone identity")
                progress("deep_trial_all_original_UUIDs_restored")
        report["all_originals_restituted"] = (
            track_inventory(board) == original_tracks
            and unchanged_fingerprints(board) == original_protected)
        report["In1_exact_after_rollback"] = every_zero(polygon_delta(
            base_In1, polygon_snapshot(board, pcbnew.In1_Cu)))
        report["L3_exact_after_rollback"] = exact_native_difference(
            base_L3, pcbnew.SHAPE_POLY_SET(
                z.GetFilledPolysList(pcbnew.In2_Cu)))["native_both_empty"]
        report["no_protected_net_copper_moved"] = (
            report["all_originals_restituted"])
        if not (report["all_originals_restituted"]
                and report["In1_exact_after_rollback"]
                and report["L3_exact_after_rollback"]):
            raise RuntimeError("Protected source after trial differs")
        report["status"] = (
            "candidate_136_only_not_accepted_without_parity_replay"
            if report["qualified_136"]
            else "deep_multinet_corridor_not_136_native_qualified")
    report["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() ==
        original_zip_sha)
    progress("native_deep_Block2_diagnostic_complete")
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cohort", choices=tuple(COHORTS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    result = run(options.candidate, options.cohort, options.output)
    print(json.dumps({
        "cohort": result["cohort"],
        "status": result["status"],
        "136_native_candidate": result["qualified_136"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

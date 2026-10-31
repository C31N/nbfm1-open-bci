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
# Evidence from workflow #8: two native 138 candidates each failed on
# these four original victim tracks (five DRC violations per candidate).
# UUIDs are diagnostic constraints, never permission to move protected copper.
RESTITUTION_HOTSPOTS = {
    "31a40ce9-1b3f-4f1a-b654-7fec9e793976": ("MUX_S2", 4),
    "2ac3aecb-9a62-4bc7-846a-75a782ad0474": ("MUX_S1", 2),
    "c320c092-5407-4ad6-9a97-2c324373271c": ("MUX_S3", 2),
    "d63cd5b4-9b79-4d97-8e66-1895bb81d615": ("MUX_S2", 2),
}

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
        "qualified_136": False,
        "any_native_net_reduction_qualified": False,
        "all_originals_restituted": False,
        "In1_exact_after_rollback": False,
        "L3_exact_after_rollback": False,
        "source_archive_unchanged": False,
        "no_protected_net_copper_moved": False,
        "historical_138_DRC_hotspot_UUIDs": {
            uid: {"net": net, "combined_DRC_findings": count}
            for uid, (net, count) in RESTITUTION_HOTSPOTS.items()
        },
        "predictive_policy": "reject any victim without a routed FCu return; no fallback",
    }

    native_start = time.monotonic()
    def progress(stage: str) -> None:
        report["last_completed_stage"] = stage
        report.setdefault("stage_elapsed_seconds", {})[stage] = round(
            time.monotonic() - native_start, 3)
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
        # Diversify cuts rather than assuming larger prefix cuts always win.
        # The protected-hotspot variant probes whether the S-bus long tracks
        # are better preserved while other Block2 copper is displaced.
        cut_plans = [
            ("mux-s2-first-32", tuple(priority[:32])),
            ("prefix-16", tuple(priority[:16])),
            ("prefix-32", tuple(priority[:32])),
            ("preserve-hotspots-32", tuple(
                uid for uid in priority if uid not in RESTITUTION_HOTSPOTS)[:32]),
            ("expanded-48", tuple(priority[:48])),
        ]
        report["planned_cuts"] = [
            {"label": label, "UUID_count": len(uuids)}
            for label, uuids in cut_plans]
        global_end = time.monotonic() + 165
        seen_cuts: set[tuple[bool, tuple[str, ...]]] = set()
        for cut_size, subset in cut_plans:
            # The same UUIDs are intentionally compared under two different
            # corridor-order strategies, so the key includes the strategy.
            cut_key = (cut_size == "mux-s2-first-32", subset)
            if not subset or cut_key in seen_cuts:
                continue
            seen_cuts.add(cut_key)
            row: dict[str, Any] = {
                "removed_UUIDs": list(subset),
                "removed_nets": sorted({
                    source_tracks[uid].GetNetname() for uid in subset}),
                "all_three_free_components_connected": False,
                "reachable_targets": [],
                "candidate_native_net_reduction_qualified": False,
                "target_net_routed": [],
                "victim_restitution": [],
                "native_DRC": None,
                "candidate_136_qualified": False,
                "restored_originals": False,
                "native_In1_exact": False, "native_L3_exact": False,
                "new_vias": 0,
                "cut_strategy": cut_size,
                "predictive_restitution_blocked_UUIDs": [],
                "predictive_restitution_routes_found": False,
                "early_mux_s2_reserved_UUIDs": [],
                "early_mux_s2_restitution_proven": False,
                "early_mux_s2_scratch_DRC": None,
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
                row["reachable_targets"] = [
                    name for name in targets
                    if row["after_cut_components"][name]["same_component"]]
                row["all_three_free_components_connected"] = (
                    len(row["reachable_targets"]) == 3)
                progress("deep_cut_three_target_FCu_component_screen_complete")
                if not row["reachable_targets"]:
                    row["status"] = "deep_cut_still_topologically_partitioned"
                    continue
                # Optional victim-first branch: reserve a real alternative
                # for the proven MUX_S2 blocker BEFORE routing target nets.
                # Strictly F.Cu; no new via or protected net is altered.
                # Keeping the original MUX_S2 in place was already found to
                # partition the target topology (preserve-hotspots-32).
                if cut_size == "mux-s2-first-32":
                    mux_s2_uid = "31a40ce9-1b3f-4f1a-b654-7fec9e793976"
                    if mux_s2_uid not in subset:
                        row["status"] = "early_mux_s2_not_in_selected_cut"
                        continue
                    victim = source_tracks[mux_s2_uid]
                    if victim.GetNetname() != "MUX_S2" or victim.GetLayer() != pcbnew.F_Cu:
                        raise RuntimeError("MUX_S2 UUID identity mismatch")
                    # Avoid the three target airwire lanes during the early
                    # return search, then keep the new copper on the board
                    # while searching each target route. This is a soft
                    # preference, not an unsafe clearance exception.
                    avoid_target_lanes = unary_union([
                        LineString(positions[name]).buffer(.34)
                        for name in targets])
                    early_path = search(
                        board, xy(victim.GetStart()), xy(victim.GetEnd()),
                        victim.GetNetCode(), .15, .15, False, 5.0,
                        step=.20, max_nodes=42000,
                        deadline=min(time.monotonic()+19, global_end),
                        start_layer=0, goal_layer=0,
                        layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                        cost_regions=((0, avoid_target_lanes, 40.0),))
                    if (early_path is None or len(early_path) < 2
                            or any(p[0] != 0 for p in early_path)):
                        row["status"] = "early_mux_s2_corridor_unavailable"
                        progress("victim_first_mux_s2_has_no_FCu_corridor")
                        continue
                    add_path(board, early_path, victim.GetNetCode(), .15,
                             layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    row["early_mux_s2_reserved_UUIDs"].append(mux_s2_uid)
                    progress("victim_first_mux_s2_corridor_pre_reserved")
                # Original victim corridors receive a soft reservation
                # BEFORE target routing, rather than being displaced last.
                victim_reservation = unary_union([
                    LineString((
                        xy(source_tracks[uid].GetStart()),
                        xy(source_tracks[uid].GetEnd())
                    )).buffer(.245)
                    for uid in subset])
                row["victim_corridors_pre_reserved"] = len(subset)
                progress("victim_return_corridor_pre_reserved")
                # A single truly open MUX pair must first pass KiCad's
                # native 138 gate before three independent closures can
                # form a candidate for the stricter 136 replay gate.
                success = True
                for name in row["reachable_targets"]:
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
                        layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                        cost_regions=((0, victim_reservation, 35.0),))
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
                # Reinsert noncolliding original victims first: they
                # reserve real copper corridors for the A* reroutes.
                progress("victim_overlap_inventory_started")
                new_targets = [
                    tr for tr in board.GetTracks()
                    if tr.m_Uuid.AsString() not in before_new
                    and not isinstance(tr, pcbnew.PCB_VIA)
                    and tr.GetLayer() == pcbnew.F_Cu]
                if not new_targets:
                    raise RuntimeError("No target FCu copper to qualify")
                occupied = unary_union([
                    LineString((
                        xy(tr.GetStart()), xy(tr.GetEnd())
                    )).buffer(pcbnew.ToMM(tr.GetWidth()) / 2 + .151)
                    for tr in new_targets])
                reroute = []
                for uid in subset:
                    victim = source_tracks[uid]
                    if uid in row["early_mux_s2_reserved_UUIDs"]:
                        row["victim_restitution"].append({
                            "uuid": uid, "net": victim.GetNetname(),
                            "strategy": "early_FCu_copper_native_verification_pending"})
                        continue
                    old_geom = LineString((
                        xy(victim.GetStart()), xy(victim.GetEnd())
                    )).buffer(pcbnew.ToMM(victim.GetWidth()) / 2)
                    if old_geom.intersects(occupied):
                        reroute.append(uid)
                    else:
                        board.Add(victim)
                        reinserted.add(uid)
                        row["victim_restitution"].append({
                            "uuid": uid, "net": victim.GetNetname(),
                            "strategy": "original_copper_pre_reserved"})
                row["victim_reroute_UUIDs"] = list(reroute)
                row["victims_preserved_original"] = len(reinserted)
                progress("victim_original_corridors_restored")
                # Predictive cooperative candidate: no cut is admissible
                # if its replacement FCu corridor cannot be routed while
                # the target copper and the other victims occupy the board.
                # Route the four proven restitution blockers first, then
                # every other displaced victim. Never reinsert a colliding
                # original merely to make the bookkeeping appear complete.
                predictive_failed = False
                for uid in sorted(reroute, key=lambda u: (
                        u not in RESTITUTION_HOTSPOTS,
                        -RESTITUTION_HOTSPOTS.get(u, ("", 0))[1], u)):
                    victim = source_tracks[uid]
                    report["active_victim_UUID"] = uid
                    progress("predictive_victim_return_search_started")
                    proposed = None
                    for grid_step, node_limit, budget in (
                            (.20, 27000, 10), (.14, 40000, 15)):
                        if time.monotonic() + 2 >= global_end:
                            break
                        trial_path = search(
                            board, xy(victim.GetStart()),
                            xy(victim.GetEnd()), victim.GetNetCode(),
                            .15, .15, False, 2.5, step=grid_step,
                            max_nodes=node_limit,
                            deadline=min(time.monotonic()+budget, global_end),
                            start_layer=0, goal_layer=0,
                            layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        if (trial_path is not None and len(trial_path) >= 2
                                and all(point[0] == 0 for point in trial_path)):
                            proposed = trial_path
                            break
                    if proposed is None:
                        row["predictive_restitution_blocked_UUIDs"].append(uid)
                        row["victim_restitution"].append({
                            "uuid": uid, "net": victim.GetNetname(),
                            "strategy": "reject_no_verified_FCu_return"})
                        predictive_failed = True
                        progress("predictive_return_deadlock_UUID_persisted")
                        break
                    add_path(board, proposed, victim.GetNetCode(), .15,
                             layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    row["victim_restitution"].append({
                        "uuid": uid, "net": victim.GetNetname(),
                        "strategy": "proposed_FCu_return_pending_native_DRC"})
                    progress("predictive_return_path_added")
                report.pop("active_victim_UUID", None)
                if predictive_failed:
                    # Preserve the rejected scratch topology as an isolated
                    # native DRC diagnostic. KiCad 8.0.9 reliably returns
                    # to pristine source after SaveBoard/native() here,
                    # whereas reloading a live pre-DRC SWIG board crashed
                    # with exit 139 in native experiment #11.
                    deadlock_dir = root / f"deadlock-{cut_size}"
                    deadlock_dir.mkdir()
                    for member in MEMBERS[1:]:
                        shutil.copyfile(root / member, deadlock_dir / member)
                    deadlock_board = deadlock_dir / MEMBERS[0]
                    pcbnew.SaveBoard(str(deadlock_board), board)
                    diagnostic = native(
                        deadlock_board,
                        root / f"deadlock-{cut_size}.json")
                    row["predictive_deadlock_diagnostic_DRC"] = metrics(
                        diagnostic)
                    progress("native_predictive_deadlock_diagnostic_saved")
                    row["status"] = "predictive_restitution_deadlock_rejected"
                    continue
                if len(row["victim_restitution"]) != len(subset):
                    raise RuntimeError("Victim accounting incomplete")
                row["predictive_restitution_routes_found"] = True
                progress("all_displaced_victims_accounted")
                progress("native_original_inventory_check_started")
                current_track_inventory = track_inventory(board)
                if any(current_track_inventory.get(k) != v
                       for k, v in original_tracks.items()
                       if k not in subset):
                    raise RuntimeError("Unselected original copper changed")
                progress("native_original_inventory_check_complete")
                if unchanged_fingerprints(board) != original_protected:
                    raise RuntimeError("Protected original copper changed")
                added_vias = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if isinstance(item, pcbnew.PCB_VIA)}
                if added_vias != original_vias:
                    raise RuntimeError("No-via invariant violated")
                progress("candidate_zone_fill_started")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                progress("candidate_zone_fill_complete")
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
                progress("candidate_fresh_native_DRC_started")
                post = native(scratch, root / f"post-{cut_size}.json")
                progress("candidate_fresh_native_DRC_complete")
                row["native_DRC"] = metrics(post)
                row["native_DRC_violation_details"] = post["violations"]
                row["native_target_open"] = {
                    name: airwire_counts(post).get(name, 0)
                    for name in targets}
                row["net_regressions"] = regressed_nets(baseline, post)
                row["candidate_native_net_reduction_qualified"] = (
                    row["native_DRC"] == {
                        "violations": 0, "warnings": 0,
                        "unconnected": 139 - len(row["target_net_routed"])}
                    and all(count == 0
                            for count in row["native_target_open"].values())
                    and not row["net_regressions"])
                row["predictive_restitution_native_DRC_clean"] = (
                    row["native_DRC"]["violations"] == 0
                    and row["native_DRC"]["warnings"] == 0
                    and not row["net_regressions"])
                row["candidate_136_qualified"] = (
                    row["candidate_native_net_reduction_qualified"]
                    and len(row["target_net_routed"]) == 3)
                row["status"] = (
                    "native_136_drc_candidate_only_not_replay_qualified"
                    if row["candidate_136_qualified"]
                    else "native_partial_copper_candidate_not_released"
                    if row["candidate_native_net_reduction_qualified"]
                    else "joint_native_DRC_or_connectivity_rejected")
                progress("native_individual_or_three_net_DRC_result_persisted")
                report["qualified_136"] |= row["candidate_136_qualified"]
                report["any_native_net_reduction_qualified"] |= (
                    row["candidate_native_net_reduction_qualified"])
            finally:
                # A victim-first proposal which did not reach native DRC
                # still receives a scratch native DRC before rollback.
                # Never risk stale KiCad SWIG objects after adding copper.
                if (row["early_mux_s2_reserved_UUIDs"]
                        and row.get("native_DRC") is None
                        and row.get("predictive_deadlock_diagnostic_DRC") is None):
                    early_dir = root / ("early-S2-" + str(cut_size))
                    early_dir.mkdir()
                    for member in MEMBERS[1:]:
                        shutil.copyfile(root / member, early_dir / member)
                    early_board = early_dir / MEMBERS[0]
                    pcbnew.SaveBoard(str(early_board), board)
                    report_early = native(
                        early_board, root / ("early-S2-" + str(cut_size) + ".json"))
                    row["early_mux_s2_scratch_DRC"] = metrics(report_early)
                    progress("victim_first_scratch_native_DRC_complete")
                progress("rollback_original_copper_started")
                if (row.get("native_DRC") is not None or
                        row.get("predictive_deadlock_diagnostic_DRC") is not None
                        or row.get("early_mux_s2_scratch_DRC") is not None):
                    # Restore from the immutable pinned PCB only after the
                    # trial board was saved and native DRC ran on a separate
                    # file. This is the successfully validated KiCad #8 path.
                    progress("pristine_native_board_reload_started")
                    if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != (
                            PINNED_CANDIDATE_SHA):
                        raise RuntimeError("Original disk source SHA drift")
                    board = pcbnew.LoadBoard(str(pcb_path))
                    source_tracks = {
                        item.m_Uuid.AsString(): item
                        for item in board.GetTracks()}
                    z = next((zone for zone in board.Zones()
                              if zone.m_Uuid.AsString() == ZONE
                              and zone.GetNetname() == "3V3A"
                              and zone.IsOnLayer(pcbnew.In2_Cu)), None)
                    if z is None:
                        raise RuntimeError("Protected zone absent in source")
                    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                    row["rollback_from_pristine_source"] = True
                else:
                    # Purely topological candidate (no added target path):
                    # use the original native UUID-safe in-memory rollback.
                    for item in list(board.GetTracks()):
                        if item.m_Uuid.AsString() not in before_new:
                            board.Remove(item)
                    for uid in subset:
                        if uid in reinserted:
                            board.Remove(source_tracks[uid])
                        board.Add(source_tracks[uid])
                    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                    row["rollback_from_pristine_source"] = False
                row["restored_originals"] = (
                    track_inventory(board) == original_tracks
                    and unchanged_fingerprints(board) == original_protected
                    and {item.m_Uuid.AsString()
                         for item in board.GetTracks()
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
            else "native_partial_reduction_only_no_release"
            if report["any_native_net_reduction_qualified"]
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

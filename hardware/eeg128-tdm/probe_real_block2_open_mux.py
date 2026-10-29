#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Route a real native Block2 open airwire, single-layer, no release.

Unlike CH025/CH027/CH022 (already zero native airwires), these three
MUX nets have verified missing connections on the pinned 139 board.
All candidate geometry is temporary, and a single-net success is still
not an accepted 136 checkpoint. Native KiCad 8.0.9 arbitrates DRC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from probe_ch025_fcu_l3_exact import ZONE, track_inventory
from probe_ch025_neutral_via_sites import (
    every_zero, polygon_delta, polygon_snapshot,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    add_path, metrics, native, search,
)

NETS = (
    "CH018_P_MUX", "CH020_N_MUX", "CH020_P_MUX",
    "CH024_N_MUX", "CH024_P_MUX",
    "CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX",
)
LOCK = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "new_vias_added": 0,
    "In1_Cu_used": False,
}

def run(candidate: Path, net: str, report_path: Path) -> dict[str, Any]:
    import pcbnew
    if net not in NETS:
        raise ValueError("Net not explicitly reviewed as a real airwire")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Unpinned KiCad")
    report: dict[str, Any] = {
        **LOCK, "net": net, "status": "not_started",
        "native_139_baseline": None,
        "native_candidate": None,
        "native_net_before": None,
        "native_net_after": None,
        "airwire_reduction": None,
        "native_DRC_qualified": False,
        "native_3V3A_exact": False,
        "native_In1_exact": False,
        "original_copper_restituted": False,
        "source_archive_unchanged": False,
        "no_regressed_nets": False,
    }

    def write(stage: str) -> None:
        report["stage"] = stage
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    write("native_preflight")
    source_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="real-mux-139-probe-") as td:
        root = Path(td)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unreviewed 139 engineering members")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Source archive SHA mismatch")
            for field in ("accepted", "routing_completed",
                          "fabrication_release",
                          "routing_replay_byteidentical_verified"):
                if audit.get(field) is not False:
                    raise RuntimeError("Unsafe 139 source acceptance state")
            for member in MEMBERS:
                (root / member).write_bytes(z.read(member))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Pinned MUX_EN/CH019 PCB SHA mismatch")
        baseline = native(pcb_path, root / "baseline.json")
        report["native_139_baseline"] = metrics(baseline)
        if report["native_139_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("Expected 139/0/0 native baseline")
        counts = airwire_counts(baseline)
        report["native_net_before"] = counts.get(net, 0)
        if report["native_net_before"] != 1:
            raise RuntimeError("Target no longer exactly one open net")
        matches = [
            row for row in baseline["unconnected_items"]
            if any("[" + net + "]" in item.get("description", "")
                   for item in row.get("items", []))]
        if len(matches) != 1 or len(matches[0]["items"]) != 2:
            raise RuntimeError("Not an exact native two-anchor airwire")
        ends = matches[0]["items"]
        if not all(("on F.Cu" in item["description"])
                   for item in ends):
            raise RuntimeError("Reviewed endpoints are no longer F.Cu")
        positions = [
            (float(item["pos"]["x"]), float(item["pos"]["y"]))
            for item in ends
        ]
        report["native_source_airwire"] = matches[0]
        report["physical_endpoints_mm"] = [
            list(point) for point in positions]
        write("native_real_missing_airwire_confirmed")
        board = pcbnew.LoadBoard(str(pcb_path))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        vias = {
            item.m_Uuid.AsString()
            for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)}
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Protected native 3V3A zone missing")
        original_3v3a = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        original_in1 = polygon_snapshot(board, pcbnew.In1_Cu)
        code = board.FindNet(net).GetNetCode()
        report["search_attempted"] = True
        write("bounded_single_layer_FCu_Astar_started")
        proposed = search(
            board, positions[0], positions[1], code,
            .15, .15, False, 6.0, step=.22,
            max_nodes=40000, deadline=time.monotonic()+35,
            start_layer=0, goal_layer=0,
            layers=(pcbnew.F_Cu, pcbnew.B_Cu))
        if (proposed is None or len(proposed) < 2
                or any(pt[0] != 0 for pt in proposed)):
            report["status"] = "bounded_FCu_search_no_path"
            report["original_copper_restituted"] = (
                track_inventory(board) == original
                and unchanged_fingerprints(board) == protected)
            write("bounded_FCu_search_no_path")
        else:
            report["native_FCu_path_points"] = [
                list(point) for point in proposed]
            before_ids = set(original)
            try:
                add_path(board, proposed, code, .15,
                         layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                if (any(track_inventory(board).get(uid) != val
                        for uid, val in original.items())
                        or unchanged_fingerprints(board) != protected):
                    raise RuntimeError("Original copper/via/pad changed")
                new_vias = {
                    item.m_Uuid.AsString()
                    for item in board.GetTracks()
                    if isinstance(item, pcbnew.PCB_VIA)}
                if new_vias != vias:
                    raise RuntimeError("New via in no-via F.Cu routing")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                delta = exact_native_difference(
                    original_3v3a,
                    pcbnew.SHAPE_POLY_SET(
                        zone.GetFilledPolysList(pcbnew.In2_Cu)))
                report["L3_loss_native_mm2"] = delta["loss_native_mm2"]
                report["L3_gain_native_mm2"] = delta["gain_native_mm2"]
                report["native_3V3A_exact"] = delta["native_both_empty"]
                report["native_In1_exact"] = every_zero(polygon_delta(
                    original_in1,
                    polygon_snapshot(board, pcbnew.In1_Cu)))
                write("native_power_exclusion_qualified")
                if report["native_3V3A_exact"] and report["native_In1_exact"]:
                    scratch = root / "scratch"
                    scratch.mkdir()
                    for member in MEMBERS[1:]:
                        shutil.copyfile(root / member, scratch / member)
                    revised = scratch / MEMBERS[0]
                    pcbnew.SaveBoard(str(revised), board)
                    post = native(revised, root / "post.json")
                    after = airwire_counts(post)
                    report["native_candidate"] = metrics(post)
                    report["native_net_after"] = after.get(net, 0)
                    report["airwire_reduction"] = (
                        report["native_net_before"] -
                        report["native_net_after"])
                    report["regressed_nets"] = regressed_nets(baseline, post)
                    report["no_regressed_nets"] = not report["regressed_nets"]
                    report["native_DRC_qualified"] = (
                        report["native_candidate"] ==
                        {"violations": 0, "warnings": 0, "unconnected": 138}
                        and report["native_net_after"] == 0
                        and report["no_regressed_nets"])
                    write("native_FCu_DRC_and_airwire_qualification_complete")
                report["status"] = (
                    "native_single_real_airwire_qualified_no_release"
                    if report["native_DRC_qualified"]
                    else "native_real_airwire_candidate_not_qualified")
            finally:
                new_tracks = [
                    item for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in before_ids]
                for item in new_tracks:
                    board.Remove(item)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                report["original_copper_restituted"] = (
                    track_inventory(board) == original
                    and unchanged_fingerprints(board) == protected
                    and exact_native_difference(
                        original_3v3a,
                        pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                    )["native_both_empty"]
                    and every_zero(polygon_delta(
                        original_in1,
                        polygon_snapshot(board, pcbnew.In1_Cu))))
                if not report["original_copper_restituted"]:
                    raise RuntimeError("Original copper rollback incomplete")
                write("all_original_copper_restituted")
    report["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == source_sha)
    write("complete")
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--net", choices=NETS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.candidate, args.net, args.output)
    print(json.dumps({
        "net": args.net, "status": result["status"],
        "qualified": result["native_DRC_qualified"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

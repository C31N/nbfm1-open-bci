#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native zone-neutral CH025 via-site audit on a disposable pinned 139 board.

Screens geometrically nominated new vias only, without modifying the source
archive, routing signals, authorizing In1.Cu/AGND changes or releasing a PCB.
Native exact copper-polygon equality is mandatory on BOTH power layers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from typing import Any

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from probe_ch025_fcu_l3_exact import CUT, ZONE, track_inventory
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from probe_ch025_ch027_transition import graph_components
from route_targeted_closure import make_via, metrics, native

NET = "CH025_N_MUX"
S3 = "5086ca27-2c22-448d-a5e4-22e598d226d3"
L3 = "3V3A"
FLAGS = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "checkpoint_promoted": False,
    "manufacturing_files": False, "In1_Cu_used": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
    "physical_route_qualified": False,
}

def polygon_snapshot(board: Any, layer: int) -> dict[str, Any]:
    import pcbnew
    return {
        z.m_Uuid.AsString(): pcbnew.SHAPE_POLY_SET(
            z.GetFilledPolysList(layer))
        for z in board.Zones() if z.IsOnLayer(layer)
    }

def polygon_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if set(a) != set(b):
        raise RuntimeError("Zone UUID membership changed")
    return {
        key: exact_native_difference(a[key], b[key])
        for key in sorted(a)
    }

def every_zero(d: dict[str, Any]) -> bool:
    return all(v["native_both_empty"] for v in d.values())

def run(candidate: Path) -> dict[str, Any]:
    import pcbnew
    out: dict[str, Any] = {
        **FLAGS, "status": "not_started",
        "source_PCB_SHA256": PINNED_CANDIDATE_SHA,
        "source_archive_139_sha256": ARCHIVE_SHA256,
        "source_archive_unchanged": False,
        "baseline_native_DRC": None,
        "protected_originals_restituted": False,
        "L3_control_exact_zero": False,
        "In1_control_exact_zero": False,
        "via_sites": [], "via_pairs": [],
        "candidate_site_count": 0,
        "topological_via_paths": [],
        "topological_status": None,
        "native_zone_neutral_pair_found": False,
        "DRC_of_new_copper_qualified": False,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Only KiCad 8.0.9 is qualified")
    archive_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="CH025-L3-exact-via-") as temp:
        folder = Path(temp)
        with zipfile.ZipFile(candidate) as bundle:
            allowed = set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}
            if set(bundle.namelist()) != allowed:
                raise RuntimeError("Unexpected engineering archive members")
            audit = json.loads(bundle.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 archive identity drift")
            for gate in ("accepted", "fabrication_release",
                         "routing_completed",
                         "routing_replay_byteidentical_verified"):
                if audit.get(gate) is not False:
                    raise RuntimeError("Unexpected candidate release state")
            for item in MEMBERS:
                (folder / item).write_bytes(bundle.read(item))
        pcb_path = folder / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("MUX_EN and CH019 pinned PCB mismatch")
        out["baseline_native_DRC"] = metrics(
            native(pcb_path, folder / "native-baseline.json"))
        if out["baseline_native_DRC"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "baseline_DRC_gate_failed"
            return out
        board = pcbnew.LoadBoard(str(pcb_path))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        current = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        for uid, net, layer in (
                (CUT, NET, pcbnew.In2_Cu),
                (S3, "MUX_S3", pcbnew.F_Cu)):
            row = current.get(uid)
            if (row is None or row.GetNetname() != net
                    or row.GetLayer() != layer
                    or isinstance(row, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                raise RuntimeError("Unreviewed virtual cut: " + uid)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        base_l3 = polygon_snapshot(board, pcbnew.In2_Cu)
        base_in1 = polygon_snapshot(board, pcbnew.In1_Cu)
        if ZONE not in base_l3:
            raise RuntimeError("Pinned 3V3A zone absent")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        out["L3_control_exact_zero"] = every_zero(
            polygon_delta(base_l3, polygon_snapshot(board, pcbnew.In2_Cu)))
        out["In1_control_exact_zero"] = every_zero(
            polygon_delta(base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
        if not (out["L3_control_exact_zero"] and
                out["In1_control_exact_zero"]):
            raise RuntimeError("Native same-board refill is not byte-exact")
        for uid in (CUT, S3):
            board.Remove(current[uid])
        try:
            topo = graph_components(
                board, NET, (49.45, 14.90), (36.105, 48.85),
                target_layer="F")
            out["topological_status"] = topo["status"]
            out["topological_via_paths"] = topo["topological_via_paths"][:2]
            proposals: list[tuple[float, float]] = []
            for route in out["topological_via_paths"]:
                for row in route:
                    if not row.get("preexisting", False):
                        proposals.append(tuple(row["xy_mm"]))
            expected_components = {topo["source_FCu_component"],
                                   topo["target_FCu_component"]}
            for row in topo.get("exact_polygon_via_pair_inventory", []):
                if row["FCu_component"] in expected_components:
                    proposals.append(tuple(row["xy_mm"]))
            unique = list(dict.fromkeys(proposals))[:20]
        finally:
            board.Add(current[CUT])
            board.Add(current[S3])
            if track_inventory(board) != original:
                raise RuntimeError("Virtual CH025/S3 ripup failed restitution")
        out["candidate_site_count"] = len(unique)
        netcode = board.FindNet(NET).GetNetCode()
        before_via_ids = {
            t.m_Uuid.AsString() for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)}
        def test_sites(points: tuple[tuple[float, float], ...]) -> dict[str, Any]:
            new_items = []
            try:
                for xy in points:
                    make_via(board, xy, netcode, .65)
                    all_vias = [
                        t for t in board.GetTracks()
                        if isinstance(t, pcbnew.PCB_VIA)
                        and t.m_Uuid.AsString() not in before_via_ids]
                    if len(all_vias) != len(new_items) + 1:
                        raise RuntimeError("Unexpected new-via identity count")
                    new_items = all_vias
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                l3_delta = polygon_delta(
                    base_l3, polygon_snapshot(board, pcbnew.In2_Cu))
                in1_delta = polygon_delta(
                    base_in1, polygon_snapshot(board, pcbnew.In1_Cu))
                return {
                    "xy_mm": [list(p) for p in points],
                    "L3_native_exact_zero": every_zero(l3_delta),
                    "In1_native_exact_zero": every_zero(in1_delta),
                    "L3_3V3A_diff": {
                        key: l3_delta[ZONE][key]
                        for key in ("native_both_empty", "loss_native_mm2",
                                    "gain_native_mm2")},
                    "every_power_zone_exact": (
                        every_zero(l3_delta) and every_zero(in1_delta)),
                    "physical_route_qualified": False,
                    "DRC_qualified": False,
                }
            finally:
                for via in new_items:
                    board.Remove(via)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                if not every_zero(polygon_delta(
                        base_l3, polygon_snapshot(board, pcbnew.In2_Cu))):
                    raise RuntimeError("L3 zone failed post-trial restitution")
                if not every_zero(polygon_delta(
                        base_in1, polygon_snapshot(board, pcbnew.In1_Cu))):
                    raise RuntimeError("In1 AGND failed post-trial restitution")
        for point in unique:
            out["via_sites"].append(test_sites((point,)))
        qualified = [tuple(row["xy_mm"][0])
                     for row in out["via_sites"]
                     if row["every_power_zone_exact"]]
        # Two individually neutral vias still require a cumulative check.
        # These are the only pairs that may pass a monotonic zone-clearance gate.
        for i, a in enumerate(qualified[:4]):
            for b in qualified[i + 1:8]:
                out["via_pairs"].append(test_sites((a, b)))
                if len(out["via_pairs"]) >= 12:
                    break
            if len(out["via_pairs"]) >= 12:
                break
        out["native_zone_neutral_pair_found"] = any(
            row["every_power_zone_exact"] for row in out["via_pairs"])
        out["protected_originals_restituted"] = (
            track_inventory(board) == original
            and unchanged_fingerprints(board) == protected
            and before_via_ids == {
                t.m_Uuid.AsString() for t in board.GetTracks()
                if isinstance(t, pcbnew.PCB_VIA)})
        if not out["protected_originals_restituted"]:
            raise RuntimeError("Protected source geometry was not fully restored")
        out["status"] = (
            "zone_neutral_pair_screen_only_not_routed"
            if out["native_zone_neutral_pair_found"]
            else "no_native_exact_zero_two_via_pair_in_sample")
    out["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == archive_hash)
    return out

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "sites_checked": len(result["via_sites"]),
        "neutral_pairs": sum(x["every_power_zone_exact"]
                              for x in result["via_pairs"]),
        "accepted": False,
        "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

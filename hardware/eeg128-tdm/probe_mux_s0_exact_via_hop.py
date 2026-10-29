#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Scratch-only native KiCad 8.0.9 MUX_S0 via-hop zone exactness screen.

Inventory existing MUX_S0 vias, then test potential new through-via
sites around the CH027/S0 F.Cu crossing. No accepted route, PCB files,
manufacturing files or source copper changes are generated. Both In1.Cu
and EVERY In2.Cu native zone polygon must be byte-geometrically equal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from probe_ch025_fcu_l3_exact import ZONE, track_inventory
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_ch025_neutral_via_sites import (
    polygon_snapshot, polygon_delta, every_zero,
)
from probe_ch027_annulus_s0_native import S0, S0_UUIDS
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import make_via, metrics, native, xy

# Two seed rows spanning both previously observed S0/CH027 crossings,
# no new via is retained; all protected power geometry is still unchanged.
X_MM = (31.20, 31.70, 32.00, 32.50,
        34.60, 35.10, 35.40, 36.00)
Y_MM = (46.50, 47.90)
FLAGS = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "In1_Cu_used": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
    "native_S0_hop_route_qualified": False,
}

def run(candidate: Path) -> dict[str, Any]:
    import pcbnew

    data: dict[str, Any] = {
        **FLAGS,
        "status": "not_started",
        "source_board_sha256": PINNED_CANDIDATE_SHA,
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_archive_unchanged": False,
        "native_baseline": None,
        "original_tracks_and_footprints_unchanged": False,
        "In1_refill_control_exact": False,
        "L3_refill_control_exact": False,
        "existing_S0_vias": [],
        "new_vias_retained": 0,
        "tested_sites": [],
        "tested_pairs": [],
        "candidate_site_count": len(X_MM) * len(Y_MM),
        "single_site_both_layers_exact_count": 0,
        "pair_both_layers_exact_count": 0,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    before_archive = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="MUX-S0-In1-L3-hop-") as tmp:
        folder = Path(tmp)
        with zipfile.ZipFile(candidate) as bundle:
            if set(bundle.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unexpected engineering candidate member")
            audit = json.loads(
                bundle.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Source archive pin mismatch")
            for flag in ("accepted", "routing_completed",
                         "fabrication_release",
                         "routing_replay_byteidentical_verified"):
                if audit.get(flag) is not False:
                    raise RuntimeError("Unsafe engineering release flags")
            for name in MEMBERS:
                (folder / name).write_bytes(bundle.read(name))
        pcb_path = folder / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("MUX_EN/CH019 pinned board hash mismatch")
        baseline = native(pcb_path, folder / "native-baseline.json")
        data["native_baseline"] = metrics(baseline)
        if data["native_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            data["status"] = "baseline_gate_failed"
            return data
        board = pcbnew.LoadBoard(str(pcb_path))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        tracks = {
            track.m_Uuid.AsString(): track
            for track in board.GetTracks()
        }
        for uid in S0_UUIDS:
            original_s0 = tracks.get(uid)
            if (original_s0 is None
                    or original_s0.GetNetname() != S0
                    or original_s0.GetLayer() != pcbnew.F_Cu
                    or isinstance(original_s0, pcbnew.PCB_VIA)):
                raise RuntimeError("Long/short MUX_S0 original changed")
        original_via_ids = {
            track.m_Uuid.AsString()
            for track in board.GetTracks()
            if isinstance(track, pcbnew.PCB_VIA)
        }
        for track in board.GetTracks():
            if (isinstance(track, pcbnew.PCB_VIA)
                    and track.GetNetname() == S0):
                data["existing_S0_vias"].append({
                    "uuid": track.m_Uuid.AsString(),
                    "xy_mm": list(xy(track.GetPosition())),
                    "diameter_mm": pcbnew.ToMM(track.GetWidth()),
                    "through_via": (
                        track.GetViaType() == pcbnew.VIATYPE_THROUGH),
                })
        data["existing_S0_vias"].sort(key=lambda x: x["uuid"])
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        base_in1 = polygon_snapshot(board, pcbnew.In1_Cu)
        base_l3 = polygon_snapshot(board, pcbnew.In2_Cu)
        if ZONE not in base_l3:
            raise RuntimeError("Protected 3V3A L3 polygon missing")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        data["In1_refill_control_exact"] = every_zero(polygon_delta(
            base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
        data["L3_refill_control_exact"] = every_zero(polygon_delta(
            base_l3, polygon_snapshot(board, pcbnew.In2_Cu)))
        if not (data["In1_refill_control_exact"]
                and data["L3_refill_control_exact"]):
            raise RuntimeError("Original power refill is not exact")
        code = board.FindNet(S0).GetNetCode()

        def trial(points: tuple[tuple[float, float], ...]) -> dict[str, Any]:
            new_items: list[Any] = []
            result: dict[str, Any] = {
                "points_mm": [list(pt) for pt in points],
                "native_in1_exact": False,
                "native_l3_exact": False,
                "native_both_layers_exact": False,
                "native_DRC_qualified": False,
                "physical_hop_qualified": False,
            }
            try:
                for point in points:
                    old_uids = {
                        obj.m_Uuid.AsString()
                        for obj in board.GetTracks()
                        if isinstance(obj, pcbnew.PCB_VIA)
                    }
                    make_via(board, point, code, .65)
                    created = [
                        obj for obj in board.GetTracks()
                        if isinstance(obj, pcbnew.PCB_VIA)
                        and obj.m_Uuid.AsString() not in old_uids
                    ]
                    if len(created) != 1:
                        raise RuntimeError("New via isolation failed")
                    new_items.append(created[0])
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                l3 = polygon_delta(
                    base_l3, polygon_snapshot(board, pcbnew.In2_Cu))
                in1 = polygon_delta(
                    base_in1, polygon_snapshot(board, pcbnew.In1_Cu))
                result["native_in1_exact"] = every_zero(in1)
                result["native_l3_exact"] = every_zero(l3)
                result["native_both_layers_exact"] = (
                    every_zero(in1) and every_zero(l3))
                zone_diff = l3[ZONE]
                result["native_3V3A_loss_mm2"] = (
                    zone_diff["loss_native_mm2"])
                result["native_3V3A_gain_mm2"] = (
                    zone_diff["gain_native_mm2"])
            finally:
                for item in reversed(new_items):
                    board.Remove(item)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                if not every_zero(polygon_delta(
                        base_l3, polygon_snapshot(board, pcbnew.In2_Cu))):
                    raise RuntimeError("L3 rollback is not exact")
                if not every_zero(polygon_delta(
                        base_in1, polygon_snapshot(board, pcbnew.In1_Cu))):
                    raise RuntimeError("In1 rollback is not exact")
                after_via_ids = {
                    v.m_Uuid.AsString() for v in board.GetTracks()
                    if isinstance(v, pcbnew.PCB_VIA)
                }
                if after_via_ids != original_via_ids:
                    raise RuntimeError("Unexpected via retained")
            return result

        for y in Y_MM:
            for x in X_MM:
                data["tested_sites"].append(trial(((x, y),)))
        eligible = [
            tuple(row["points_mm"][0]) for row in data["tested_sites"]
            if row["native_both_layers_exact"]
        ]
        data["single_site_both_layers_exact_count"] = len(eligible)
        for i, first in enumerate(eligible[:5]):
            for second in eligible[i + 1:9]:
                data["tested_pairs"].append(trial((first, second)))
                if len(data["tested_pairs"]) >= 12:
                    break
            if len(data["tested_pairs"]) >= 12:
                break
        data["pair_both_layers_exact_count"] = sum(
            row["native_both_layers_exact"]
            for row in data["tested_pairs"])
        data["original_tracks_and_footprints_unchanged"] = (
            track_inventory(board) == original
            and unchanged_fingerprints(board) == protected)
        if not data["original_tracks_and_footprints_unchanged"]:
            raise RuntimeError("Protected original geometry changed")
        data["status"] = (
            "potential_exact_pair_not_routed"
            if data["pair_both_layers_exact_count"]
            else "no_exact_neutral_two_via_pair_in_sample")
    data["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() ==
        before_archive)
    return data

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
        "existing_S0_vias": len(result["existing_S0_vias"]),
        "single_exact_sites": result["single_site_both_layers_exact_count"],
        "pair_exact_sites": result["pair_both_layers_exact_count"],
        "accepted": False,
        "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

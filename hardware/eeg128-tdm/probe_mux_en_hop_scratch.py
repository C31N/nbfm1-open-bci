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
        board.Remove(originals[EN])
        board.Remove(ch019)
        out["CH019_original_track_removed_on_scratch"] = True
        for segment, layer in (
                (L1_SOURCE, pcbnew.F_Cu),
                (L4_MIDDLE, pcbnew.B_Cu),
                (L1_TARGET, pcbnew.F_Cu)):
            for start, end in zip(segment, segment[1:]):
                make_track(board, start, end, netcode, .15, layer)
        make_via(board, WEST, netcode, .65)
        make_via(board, EAST, netcode, .65)
        out["new_vias_added_scratch_only"] = True
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
        out["native_L3_exact_qualified"] = delta["native_both_empty"]
        pcbnew.SaveBoard(str(pcb_path), board)
        # The original project .kicad_pro snapshot is preserved by native().
        post = native(pcb_path, root / "candidate-drc.json")
        out["candidate_native_metrics"] = metrics(post)
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
        out["status"] = "scratch_MUX_EN_hop_native_diagnostic_unqualified"
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

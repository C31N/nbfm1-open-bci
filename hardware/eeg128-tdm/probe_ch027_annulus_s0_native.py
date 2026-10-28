#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Scratch-only CH027 F.Cu annulus landing with two MUX_S0 restorations.

The immutable, SHA-pinned engineering input is never written. Only two
reviewed S0 tracks and the CH027 cut may be removed from disposable boards.
Native DRC and exact native L3 are required; no release or replay claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from analyze_ch025_l3_native_refill import filled
from native_connectivity import regressed_nets
from probe_ch025_cooperative8 import CH027_ALT_VIA, unchanged_fingerprints
from probe_ch025_fcu_l3_exact import ZONE, track_inventory, power_fcu_obstacles
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import make_track, metrics, native, routing_domain, xy
from escape_mesh_505 import mesh_route

CH027 = "CH027_N_MUX"
S0 = "MUX_S0"
CUT = "81777460-c80a-48c9-8608-bae0dd42ee2f"
S0_UUIDS = ("ff9f490d-9f0d-4dc1-96a8-089ed3689134",
            "8a8a90ef-22d5-4e06-96d9-93c2d001cb17")
LANDING = (32.548019, 47.819777)
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "independent_replay_verified": False,
    "schematic_parity_qualified": False, "In1_Cu_used": False,
}

def routed(board: Any, source: tuple[float, float],
           target: tuple[float, float], code: int,
           power: Any, label: str,
           reserved_S0_line: tuple[Any, Any] | None = None
           ) -> tuple[list[Any] | None, dict[str, Any]]:
    import pcbnew
    from shapely.geometry import GeometryCollection, LineString, box
    from shapely.ops import unary_union
    domain = routing_domain(board, .075, .25)
    result: dict[str, Any] = {
        "name": label, "source_mm": list(source), "target_mm": list(target),
        "candidate_FCu_only": True, "new_vias": False,
        "native_DRC_qualified": False, "attempts": [],
        "S0_original_corridor_reserved": reserved_S0_line is not None,
    }
    guard = power_fcu_obstacles(board)
    if reserved_S0_line is not None:
        # Two original S0 endpoints are immutable. Reserve 0.15mm trace
        # plus 0.15mm clearance plus 0.075mm CH027 half-width.
        # This is a prospective routing exclusion, not a DRC exemption.
        guard = unary_union([
            guard, LineString(reserved_S0_line).buffer(.22500001)])
    margins = (2.0, 4.0, 7.0) if reserved_S0_line else (2.0, 4.0)
    for margin in margins:
        region = domain.intersection(box(
            min(source[0], target[0]) - margin,
            min(source[1], target[1]) - margin,
            max(source[0], target[0]) + margin,
            max(source[1], target[1]) + margin))
        proposal = mesh_route(
            board, source, target, code,
            (pcbnew.F_Cu, pcbnew.B_Cu), power, region,
            start_layer=0, goal_layer=0, allow_vias=False,
            extra_obstacles=[guard, GeometryCollection()])
        valid = (
            proposal is not None and len(proposal) >= 2
            and tuple(proposal[0]) == (0, *source)
            and tuple(proposal[-1]) == (0, *target)
            and all(p[0] == 0 for p in proposal))
        result["attempts"].append({
            "margin_mm": margin, "proposal_found": bool(valid),
            "vertex_count": len(proposal) if valid else 0})
        if valid:
            result["vertices"] = [list(p) for p in proposal]
            result["route_length_mm"] = sum(
                math.dist(a[1:], b[1:])
                for a, b in zip(proposal, proposal[1:]))
            return proposal, result
    return None, result


def run(candidate: Path, order_index: int) -> dict[str, Any]:
    import pcbnew
    out: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started",
        "candidate_source_sha256": PINNED_CANDIDATE_SHA,
        "original_candidate_unchanged": False,
        "source_archive_139_sha256": ARCHIVE_SHA256,
        "native_139_baseline": None,
        "native_L3_exact_zero": False,
        "protected_originals_unchanged": False,
        "candidate_native_DRC_qualified": False,
        "trials": [],
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    archive_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="ch027-s0-annulus-native-") as td:
        root = Path(td)
        original = root / MEMBERS[0]
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != set(MEMBERS) | {
                    "NO_RELEASE_ENGINEERING_ONLY.json"}:
                raise RuntimeError("Unreviewed candidate archive members")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 archive identity mismatch")
            for k in ("accepted", "routing_completed", "fabrication_release",
                      "routing_replay_byteidentical_verified"):
                if audit.get(k) is not False:
                    raise RuntimeError("Engineering input promoted unexpectedly")
            for member in MEMBERS:
                (root / member).write_bytes(z.read(member))
        if hashlib.sha256(original.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Locked MUX_EN/CH019 candidate hash mismatch")
        baseline = native(original, root / "baseline-native.json")
        out["native_139_baseline"] = metrics(baseline)
        if out["native_139_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "native_baseline_gate_failed"
            return out

        schedules = (
            (S0_UUIDS, False), (S0_UUIDS[::-1], False),
            (S0_UUIDS, True), (S0_UUIDS[::-1], True),
        )
        # KiCad 8 SWIG BOARD_ITEM references may become dangling when
        # an earlier BOARD is garbage-collected before a later load.
        # Retain every disposable board until the temporary workspace exits.
        retained_boards: list[Any] = []
        if order_index not in range(len(schedules)):
            raise ValueError('Unreviewed isolated routing order')
        for index, (order, reserve_S0) in enumerate(schedules):
            if index != order_index:
                continue
            board = pcbnew.LoadBoard(str(original))
            retained_boards.append(board)
            before = track_inventory(board)
            protected = unchanged_fingerprints(board)
            current = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
            chosen = {CUT: (CH027, pcbnew.F_Cu),
                      **{uid: (S0, pcbnew.F_Cu) for uid in S0_UUIDS}}
            for uid, (net, layer) in chosen.items():
                item = current.get(uid)
                if (item is None or item.GetNetname() != net
                        or item.GetLayer() != layer
                        or isinstance(item, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                    raise RuntimeError("Unreviewed scratch ripup " + uid)
            via = current.get(CH027_ALT_VIA)
            if (not isinstance(via, pcbnew.PCB_VIA)
                    or via.GetNetname() != CH027
                    or math.dist(xy(via.GetPosition()), LANDING) >=
                    pcbnew.ToMM(via.GetWidth()) / 2 - .01):
                raise RuntimeError("Existing CH027 via copper contact changed")
            zone = next((z for z in board.Zones()
                         if z.m_Uuid.AsString() == ZONE
                         and z.IsOnLayer(pcbnew.In2_Cu)
                         and z.GetNetname() == "3V3A"), None)
            if zone is None:
                raise RuntimeError("Protected 3V3A L3 zone not found")
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            l3_before = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            # SWIG BOARD_ITEM pointers must never be dereferenced after
            # board.Remove(): freeze exact original start/end coordinates.
            frozen_endpoints = {
                uid: (xy(current[uid].GetStart()),
                      xy(current[uid].GetEnd()))
                for uid in chosen
            }
            row: dict[str, Any] = {
                "order": list(order), "status": "not_started",
                "S0_long_corridor_reserved_before_CH027": reserve_S0,
                "scratch_only": True, "no_new_vias": True,
                "candidate_native_DRC_qualified": False,
                "accepted": False, "fabrication_release": False,
                "routing_completed": False, "routes": [],
            }
            for uid in chosen:
                board.Remove(current[uid])
            power = filled(zone)
            ch027_code = board.FindNet(CH027).GetNetCode()
            start = frozen_endpoints[CUT][0]
            reservation = (
                frozen_endpoints[S0_UUIDS[0]]
                if reserve_S0 else None)
            proposed, detail = routed(
                board, start, LANDING, ch027_code, power,
                "CH027_FCu_annulus", reserved_S0_line=reservation)
            row["routes"].append(detail)
            if proposed is None:
                row["status"] = "CH027_annulus_FCu_mesh_missing"
                out["trials"].append(row)
                continue
            for a, b in zip(proposed, proposed[1:]):
                make_track(board, tuple(a[1:]), tuple(b[1:]),
                           ch027_code, .15, pcbnew.F_Cu)

            all_s0_restored = True
            for uid in order:
                source, destination = frozen_endpoints[uid]
                proposed, detail = routed(
                    board, source, destination,
                    board.FindNet(S0).GetNetCode(), power,
                    "MUX_S0_" + uid)
                row["routes"].append(detail)
                if proposed is None:
                    all_s0_restored = False
                    row["status"] = "MUX_S0_restitution_mesh_missing"
                    break
                for a, b in zip(proposed, proposed[1:]):
                    make_track(board, tuple(a[1:]), tuple(b[1:]),
                               board.FindNet(S0).GetNetCode(),
                               .15, pcbnew.F_Cu)
            if not all_s0_restored:
                out["trials"].append(row)
                continue
            after = track_inventory(board)
            if any(after.get(uid) != item for uid, item in before.items()
                   if uid not in chosen):
                raise RuntimeError("An unreviewed original track was changed")
            if unchanged_fingerprints(board) != protected:
                raise RuntimeError("Protected via/pad/zone changed")
            original_vias = {uid for uid, vals in before.items()
                             if vals[-1] == "PCB_VIA"}
            new_vias = {t.m_Uuid.AsString() for t in board.GetTracks()
                        if isinstance(t, pcbnew.PCB_VIA)}
            if new_vias != original_vias:
                raise RuntimeError("A new or removed via violates zero-via gate")
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            native_l3 = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            delta = exact_native_difference(l3_before, native_l3)
            row["L3_loss_mm2"] = delta["loss_native_mm2"]
            row["L3_gain_mm2"] = delta["gain_native_mm2"]
            row["L3_native_exact_zero"] = delta["native_both_empty"]
            if not delta["native_both_empty"]:
                row["status"] = "native_L3_exact_zero_failed"
                out["trials"].append(row)
                continue
            scratchdir = root / ("CH027_S0_order_" + str(index))
            scratchdir.mkdir()
            for member in MEMBERS[1:]:
                shutil.copyfile(root / member, scratchdir / member)
            scratch = scratchdir / MEMBERS[0]
            pcbnew.SaveBoard(str(scratch), board)
            post = native(scratch, root / ("post-" + str(index) + ".json"))
            row["candidate_native_DRC"] = metrics(post)
            row["regressed_nets"] = regressed_nets(baseline, post)
            row["candidate_native_DRC_qualified"] = (
                metrics(post)["violations"] == 0
                and metrics(post)["warnings"] == 0
                and metrics(post)["unconnected"] < 139
                and not row["regressed_nets"])
            row["status"] = (
                "CH027_S0_native_DRC_pass_no_checkpoint_promotion"
                if row["candidate_native_DRC_qualified"]
                else "CH027_S0_native_DRC_or_connectivity_gate_failed")
            out["trials"].append(row)
            if row["candidate_native_DRC_qualified"]:
                out["candidate_native_DRC_qualified"] = True
                out["native_L3_exact_zero"] = True
                out["protected_originals_unchanged"] = True
                break
        out["status"] = (
            "CH027_annulus_physical_scratch_qualified_no_release"
            if out["candidate_native_DRC_qualified"]
            else "CH027_annulus_physical_scratch_not_qualified")
    out["original_candidate_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == archive_hash)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--order-index', type=int, choices=(0, 1, 2, 3), required=True)
    args = parser.parse_args()
    report = run(args.candidate, args.order_index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"],
                      "qualified": report["candidate_native_DRC_qualified"],
                      "accepted": False, "fabrication_release": False}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Scratch-only, pinned MUX_EN four-via multihop and CH019 restitution.

This diagnostic NEVER promotes checkpoint, never writes the source archive
and never exports fabrication files. It fails closed on every routing gate.
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
    pinned_items, unchanged_fingerprints, CH027_ALT_VIA,
)
from probe_ch025_fcu_l3_exact import track_inventory, power_fcu_obstacles
from analyze_ch025_l3_precision_mask import exact_native_difference
from probe_mux_topological_capacity import TERMINALS
from route_targeted_closure import (
    routing_domain, make_via, make_track, native, metrics, xy,
)
from escape_mesh_505 import mesh_route

WEST = (28.5, 33.75)
A = (28.487502, 34.7)
B = (34.805097, 42.25221)
EAST = (36.75, 34.0)
CH019_CUT = "0832ca70-347c-5b2d-b8d9-c8fff7096f8a"
EN = "MUX_EN"
CH019 = "CH019_N_MUX"
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
    "checkpoint_promoted": False, "In1_Cu_used": False,
}


def find_leg(board: Any, en: int, power: Any, name: str,
             start: tuple[float, float], target: tuple[float, float],
             layer: int, bounds: tuple[float, float, float, float],
             fcu_guard: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import GeometryCollection, box

    domain = routing_domain(board, .075, .25)
    region = domain.intersection(box(*bounds))
    if layer == pcbnew.F_Cu:
        layers = (pcbnew.F_Cu, pcbnew.B_Cu)
        extras = [fcu_guard, GeometryCollection()]
    elif layer == pcbnew.B_Cu:
        layers = (pcbnew.B_Cu, pcbnew.F_Cu)
        extras = [GeometryCollection(), fcu_guard]
    else:
        raise RuntimeError("In1.Cu and In2.Cu signal tracks forbidden")
    route = mesh_route(
        board, start, target, en, layers, power, region,
        start_layer=0, goal_layer=0, allow_vias=False,
        extra_obstacles=extras)
    valid = (
        route is not None and len(route) >= 2
        and tuple(route[0]) == (0, *start)
        and tuple(route[-1]) == (0, *target)
        and all(point[0] == 0 for point in route)
        and all(math.dist(p[1:], q[1:]) > .000001
                for p, q in zip(route, route[1:])))
    return {
        "name": name,
        "layer": "F.Cu" if layer == pcbnew.F_Cu else "B.Cu",
        "route_found": bool(valid),
        "route_vertices": [list(point) for point in route] if valid else [],
        "route_length_mm": (
            sum(math.dist(p[1:], q[1:])
                for p, q in zip(route, route[1:]))
            if valid else None),
        "DRC_qualified": False,
        "power_gate_qualified": False,
    }


def run(archive: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from analyze_ch025_l3_native_refill import filled
    from native_connectivity import regressed_nets

    out: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started",
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_pcb_sha256": BOARD_SHA256,
        "source_139_PCB_untouched": False,
        "protected_original_tracks_unchanged": False,
        "protected_original_vias_pads_zones_unchanged": False,
        "CH027_fixed_via_unchanged": False,
        "native_139_baseline": None,
        "target_136_not_promoted": True,
        "candidate_native_DRC": None,
        "candidate_regressed_nets": None,
        "native_L3_loss_mm2": None,
        "native_L3_gain_mm2": None,
        "native_L3_both_difference_sets_empty": False,
        "full_MUX_EN_multihop_routed_on_scratch": False,
        "CH019_BCu_restituted_on_scratch": False,
        "leg_diagnostics": [],
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Native KiCad 8.0.9 is required")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("Pinned 139 archive mismatch")
    with tempfile.TemporaryDirectory(prefix="mux-en-four-via-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as source:
            if sorted(source.namelist()) != sorted(MEMBERS):
                raise RuntimeError("Pinned PCB package contents mismatch")
            for name in MEMBERS:
                (root / name).write_bytes(source.read(name))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != BOARD_SHA256:
            raise RuntimeError("Original 139 PCB SHA mismatch")
        baseline = native(pcb_path, root / "native-baseline.json")
        out["native_139_baseline"] = metrics(baseline)
        if metrics(baseline) != {
            "violations": 0, "warnings": 0, "unconnected": 139,
        }:
            out["status"] = "source_native_DRC_baseline_mismatch"
            return out

        board = pcbnew.LoadBoard(str(pcb_path))
        pinned, zone, _ = pinned_items(board)
        current_tracks = track_inventory(board)
        before_protected = unchanged_fingerprints(board)
        netcode = board.FindNet(EN).GetNetCode()
        old_en = pinned[EN]
        ch019 = next((item for item in board.GetTracks()
                      if item.m_Uuid.AsString() == CH019_CUT
                      and item.GetNetname() == CH019
                      and item.GetLayer() == pcbnew.B_Cu
                      and not isinstance(item, (pcbnew.PCB_VIA,
                                                pcbnew.PCB_ARC))), None)
        if ch019 is None:
            raise RuntimeError("Original CH019 reviewed track not found")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        before_l3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        if not before_l3.OutlineCount():
            raise RuntimeError("Pinned L3 3V3A polygon missing")
        board.Remove(old_en)
        board.Remove(ch019)
        try:
            for at in (WEST, A, B, EAST):
                make_via(board, at, netcode, .65)
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            refilled = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            before_routes = exact_native_difference(before_l3, refilled)
            out["native_L3_zero_after_four_vias"] = (
                before_routes["native_both_empty"])
            if not before_routes["native_both_empty"]:
                out["status"] = "cumulative_four_via_L3_gate_failed"
                return out

            power = filled(zone)
            controls = unary_union([
                LineString(TERMINALS[name]).buffer(.22501)
                for name in ("MUX_S2", "MUX_S3")
            ])
            fguard = unary_union([controls, power_fcu_obstacles(board)])
            legs = (
                ("source_to_WEST", TERMINALS[EN][0], WEST, pcbnew.F_Cu,
                 (19.0, 27.0, 50.0, 48.0)),
                ("WEST_to_A", WEST, A, pcbnew.B_Cu,
                 (25.0, 30.5, 32.0, 38.0)),
                ("A_to_B_bridge", A, B, pcbnew.F_Cu,
                 (18.0, 21.0, 55.0, 65.0)),
                ("B_to_EAST", B, EAST, pcbnew.B_Cu,
                 (19.0, 27.0, 52.0, 56.0)),
                ("EAST_to_target", EAST, TERMINALS[EN][1], pcbnew.F_Cu,
                 (30.0, 29.0, 50.0, 45.0)),
            )
            for name, start, target, layer, bounds in legs:
                row = find_leg(
                    board, netcode, power, name, start, target,
                    layer, bounds, fguard)
                out["leg_diagnostics"].append(row)
                if not row["route_found"]:
                    out["status"] = "one_of_five_fixed_multihop_mesh_legs_missing"
                    return out
                vertices = [tuple(point[1:])
                            for point in row["route_vertices"]]
                for p, q in zip(vertices, vertices[1:]):
                    make_track(board, p, q, netcode, .15, layer)
            out["full_MUX_EN_multihop_routed_on_scratch"] = True

            ch019_code = board.FindNet(CH019).GetNetCode()
            start = xy(ch019.GetStart())
            target = xy(ch019.GetEnd())
            ch019_route = mesh_route(
                board, start, target, ch019_code,
                (pcbnew.B_Cu, pcbnew.F_Cu), power,
                routing_domain(board, .075, .25).intersection(
                    box(27.0, 30.0, 51.0, 52.0)),
                start_layer=0, goal_layer=0, allow_vias=False)
            if (ch019_route is None or len(ch019_route) < 2
                    or tuple(ch019_route[0]) != (0, *start)
                    or tuple(ch019_route[-1]) != (0, *target)
                    or any(point[0] != 0 for point in ch019_route)):
                out["status"] = "CH019_BCu_restitution_mesh_missing"
                return out
            coordinates = [tuple(x[1:]) for x in ch019_route]
            for a, b in zip(coordinates, coordinates[1:]):
                make_track(board, a, b, ch019_code, .15, pcbnew.B_Cu)
            out["CH019_BCu_restituted_on_scratch"] = True
            out["CH019_BCu_restitution_vertices"] = len(coordinates)
            out["CH019_BCu_restitution_length_mm"] = sum(
                math.dist(a, b) for a, b in zip(
                    coordinates, coordinates[1:]))

            modified = track_inventory(board)
            removed = {old_en.m_Uuid.AsString(), CH019_CUT}
            if any(modified.get(uid) != props for uid, props
                   in current_tracks.items() if uid not in removed):
                raise RuntimeError("Protected original track UUID modified")
            out["protected_original_tracks_unchanged"] = True
            after_originals = unchanged_fingerprints(board)
            original_vias = {
                row[0]: row for row in before_protected["vias"]}
            new_vias = {
                row[0]: row for row in after_originals["vias"]}
            if (after_originals["pads"] != before_protected["pads"]
                    or after_originals["zones"] != before_protected["zones"]
                    or any(new_vias.get(uid) != row
                           for uid, row in original_vias.items())):
                raise RuntimeError("Protected pad/via/zone changed")
            out["protected_original_vias_pads_zones_unchanged"] = True
            out["CH027_fixed_via_unchanged"] = (
                CH027_ALT_VIA in original_vias and
                new_vias.get(CH027_ALT_VIA) ==
                original_vias[CH027_ALT_VIA])
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            after_l3 = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            delta = exact_native_difference(before_l3, after_l3)
            out["native_L3_loss_mm2"] = delta["loss_native_mm2"]
            out["native_L3_gain_mm2"] = delta["gain_native_mm2"]
            out["native_L3_both_difference_sets_empty"] = (
                delta["native_both_empty"])
            if not delta["native_both_empty"]:
                out["status"] = "route_refill_L3_exact_gate_failed"
                return out
            pcbnew.SaveBoard(str(pcb_path), board)
            post = native(pcb_path, root / "candidate-native-DRC.json")
            out["candidate_native_DRC"] = metrics(post)
            out["candidate_regressed_nets"] = regressed_nets(
                baseline, post)
            out["candidate_native_DRC_qualified"] = (
                metrics(post)["violations"] == 0
                and metrics(post)["warnings"] == 0
                and not out["candidate_regressed_nets"])
            out["status"] = (
                "full_MUX_EN_CH019_scratch_native_DRC_pass_no_promotion"
                if out["candidate_native_DRC_qualified"]
                else "full_MUX_EN_CH019_scratch_native_DRC_failed")
        finally:
            # All writes were restricted to the TemporaryDirectory
            # board instance and never persist to the source ZIP.
            out["source_139_PCB_untouched"] = (
                hashlib.sha256(archive.read_bytes()).hexdigest() ==
                ARCHIVE_SHA256)
    return out


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
        "five_leg_results": [x["route_found"]
                             for x in result["leg_diagnostics"]],
        "candidate_native_DRC": result["candidate_native_DRC"],
        "accepted": False, "fabrication_release": False,
    }))

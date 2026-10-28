#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only feasibility of remaining reviewed MUX F.Cu links after EN multihop.

All tests use a SHA-locked unaccepted engineering source candidate. Each
original reviewed copper segment is removed in memory ONE AT A TIME and
restored before trying the next. No PCB is saved and no manufacture exported.
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

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from probe_ch025_neighbor_restitution7 import NEIGHBORS, UNCHANGED
from probe_ch025_fcu_l3_exact import (
    CUT, NET, track_inventory, power_fcu_obstacles,
)
from probe_ch025_cooperative8 import CH027_ALT_TARGET, unchanged_fingerprints
from route_targeted_closure import native, metrics, xy

PINNED_CANDIDATE_SHA = (
    "b42e81b37971cec3e88382392026de3f6b2e45498b6af98810779478fc35a348"
)
FIXED_S2_S3 = ("MUX_S2", "MUX_S3")
OTHER_FCU = ("MUX_S0", "MUX_S1", "CH027_N_MUX", "CH030_P_MUX")
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "independent_full_block_replay_verified": False,
    "schematic_parity_qualified": False,
    "full_136_gate_qualified": False,
    "In1_Cu_used": False,
}


def probe(candidate: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import GeometryCollection, box
    from escape_mesh_505 import mesh_route
    from route_targeted_closure import routing_domain
    from analyze_ch025_l3_native_refill import filled

    out: dict[str, Any] = {
        **NO_RELEASE,
        "status": "not_started",
        "reviewed_source_139_archive_sha256": ARCHIVE_SHA256,
        "reviewed_candidate_pcb_sha256": PINNED_CANDIDATE_SHA,
        "original_candidate_archive_untouched": False,
        "strict_native_baseline_DRC": None,
        "protected_originals_restituted": False,
        "S2_S3_originals_preserved": False,
        "remaining_mux_fcu_trials": [],
        "all_five_FCu_geometry_proposed": False,
        "native_whole_block_DRC_qualified": False,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    initial_archive_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="mux-en-remaining-fcu-") as td:
        root = Path(td)
        with zipfile.ZipFile(candidate) as src:
            if set(src.namelist()) != set(MEMBERS) | {
                    "NO_RELEASE_ENGINEERING_ONLY.json"}:
                raise RuntimeError("Unreviewed engineering candidate members")
            audit = json.loads(src.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if (audit.get("accepted") is not False
                    or audit.get("routing_completed") is not False
                    or audit.get("fabrication_release") is not False
                    or audit.get("source_archive_sha256") != ARCHIVE_SHA256):
                raise RuntimeError("Unreviewed promotion/audit flags")
            for member in MEMBERS:
                (root / member).write_bytes(src.read(member))
        board_path = root / MEMBERS[0]
        if hashlib.sha256(board_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Wrong byte-pinned four-via native PCB")
        drc = native(board_path, root / "source-drc.json")
        out["strict_native_baseline_DRC"] = metrics(drc)
        if metrics(drc) != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "native_engineering_candidate_baseline_failed"
            return out
        board = pcbnew.LoadBoard(str(board_path))
        before = track_inventory(board)
        fingerprints = unchanged_fingerprints(board)
        copper = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        for uid, net in UNCHANGED.items():
            if uid not in copper or copper[uid].GetNetname() != net:
                raise RuntimeError("Untouchable neighbor original missing")
        candidates = {}
        for uid, net in NEIGHBORS.items():
            if net == "MUX_EN":
                if uid in copper:
                    raise RuntimeError("Multihop unexpectedly retained old EN")
                continue
            if (uid not in copper or copper[uid].GetNetname() != net
                    or copper[uid].GetLayer() != pcbnew.F_Cu
                    or isinstance(copper[uid], (pcbnew.PCB_VIA,
                                                pcbnew.PCB_ARC))):
                raise RuntimeError("Reviewed FCu neighbor identity changed")
            candidates[net] = copper[uid]
        if not (set(candidates) == set(OTHER_FCU) | set(FIXED_S2_S3)
                and CUT in copper
                and copper[CUT].GetNetname() == NET
                and copper[CUT].GetLayer() == pcbnew.In2_Cu):
            raise RuntimeError("Reviewed CH025 or MUX neighbor set changed")
        out["S2_S3_originals_preserved"] = all(
            before[uid][0] == net for uid, net in NEIGHBORS.items()
            if net in FIXED_S2_S3)

        targets = [(net, candidates[net]) for net in OTHER_FCU]
        targets.append((NET, copper[CUT]))
        domain = routing_domain(board, .075, .25)
        zone = next((z for z in board.Zones()
                     if z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Missing native 3V3A power zone")
        power = filled(zone)
        for name, original in targets:
            if name == NET:
                source = (49.45, 14.90)
                goal = (36.105, 48.85)
            elif name == "CH027_N_MUX":
                source = xy(original.GetStart())
                goal = CH027_ALT_TARGET
            else:
                source = xy(original.GetStart())
                goal = xy(original.GetEnd())
            row: dict[str, Any] = {
                "net": name,
                "reviewed_copper_UUID": original.m_Uuid.AsString(),
                "source_xy_mm": list(source),
                "goal_xy_mm": list(goal),
                "F_Cu_only": True,
                "new_vias": False,
                "mesh_geometry_found": False,
                "native_candidate_DRC_qualified": False,
                "native_L3_gate_qualified": False,
                "original_copper_restored": False,
                "attempts": [],
            }
            board.Remove(original)
            try:
                from shapely.geometry import Point
                if not (domain.covers(Point(source))
                        and domain.covers(Point(goal))):
                    row["status"] = "terminal_outside_board_edge_domain"
                else:
                    for margin in (3.0, 6.0):
                        region = domain.intersection(
                            box(min(source[0], goal[0]) - margin,
                                min(source[1], goal[1]) - margin,
                                max(source[0], goal[0]) + margin,
                                max(source[1], goal[1]) + margin))
                        route = mesh_route(
                            board, source, goal, original.GetNetCode(),
                            (pcbnew.F_Cu, pcbnew.B_Cu), power, region,
                            start_layer=0, goal_layer=0, allow_vias=False,
                            extra_obstacles=[
                                power_fcu_obstacles(board),
                                GeometryCollection()])
                        found = (
                            route is not None and len(route) > 1
                            and tuple(route[0]) == (0, *source)
                            and tuple(route[-1]) == (0, *goal)
                            and all(p[0] == 0 for p in route))
                        row["attempts"].append({
                            "margin_mm": margin, "route_found": found,
                            "vertex_count": len(route) if found else 0})
                        if found:
                            row["mesh_geometry_found"] = True
                            row["path_mm"] = [
                                [float(p[1]), float(p[2])] for p in route]
                            row["length_mm"] = sum(
                                math.dist(a[1:], b[1:])
                                for a, b in zip(route, route[1:]))
                            break
                    row["status"] = (
                        "FCu_mesh_geometry_not_DRC_qualified"
                        if row["mesh_geometry_found"]
                        else "no_FCu_mesh_in_reviewed_margin")
            finally:
                board.Add(original)
                if track_inventory(board) != before:
                    raise RuntimeError("Original reviewed MUX track not restored")
                row["original_copper_restored"] = True
            out["remaining_mux_fcu_trials"].append(row)
        if unchanged_fingerprints(board) != fingerprints:
            raise RuntimeError("Protected vias, pads or zone fingerprints changed")
        out["protected_originals_restituted"] = (
            track_inventory(board) == before)
        out["all_five_FCu_geometry_proposed"] = all(
            row["mesh_geometry_found"]
            for row in out["remaining_mux_fcu_trials"])
        out["status"] = "read_only_remaining_FCu_mesh_audit_no_promotion"
    out["original_candidate_archive_untouched"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() ==
        initial_archive_sha)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = probe(args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"],
                      "proposals_found": sum(
                          row["mesh_geometry_found"] for row in
                          report["remaining_mux_fcu_trials"]),
                      "accepted": False, "fabrication_release": False}))


if __name__ == "__main__":
    main()

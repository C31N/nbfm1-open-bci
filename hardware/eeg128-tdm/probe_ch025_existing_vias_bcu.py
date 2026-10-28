#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Existing CH025 through-via, B.Cu-only escape feasibility and native gates.

All four UUID-pinned CH025 vias are immutable. No new vias, no In1.Cu
tracks, no changes to unrelated originals. Only temporary PCB copies.
Mesh proposals are not accepted without exact native refill and DRC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from analyze_ch025_l3_native_refill import filled
from escape_mesh_505 import mesh_route, polygons
from native_connectivity import regressed_nets
from probe_ch025_cooperative8 import SRC_VIA, DST_VIA, unchanged_fingerprints
from probe_ch025_fcu_l3_exact import CUT, NET, ZONE, track_inventory
from probe_ch025_neutral_via_sites import polygon_snapshot, polygon_delta, every_zero
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    POWER, make_track, metrics, native, pad_copper_shape,
    routing_domain, xy,
)

SRC_ALT_VIA = "6040bdea-9da3-44af-9e52-227de6f931c8"
DST_ALT_VIA = "dbdd22b2-65d2-47f7-aaf7-bae5ec14caa8"
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "In1_Cu_used": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
}

def bcu_power_copper_guard(board: Any) -> Any:
    import pcbnew
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    shapes = []
    for track in board.GetTracks():
        if track.GetNetname() not in POWER:
            continue
        width = pcbnew.ToMM(track.GetWidth()) / 2
        if isinstance(track, pcbnew.PCB_VIA):
            shapes.append(Point(xy(track.GetPosition())).buffer(
                width + .505 + .075))
        elif track.GetLayer() == pcbnew.B_Cu:
            shapes.append(LineString((
                xy(track.GetStart()), xy(track.GetEnd()))).buffer(
                    width + .505 + .075))
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if (pad.GetNetname() in POWER and
                    pad.IsOnLayer(pcbnew.B_Cu)):
                shapes.append(pad_copper_shape(
                    pad, pcbnew.B_Cu).buffer(.505 + .075))
    return unary_union(shapes) if shapes else Point().buffer(0)

def run(candidate: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from shapely.strtree import STRtree
    from probe_ch025_ch027_transition import component_index
    from route_targeted_closure import obstacles

    report: dict[str, Any] = {
        **NO_RELEASE,
        "status": "not_started",
        "139_source_sha256": PINNED_CANDIDATE_SHA,
        "baseline_native_DRC": None,
        "source_archive_unchanged": False,
        "protected_originals_preserved": False,
        "native_in1_zero": False,
        "native_l3_zero": False,
        "new_via_count": 0,
        "physical_BCu_route_qualified": False,
        "candidate_routes": [],
        "existing_CH025_vias": [],
        "BCu_component_count": 0,
        "BCu_direct_component_pair_count": 0,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    raw_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="CH025-existing-via-") as tmp:
        folder = Path(tmp)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unexpected engineering candidate members")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Pinned source archive SHA changed")
            for key in ("accepted", "fabrication_release",
                        "routing_completed", "routing_replay_byteidentical_verified"):
                if audit.get(key) is not False:
                    raise RuntimeError("Candidate already promoted")
            for name in MEMBERS:
                (folder / name).write_bytes(z.read(name))
        pcb_path = folder / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("Pinned MUX_EN/CH019 scratch board mismatch")
        baseline = native(pcb_path, folder / "baseline-Drc.json")
        report["baseline_native_DRC"] = metrics(baseline)
        if report["baseline_native_DRC"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            report["status"] = "baseline_139_not_verified"
            return report
        board = pcbnew.LoadBoard(str(pcb_path))
        before = track_inventory(board)
        protected = unchanged_fingerprints(board)
        tracks = {track.m_Uuid.AsString(): track
                  for track in board.GetTracks()}
        cut = tracks.get(CUT)
        if (cut is None or cut.GetNetname() != NET or
                cut.GetLayer() != pcbnew.In2_Cu
                or isinstance(cut, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise RuntimeError("CH025 In2 existing cut identity mismatch")
        via_ids = (SRC_VIA, SRC_ALT_VIA, DST_VIA, DST_ALT_VIA)
        positions = {}
        for uid in via_ids:
            via = tracks.get(uid)
            if (not isinstance(via, pcbnew.PCB_VIA)
                    or via.GetNetname() != NET
                    or via.GetViaType() != pcbnew.VIATYPE_THROUGH):
                raise RuntimeError("Unapproved CH025 via " + uid)
            positions[uid] = xy(via.GetPosition())
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        base_in1 = polygon_snapshot(board, pcbnew.In1_Cu)
        base_l3 = polygon_snapshot(board, pcbnew.In2_Cu)
        if ZONE not in base_l3:
            raise RuntimeError("3V3A L3 zone missing")
        domain = routing_domain(board, .075, .25)
        region = domain.intersection(box(24.0, 8.0, 57.0, 57.0))
        code = board.FindNet(NET).GetNetCode()
        obstacles_pair, _ = obstacles(
            board, code, .15, .15, region, .65,
            (pcbnew.B_Cu, pcbnew.F_Cu))
        power_guard = bcu_power_copper_guard(board)
        safe = region.difference(
            obstacles_pair[0].union(power_guard)).buffer(-.000005)
        parts = polygons(safe)
        tree = STRtree(parts)
        for uid in via_ids:
            point = Point(positions[uid])
            idx = component_index(tree, parts, point)
            annulus = point.buffer(.325 - .01)
            contacts = [j for j, geom in enumerate(parts)
                        if geom.intersects(annulus)]
            report["existing_CH025_vias"].append({
                "uuid": uid, "xy_mm": list(positions[uid]),
                "BCu_centre_component": idx,
                "BCu_annulus_components": contacts,
            })
        report["BCu_component_count"] = len(parts)
        report["BCu_direct_component_pair_count"] = sum(
            bool(set(next(x for x in report["existing_CH025_vias"]
                          if x["uuid"] == a)["BCu_annulus_components"]) &
                 set(next(x for x in report["existing_CH025_vias"]
                          if x["uuid"] == b)["BCu_annulus_components"]))
            for a in (SRC_VIA, SRC_ALT_VIA)
            for b in (DST_VIA, DST_ALT_VIA))
        # No new layer changes are allowed; F.Cu is explicitly an unused
        # second routing mesh layer needed by the two-layer mesh library.
        guard_fcu = GeometryCollection()
        power = filled(next(z for z in board.Zones()
                            if z.m_Uuid.AsString() == ZONE))
        for source_uid in (SRC_VIA, SRC_ALT_VIA):
            for target_uid in (DST_VIA, DST_ALT_VIA):
                source = positions[source_uid]
                target = positions[target_uid]
                row: dict[str, Any] = {
                    "source_uuid": source_uid, "target_uuid": target_uid,
                    "source_mm": list(source), "target_mm": list(target),
                    "BCu_route_proposed": False,
                    "native_DRC_qualified": False,
                    "no_new_vias": True, "In1_Cu_used": False,
                    "mesh_margin_mm": None,
                }
                for margin in (3.0, 8.0):
                    bounds = box(min(source[0], target[0]) - margin,
                                 min(source[1], target[1]) - margin,
                                 max(source[0], target[0]) + margin,
                                 max(source[1], target[1]) + margin)
                    path = mesh_route(
                        board, source, target, code,
                        (pcbnew.B_Cu, pcbnew.F_Cu), power,
                        region.intersection(bounds),
                        start_layer=0, goal_layer=0, allow_vias=False,
                        extra_obstacles=[power_guard, guard_fcu])
                    if (path is None or len(path) < 2 or
                            any(p[0] != 0 for p in path)):
                        continue
                    row["BCu_route_proposed"] = True
                    row["mesh_margin_mm"] = margin
                    row["BCu_route_mm"] = [list(p) for p in path]
                    break
                report["candidate_routes"].append(row)
                if not row["BCu_route_proposed"]:
                    continue
                # Physical scratch-only gate: test first legal route, never
                # advance a checkpoint without the complete three-net closure.
                for a, b in zip(path, path[1:]):
                    make_track(board, tuple(a[1:]), tuple(b[1:]),
                               code, .15, pcbnew.B_Cu)
                board.Remove(cut)
                after = track_inventory(board)
                if any(after.get(uid) != info for uid, info in before.items()
                       if uid != CUT):
                    raise RuntimeError("Protected original track modified")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Protected vias, pads or zones changed")
                originals = {u for u, vals in before.items()
                             if vals[-1] == "PCB_VIA"}
                now = {t.m_Uuid.AsString() for t in board.GetTracks()
                       if isinstance(t, pcbnew.PCB_VIA)}
                if originals != now:
                    raise RuntimeError("New via prohibited")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                delta_l3 = polygon_delta(
                    base_l3, polygon_snapshot(board, pcbnew.In2_Cu))
                delta_in1 = polygon_delta(
                    base_in1, polygon_snapshot(board, pcbnew.In1_Cu))
                row["L3_exact_zero"] = every_zero(delta_l3)
                row["In1_exact_zero"] = every_zero(delta_in1)
                native_3v3a = exact_native_difference(
                    base_l3[ZONE],
                    polygon_snapshot(board, pcbnew.In2_Cu)[ZONE])
                row["native_3V3A_delta"] = {
                    k: native_3v3a[k]
                    for k in ("loss_native_mm2", "gain_native_mm2",
                              "native_both_empty")}
                if not (row["L3_exact_zero"] and row["In1_exact_zero"]):
                    row["status"] = "physical_path_zone_gate_failed"
                    break
                scratchdir = folder / "scratch"
                scratchdir.mkdir()
                for item in MEMBERS[1:]:
                    shutil.copyfile(folder / item, scratchdir / item)
                scratch = scratchdir / MEMBERS[0]
                pcbnew.SaveBoard(str(scratch), board)
                post = native(scratch, folder / "post-DRC.json")
                row["native_DRC"] = metrics(post)
                row["regressed_nets"] = regressed_nets(baseline, post)
                row["native_DRC_qualified"] = (
                    metrics(post)["violations"] == 0
                    and metrics(post)["warnings"] == 0
                    and metrics(post)["unconnected"] < 139
                    and not row["regressed_nets"])
                report["physical_BCu_route_qualified"] = (
                    row["native_DRC_qualified"])
                break
        if not any(row["BCu_route_proposed"] for row in report["candidate_routes"]):
            report["status"] = "existing_CH025_vias_BCu_no_path_without_ripup"
        elif report["physical_BCu_route_qualified"]:
            report["status"] = "existing_CH025_vias_BCu_scratch_pass_no_release"
        else:
            report["status"] = "existing_CH025_vias_BCu_not_qualified"
        report["protected_originals_preserved"] = (
            (track_inventory(board) == before
             if not any(row["BCu_route_proposed"]
                        for row in report["candidate_routes"])
             else all(
                 track_inventory(board).get(uid) == data
                 for uid, data in before.items() if uid != CUT))
            and unchanged_fingerprints(board) == protected)
        report["native_in1_zero"] = every_zero(polygon_delta(
            base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
        report["native_l3_zero"] = every_zero(polygon_delta(
            base_l3, polygon_snapshot(board, pcbnew.In2_Cu)))
    report["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == raw_hash)
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = run(args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({
        "status": data["status"],
        "BCu_pair_count": len(data["candidate_routes"]),
        "native_route_qualified": data["physical_BCu_route_qualified"],
        "accepted": False, "fabrication_release": False}))

if __name__ == "__main__":
    main()

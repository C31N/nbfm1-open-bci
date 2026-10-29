#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wide F.Cu-only CH027 annulus route with BOTH original MUX_S0 tracks intact.

Unlike earlier ripup trials, absolutely no S0 copper is removed. The
scratch-only source board is pinned, existing vias/AGND/VCM/MUX_EN protected,
and exact native L3/DRC qualification is mandatory before claiming closure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile
import math

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_native_refill import filled
from analyze_ch025_l3_precision_mask import exact_native_difference
from native_connectivity import regressed_nets
from probe_ch025_cooperative8 import CH027_ALT_VIA, unchanged_fingerprints
from probe_ch025_fcu_l3_exact import ZONE, track_inventory, power_fcu_obstacles
from probe_ch027_annulus_s0_native import (
    CH027, S0, CUT, S0_UUIDS, CH027_VIA_LANDINGS_MM,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    make_track, metrics, native, routing_domain, xy,
)
from escape_mesh_505 import mesh_route

NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "In1_Cu_used": False,
    "schematic_parity_qualified": False,
    "independent_replay_verified": False,
}

def run(candidate: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    from route_targeted_closure import obstacles
    from escape_mesh_505 import polygons

    out: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started",
        "source_archive_unchanged": False,
        "source_board_sha256": PINNED_CANDIDATE_SHA,
        "native_139_baseline": None,
        "both_original_S0_tracks_untouched": False,
        "protected_originals_unchanged": False,
        "native_CH027_DRC_qualified": False,
        "native_L3_exact_zero": False,
        "new_via_count": 0,
        "attempts": [],
        "connectivity_prescreen_performed": True,
        "large_region_mesh_complexity_limit": 1900,
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned native KiCad 8.0.9 required")
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="CH027-wide-S0-immutable-") as d:
        folder = Path(d)
        with zipfile.ZipFile(candidate) as archive:
            if set(archive.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unreviewed engineering input")
            flags = json.loads(archive.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if flags.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 source identity mismatch")
            for key in ("accepted", "fabrication_release",
                        "routing_completed",
                        "routing_replay_byteidentical_verified"):
                if flags.get(key) is not False:
                    raise RuntimeError("Unexpected source release state")
            for name in MEMBERS:
                (folder / name).write_bytes(archive.read(name))
        original = folder / MEMBERS[0]
        if hashlib.sha256(original.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("Protected MUX_EN/CH019 board digest mismatch")
        baseline = native(original, folder / "baseline.json")
        out["native_139_baseline"] = metrics(baseline)
        if out["native_139_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "baseline_139_gate_failed"
            return out
        board = pcbnew.LoadBoard(str(original))
        before = track_inventory(board)
        protected = unchanged_fingerprints(board)
        items = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        for uid in S0_UUIDS:
            track = items.get(uid)
            if (track is None or track.GetNetname() != S0
                    or track.GetLayer() != pcbnew.F_Cu
                    or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                raise RuntimeError("Original S0 copper identity mismatch")
        cut = items.get(CUT)
        if (cut is None or cut.GetNetname() != CH027
                or cut.GetLayer() != pcbnew.F_Cu
                or isinstance(cut, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise RuntimeError("Unreviewed CH027 original ripup")
        via = items.get(CH027_ALT_VIA)
        if (not isinstance(via, pcbnew.PCB_VIA)
                or via.GetNetname() != CH027):
            raise RuntimeError("CH027 existing via changed")
        center = xy(via.GetPosition())
        radius = pcbnew.ToMM(via.GetWidth()) / 2
        start = xy(cut.GetStart())
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Native protected 3V3A zone missing")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        l3_before = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        vias_before = {uid for uid, values in before.items()
                       if values[-1] == "PCB_VIA"}
        board.Remove(cut)
        code = board.FindNet(CH027).GetNetCode()
        power = filled(zone)
        domain = routing_domain(board, .075, .25)
        guard = power_fcu_obstacles(board)
        completed = False
        for contact in CH027_VIA_LANDINGS_MM:
            if math.dist(center, contact) >= radius - .01:
                raise RuntimeError("Landing outside existing via annulus")
            for margin in (8.0, 14.0, 25.0):
                region = domain.intersection(box(
                    min(start[0], contact[0]) - margin,
                    min(start[1], contact[1]) - margin,
                    max(start[0], contact[0]) + margin,
                    max(start[1], contact[1]) + margin))
                # Cheap exact geometric reachability screen BEFORE expensive
                # constrained Delaunay triangles. Existing S0/VCM/Block1
                # copper remains a literal obstacle; no ripup is permitted.
                foreign, _ = obstacles(
                    board, code, .15, .15, region, .60,
                    (pcbnew.F_Cu, pcbnew.B_Cu))
                free_f = region.difference(unary_union([
                    foreign[0], guard])).buffer(-.000005)
                components = polygons(free_f)
                tree = STRtree(components)
                def component(point: tuple[float, float]) -> int | None:
                    return next((int(idx) for idx in tree.query(Point(point))
                                 if components[int(idx)].covers(Point(point))),
                                None)
                source_component = component(start)
                target_component = component(contact)
                connected = (
                    source_component is not None
                    and source_component == target_component)
                complexity = sum(
                    len(poly.exterior.coords) +
                    sum(len(hole.coords) for hole in poly.interiors)
                    for poly in components)
                path = None
                mesh_screened = not connected
                # Cap costly triangulation to avoid a timeout with NO JSON
                # output. A cap is NOT a proof that the route cannot exist.
                if connected and complexity <= 1900:
                    path = mesh_route(
                        board, start, contact, code,
                        (pcbnew.F_Cu, pcbnew.B_Cu), power, region,
                        start_layer=0, goal_layer=0, allow_vias=False,
                        extra_obstacles=[guard, GeometryCollection()])
                valid = (
                    path is not None and len(path) >= 2
                    and all(vertex[0] == 0 for vertex in path))
                row = {
                    "contact_mm": list(contact), "margin_mm": margin,
                    "FCu_only_path_found": bool(valid),
                    "source_component": source_component,
                    "target_component": target_component,
                    "FCu_topologically_connected": bool(connected),
                    "mesh_skipped_disconnected": bool(mesh_screened),
                    "free_geometry_vertex_count": complexity,
                    "mesh_skipped_complexity_budget": (
                        connected and complexity > 1900),
                    "native_DRC_qualified": False,
                    "S0_original_tracks_untouched": True,
                    "new_vias": False,
                }
                out["attempts"].append(row)
                if not valid:
                    continue
                row["path"] = [list(v) for v in path]
                for first, second in zip(path, path[1:]):
                    make_track(board, tuple(first[1:]),
                               tuple(second[1:]), code, .15, pcbnew.F_Cu)
                current = track_inventory(board)
                if any(current.get(uid) != val for uid, val in before.items()
                       if uid != CUT):
                    raise RuntimeError("Unexpected original track mutation")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Protected vias, pads or zones altered")
                new_via_ids = {
                    t.m_Uuid.AsString() for t in board.GetTracks()
                    if isinstance(t, pcbnew.PCB_VIA)}
                if new_via_ids != vias_before:
                    raise RuntimeError("New via prohibited")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                l3_after = pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
                delta = exact_native_difference(l3_before, l3_after)
                row["L3_native_exact_zero"] = delta["native_both_empty"]
                row["L3_loss_mm2"] = delta["loss_native_mm2"]
                row["L3_gain_mm2"] = delta["gain_native_mm2"]
                if delta["native_both_empty"]:
                    scratch = folder / "scratch"
                    scratch.mkdir()
                    for name in MEMBERS[1:]:
                        shutil.copyfile(folder / name, scratch / name)
                    out_board = scratch / MEMBERS[0]
                    pcbnew.SaveBoard(str(out_board), board)
                    after = native(out_board, folder / "candidate.json")
                    row["native_metrics"] = metrics(after)
                    row["regressed_nets"] = regressed_nets(baseline, after)
                    row["native_DRC_qualified"] = (
                        metrics(after)["violations"] == 0
                        and metrics(after)["warnings"] == 0
                        and metrics(after)["unconnected"] < 139
                        and not row["regressed_nets"])
                    out["native_CH027_DRC_qualified"] = row["native_DRC_qualified"]
                    out["native_L3_exact_zero"] = True
                completed = True
                break
            if completed:
                break
        out["both_original_S0_tracks_untouched"] = all(
            track_inventory(board).get(uid) == before[uid]
            for uid in S0_UUIDS)
        out["protected_originals_unchanged"] = (
            all(track_inventory(board).get(uid) == value
                for uid, value in before.items() if uid != CUT)
            and unchanged_fingerprints(board) == protected)
        if not (out["both_original_S0_tracks_untouched"]
                and out["protected_originals_unchanged"]):
            raise RuntimeError("Protected copper regression")
        out["status"] = (
            "wide_FCu_route_native_DRC_pass_no_release"
            if out["native_CH027_DRC_qualified"]
            else "wide_FCu_route_not_qualified")
    out["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() ==
        candidate_hash)
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
        "DRC_qualified": result["native_CH027_DRC_qualified"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

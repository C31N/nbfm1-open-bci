#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native F/B/In2 reachability for genuinely OPEN Block2 MUX airwires.

ONLY existing same-net through-vias can transition copper layers.
The native 139 source and every protected track/via are immutable. This
diagnostic opens no route by itself; a simple two-via path, if found, may
be routed on disposable copper and accepted only after 0/0 DRC, exact
3V3A loss=gain=0, unchanged In1, zero net regressions and 138 airwires.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_native_refill import filled
from analyze_ch025_l3_precision_mask import exact_native_difference
from escape_mesh_505 import polygons
from native_connectivity import airwire_counts, regressed_nets
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_ch025_fcu_l3_exact import ZONE, track_inventory, power_fcu_obstacles
from probe_ch025_neutral_via_sites import every_zero, polygon_delta, polygon_snapshot
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    add_path, metrics, native, obstacles, routing_domain, search, xy,
)

NETS = (
    "CH018_P_MUX", "CH020_N_MUX", "CH020_P_MUX",
    "CH024_N_MUX", "CH024_P_MUX", "CH028_N_MUX",
    "CH029_N_MUX", "CH030_N_MUX",
)
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "new_vias_added": 0,
    "In1_Cu_used": False,
}
LAYERS = ("F.Cu", "B.Cu", "In2.Cu")
PAIR = {
    "F.Cu": ("F.Cu", "B.Cu"),
    "B.Cu": ("B.Cu", "F.Cu"),
    "In2.Cu": ("In2.Cu", "B.Cu"),
}

def native_airwire_points(report: dict[str, Any], net: str) -> list[tuple[float, float]]:
    items = [
        row for row in report["unconnected_items"]
        if any("[" + net + "]" in entry.get("description", "")
               for entry in row.get("items", []))]
    if len(items) != 1 or len(items[0]["items"]) != 2:
        raise RuntimeError("Expected exactly one native two-terminal airwire")
    ends = items[0]["items"]
    if any("on F.Cu" not in item.get("description", "") for item in ends):
        raise RuntimeError("Unreviewed non-FCu terminal")
    return [
        (float(item["pos"]["x"]), float(item["pos"]["y"]))
        for item in ends]

def graph_route(
        components: dict[str, list[Any]],
        endpoint: list[tuple[float, float]],
        vias: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """BFS over (layer, free-copper-component), via UUID edges only."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    trees = {layer: STRtree(rows) for layer, rows in components.items()}

    def locate(layer: str, pos: tuple[float, float]) -> list[tuple[int, tuple[float,float]]]:
        point = Point(pos)
        return [(int(idx), pos) for idx in trees[layer].query(point)
                if components[layer][int(idx)].covers(point)]

    def annulus_contacts(layer: str, via: dict[str, Any]) -> list[dict[str, Any]]:
        disk = Point(via["xy_mm"]).buffer(
            max(0.01, via["diameter_mm"] / 2 - .01), quad_segs=32)
        contacts = []
        for idx in trees[layer].query(disk):
            section = components[layer][int(idx)].intersection(disk)
            if section.area <= .00001:
                continue
            pt = section.representative_point()
            contacts.append({
                "component": int(idx),
                "xy_mm": [round(pt.x, 6), round(pt.y, 6)],
                "contact_area_mm2": round(section.area, 9),
            })
        return contacts

    starts = locate("F.Cu", endpoint[0])
    ends = locate("F.Cu", endpoint[1])
    edges: dict[tuple[str,int], list[tuple[tuple[str,int],str,tuple[float,float],tuple[float,float]]]] = {}
    for via in vias:
        via["contacts"] = {layer: annulus_contacts(layer, via)
                           for layer in LAYERS}
        for i, left in enumerate(LAYERS):
            for right in LAYERS[i+1:]:
                for a in via["contacts"][left]:
                    for b in via["contacts"][right]:
                        src = (left, a["component"])
                        dst = (right, b["component"])
                        e1 = (dst, via["uuid"], tuple(a["xy_mm"]), tuple(b["xy_mm"]))
                        e2 = (src, via["uuid"], tuple(b["xy_mm"]), tuple(a["xy_mm"]))
                        edges.setdefault(src, []).append(e1)
                        edges.setdefault(dst, []).append(e2)
    source_nodes = [("F.Cu", i) for i, _ in starts]
    goal_nodes = {("F.Cu", i) for i, _ in ends}
    visited = set(source_nodes)
    pending = deque([(node, []) for node in source_nodes])
    chosen = None
    while pending:
        node, path = pending.popleft()
        if node in goal_nodes:
            chosen = path
            break
        for other, uid, from_xy, to_xy in edges.get(node, ()):
            if other not in visited:
                visited.add(other)
                pending.append((other, path + [{
                    "from_layer": node[0], "from_component": node[1],
                    "to_layer": other[0], "to_component": other[1],
                    "via_uuid": uid,
                    "contact_from_mm": list(from_xy),
                    "contact_to_mm": list(to_xy),
                }]))
    return chosen or [], {
        "source_FCu_components": [i for i, _ in starts],
        "target_FCu_components": [i for i, _ in ends],
        "source_and_target_FCu_same_component": bool(
            {i for i, _ in starts} & {i for i, _ in ends}),
        "reachable_component_nodes": [
            [layer, idx] for layer, idx in sorted(visited)],
        "same_net_existing_through_via_count": len(vias),
        "same_net_existing_through_vias": vias,
        "topological_transition_count": (
            len(chosen) if chosen is not None else None),
        "topological_via_hops": chosen or [],
        "topological_path_found": chosen is not None,
        "native_DRC_qualified": False,
        "not_a_routed_copper_path": True,
    }

def run(archive_path: Path, net: str, output_path: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box
    from shapely.ops import unary_union

    if net not in NETS:
        raise ValueError("Unreviewed open net")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Expected pinned KiCad 8.0.9")
    result: dict[str, Any] = {
        **NO_RELEASE, "status": "preflight", "net": net,
        "native_baseline": None, "topology": None,
        "candidate_route_native_DRC": None,
        "candidate_net_after": None,
        "single_net_candidate_qualified": False,
        "original_copper_restituted": False,
        "original_archive_unchanged": False,
        "native_L3_exact_after_rollback": False,
        "native_In1_exact_after_rollback": False,
    }

    def record(stage: str) -> None:
        result["last_stage"] = stage
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n")

    original_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    record("verify_pinned_board")
    with tempfile.TemporaryDirectory(prefix="real-mux-three-layer-") as td:
        root = Path(td)
        with zipfile.ZipFile(archive_path) as archive:
            if set(archive.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unreviewed engineering input")
            audit = json.loads(archive.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 engineering source SHA mismatch")
            for key in ("accepted", "routing_completed",
                        "fabrication_release",
                        "routing_replay_byteidentical_verified"):
                if audit.get(key) is not False:
                    raise RuntimeError("Invalid release metadata")
            for name in MEMBERS:
                (root / name).write_bytes(archive.read(name))
        board_path = root / MEMBERS[0]
        if hashlib.sha256(board_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Pinned MUX_EN source PCB changed")
        baseline = native(board_path, root / "baseline.json")
        result["native_baseline"] = metrics(baseline)
        if result["native_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("139/0/0 baseline violated")
        if airwire_counts(baseline).get(net, 0) != 1:
            raise RuntimeError("Expected real open single airwire")
        anchors = native_airwire_points(baseline, net)
        result["native_open_endpoints_mm"] = [list(x) for x in anchors]
        board = pcbnew.LoadBoard(str(board_path))
        old_tracks = track_inventory(board)
        old_protected = unchanged_fingerprints(board)
        vias_before = {
            item.m_Uuid.AsString()
            for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)}
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Missing protected 3V3A zone")
        base_L3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        base_In1 = polygon_snapshot(board, pcbnew.In1_Cu)
        power = filled(zone)
        code = board.FindNet(net).GetNetCode()
        domain = routing_domain(board, .075, .25)
        window = domain.intersection(box(
            min(x[0] for x in anchors) - 4.0,
            min(x[1] for x in anchors) - 4.0,
            max(x[0] for x in anchors) + 4.0,
            max(x[1] for x in anchors) + 4.0))
        fb, _ = obstacles(board, code, .15, .15, window, .65,
                          (pcbnew.F_Cu, pcbnew.B_Cu))
        bi, _ = obstacles(board, code, .15, .15, window, .65,
                          (pcbnew.B_Cu, pcbnew.In2_Cu))
        blocked = {
            "F.Cu": unary_union([fb[0], power_fcu_obstacles(board)]),
            "B.Cu": fb[1],
            "In2.Cu": unary_union([bi[1], power.buffer(.58)]),
        }
        components = {
            name: polygons(window.difference(blocked[name]).buffer(-.000005))
            for name in LAYERS}
        same_net_vias = []
        for item in board.GetTracks():
            if (isinstance(item, pcbnew.PCB_VIA)
                    and item.GetNetname() == net
                    and item.GetViaType() == pcbnew.VIATYPE_THROUGH):
                same_net_vias.append({
                    "uuid": item.m_Uuid.AsString(),
                    "xy_mm": list(xy(item.GetPosition())),
                    "diameter_mm": pcbnew.ToMM(item.GetWidth()),
                    "protected_original": True,
                })
        route, topology = graph_route(components, anchors, same_net_vias)
        result["topology"] = {
            **topology,
            "layer_component_counts": {
                layer: len(components[layer]) for layer in LAYERS},
            "search_window_mm": [round(v, 6) for v in window.bounds],
            "0_505mm_power_clearance_applied": True,
            "new_via_sites_sampled": 0,
        }
        record("original_via_three_layer_graph_complete")
        # Only a two-hop path is currently physically routable via-only:
        # F.Cu -> B.Cu/In2.Cu -> F.Cu, existing through vias only.
        physical = (len(route) == 2
                    and route[0]["from_layer"] == "F.Cu"
                    and route[0]["to_layer"] == route[1]["from_layer"]
                    and route[1]["to_layer"] == "F.Cu"
                    and route[0]["via_uuid"] != route[1]["via_uuid"])
        result["eligible_for_bounded_two_existing_via_trial"] = physical
        if physical:
            sequence = [
                ("F.Cu", anchors[0], route[0]["contact_from_mm"]),
                (route[0]["to_layer"], route[0]["contact_to_mm"],
                 route[1]["contact_from_mm"]),
                ("F.Cu", route[1]["contact_to_mm"], anchors[1]),
            ]
            original_ids = set(old_tracks)
            try:
                success = True
                for i, (layer, start, finish) in enumerate(sequence):
                    result["active_segment"] = i
                    record("bounded_existing_via_segment_search")
                    pair = PAIR[layer]
                    copper_layers = tuple({
                        "F.Cu": pcbnew.F_Cu,
                        "B.Cu": pcbnew.B_Cu,
                        "In2.Cu": pcbnew.In2_Cu}[value] for value in pair)
                    proposal = search(
                        board, tuple(start), tuple(finish), code,
                        .15, .15, False, 5.0, step=.20,
                        max_nodes=35000, deadline=time.monotonic()+25,
                        start_layer=0, goal_layer=0,
                        layers=copper_layers)
                    if (proposal is None or len(proposal) < 2
                            or any(point[0] != 0 for point in proposal)):
                        success = False
                        result["failed_segment"] = i
                        break
                    add_path(board, proposal, code, .15,
                             layers=copper_layers)
                if success:
                    if (any(track_inventory(board).get(k) != value
                            for k, value in old_tracks.items())
                            or unchanged_fingerprints(board) != old_protected):
                        raise RuntimeError("Protected original copper changed")
                    new_vias = {
                        item.m_Uuid.AsString() for item in board.GetTracks()
                        if isinstance(item, pcbnew.PCB_VIA)}
                    if new_vias != vias_before:
                        raise RuntimeError("Unexpected new via")
                    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                    native_delta = exact_native_difference(
                        base_L3, pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu)))
                    result["candidate_L3_loss_mm2"] = (
                        native_delta["loss_native_mm2"])
                    result["candidate_L3_gain_mm2"] = (
                        native_delta["gain_native_mm2"])
                    result["candidate_L3_exact"] = (
                        native_delta["native_both_empty"])
                    result["candidate_In1_exact"] = every_zero(polygon_delta(
                        base_In1, polygon_snapshot(board, pcbnew.In1_Cu)))
                    record("candidate_native_power_gate_checked")
                    if (result["candidate_L3_exact"]
                            and result["candidate_In1_exact"]):
                        scratch_dir = root / "scratch"
                        scratch_dir.mkdir()
                        for member in MEMBERS[1:]:
                            shutil.copyfile(root / member, scratch_dir / member)
                        scratch = scratch_dir / MEMBERS[0]
                        pcbnew.SaveBoard(str(scratch), board)
                        post = native(scratch, root / "after.json")
                        count = airwire_counts(post)
                        result["candidate_route_native_DRC"] = metrics(post)
                        result["candidate_net_after"] = count.get(net, 0)
                        result["regressed_nets"] = regressed_nets(
                            baseline, post)
                        result["single_net_candidate_qualified"] = (
                            result["candidate_route_native_DRC"] ==
                            {"violations": 0, "warnings": 0, "unconnected": 138}
                            and result["candidate_net_after"] == 0
                            and not result["regressed_nets"])
                        record("native_drc_and_138_gate_checked")
            finally:
                for item in list(board.GetTracks()):
                    if item.m_Uuid.AsString() not in original_ids:
                        board.Remove(item)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                result["original_copper_restituted"] = (
                    track_inventory(board) == old_tracks
                    and unchanged_fingerprints(board) == old_protected)
                result["native_L3_exact_after_rollback"] = (
                    exact_native_difference(
                        base_L3, pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                    )["native_both_empty"])
                result["native_In1_exact_after_rollback"] = every_zero(
                    polygon_delta(base_In1,
                                  polygon_snapshot(board, pcbnew.In1_Cu)))
                if not (result["original_copper_restituted"]
                        and result["native_L3_exact_after_rollback"]
                        and result["native_In1_exact_after_rollback"]):
                    raise RuntimeError("Original copper or zone rollback failed")
        else:
            result["original_copper_restituted"] = (
                track_inventory(board) == old_tracks
                and unchanged_fingerprints(board) == old_protected)
            result["native_L3_exact_after_rollback"] = True
            result["native_In1_exact_after_rollback"] = True
        result["status"] = (
            "single_net_existing_via_native_138_qualified_no_release"
            if result["single_net_candidate_qualified"]
            else "no_native_qualified_two_existing_via_route")
    result["original_archive_unchanged"] = (
        hashlib.sha256(archive_path.read_bytes()).hexdigest() ==
        original_hash)
    record("complete")
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--net", choices=NETS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.candidate, args.net, args.output)
    print(json.dumps({
        "net": args.net, "status": result["status"],
        "two_existing_via_trial": result[
            "eligible_for_bounded_two_existing_via_trial"],
        "qualified": result["single_net_candidate_qualified"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

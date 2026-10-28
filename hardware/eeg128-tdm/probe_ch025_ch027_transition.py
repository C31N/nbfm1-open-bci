#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CH025/CH027 FCu/BCu transition survey on SHA-pinned MUX_EN engineering PCB.

Read-only original, isolated disposable PCB. A via graph is ONLY a necessary
topological pre-screen. Foreign copper, especially VCM/Block-1, is immutable.
No net is promoted without native DRC, combined L3 and independent replay.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from probe_ch025_cooperative8 import CH027_ALT_TARGET, CH027_ALT_VIA, unchanged_fingerprints
from probe_ch025_fcu_l3_exact import CUT, NET, ZONE, track_inventory, power_fcu_obstacles
from probe_ch025_neighbor_restitution7 import NEIGHBORS, UNCHANGED
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import native, metrics, xy

NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "In1_Cu_used": False, "checkpoint_promoted": False,
    "all_eight_mux_qualified": False, "CH022_qualified": False,
    "schematic_parity_qualified": False, "independent_replay_verified": False,
}
TARGETS = ("CH025_N_MUX", "CH027_N_MUX")


def component_index(tree: Any, parts: list[Any], point: Any) -> int | None:
    """Shapely2 integer STRtree spatial-index lookup with exact polygon cover."""
    return next((int(i) for i in tree.query(point)
                 if parts[int(i)].covers(point)), None)


def power_via_guard(board: Any, layer: int) -> Any:
    """0.505-mm copper-to-copper power clearance for 0.65-mm via centres."""
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    from route_targeted_closure import POWER, pad_copper_shape
    copper = []
    for track in board.GetTracks():
        if track.GetNetname() not in POWER:
            continue
        if isinstance(track, pcbnew.PCB_VIA):
            copper.append(Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2))
        elif track.GetLayer() == layer:
            if isinstance(track, pcbnew.PCB_ARC):
                bb = track.GetBoundingBox()
                copper.append(box(pcbnew.ToMM(bb.GetX()),
                                  pcbnew.ToMM(bb.GetY()),
                                  pcbnew.ToMM(bb.GetRight()),
                                  pcbnew.ToMM(bb.GetBottom())))
            else:
                copper.append(LineString([
                    xy(track.GetStart()), xy(track.GetEnd())]).buffer(
                        pcbnew.ToMM(track.GetWidth()) / 2))
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if (pad.GetNetname() in POWER and
                    pad.IsOnLayer(layer)):
                copper.append(pad_copper_shape(pad, layer))
    return (unary_union(copper).buffer(.505 + .325 + .00001)
            if copper else Point().buffer(0))


def graph_components(board: Any, net: str, source: tuple[float, float],
                     target: tuple[float, float], *,
                     target_layer: str = "F") -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box
    from shapely.strtree import STRtree
    from shapely.ops import unary_union
    from escape_mesh_505 import polygons
    from route_targeted_closure import obstacles, routing_domain

    en = board.FindNet(net).GetNetCode()
    domain = routing_domain(board, .075, .25)
    via_domain = routing_domain(board, .325, .25)
    bounds = (
        min(source[0], target[0]) - 7.0,
        min(source[1], target[1]) - 7.0,
        max(source[0], target[0]) + 7.0,
        max(source[1], target[1]) + 7.0,
    )
    region = domain.intersection(box(*bounds))
    via_region = via_domain.intersection(box(*bounds))
    foreign, via_walls = obstacles(
        board, en, .15, .15, region, .65,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    power_f = power_fcu_obstacles(board)
    free_f = region.difference(unary_union(
        [foreign[0], power_f])).buffer(-.000005)
    free_b = region.difference(foreign[1]).buffer(-.000005)
    fparts, bparts = polygons(free_f), polygons(free_b)
    ftree, btree = STRtree(fparts), STRtree(bparts)
    fsource = component_index(ftree, fparts, Point(source))
    ftarget = component_index(ftree, fparts, Point(target))
    bsource = component_index(btree, bparts, Point(source))
    btarget = component_index(btree, bparts, Point(target))
    if target_layer not in ("F", "B"):
        raise ValueError("Only F.Cu and B.Cu terminal targets permitted")
    no_new_via = {
        "target_layer": "F.Cu" if target_layer == "F" else "B.Cu",
        "source_xy_mm": list(source), "target_xy_mm": list(target),
        "search_region_mm": list(region.bounds),
        "FCu_components": len(fparts), "BCu_components": len(bparts),
        "source_FCu_component": fsource,
        "target_FCu_component": ftarget,
        "source_BCu_component": bsource,
        "target_BCu_component": btarget,
        "source_FCu_connected_to_target": (
            fsource is not None and fsource == ftarget),
        "same_BCu_component_if_existing_vias_at_both_endpoints": (
            bsource is not None and bsource == btarget),
    }
    if fsource is None or (ftarget if target_layer == "F" else btarget) is None:
        return {
            **no_new_via, "status": "FCu_terminal_not_free",
            "topological_via_paths": [], "existing_same_net_vias": [],
            "new_legal_via_sites_sampled": 0,
            "native_L3_pair_qualified": False,
        }

    existing = []
    edges: dict[tuple[str, int], list[tuple[tuple[str, int], Any]]] = defaultdict(list)
    original_vias = [
        item for item in board.GetTracks()
        if (isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == net
            and item.GetViaType() == pcbnew.VIATYPE_THROUGH)]
    for item in original_vias:
        pos = xy(item.GetPosition())
        fp = component_index(ftree, fparts, Point(pos))
        bp = component_index(btree, bparts, Point(pos))
        entry = {"uuid": item.m_Uuid.AsString(), "xy_mm": list(pos),
                 "FCu_component": fp, "BCu_component": bp,
                 "preexisting": True}
        existing.append(entry)
        if fp is not None and bp is not None:
            left, right = ("F", fp), ("B", bp)
            edges[left].append((right, entry))
            edges[right].append((left, entry))

    # The via diameter is 0.65 mm. Shrink trace centreline free space by
    # its radius difference 0.25 mm, and preserve all drill/pad obstacles.
    allowed = via_region.intersection(free_f.buffer(-.25)).intersection(
        free_b.buffer(-.25)).difference(
        unary_union([
            via_walls,
            power_f.buffer(.25),
            power_via_guard(board, pcbnew.B_Cu),
        ])).buffer(-.000005)
    if allowed.is_empty:
        sites = []
    else:
        a, b, c, d = allowed.bounds
        sites = []
        step = .5
        for i in range(int(math.ceil((c-a)/step))):
            px = round(a + (i+.5)*step, 6)
            for j in range(int(math.ceil((d-b)/step))):
                py = round(b + (j+.5)*step, 6)
                point = Point(px, py)
                if not allowed.covers(point):
                    continue
                fp = component_index(ftree, fparts, point)
                bp = component_index(btree, bparts, point)
                if fp is None or bp is None:
                    continue
                entry = {"xy_mm": [px, py],
                         "FCu_component": fp,
                         "BCu_component": bp, "preexisting": False}
                sites.append(entry)
                left, right = ("F", fp), ("B", bp)
                edges[left].append((right, entry))
                edges[right].append((left, entry))
    # Graph BFS minimizes the number of additional layer transitions;
    # each edge represents a via site, NOT a fully routed copper path.
    start_node = ("F", fsource)
    finish_node = ("F", ftarget) if target_layer == "F" else ("B", btarget)
    frontier = deque([(start_node, [])])
    visited: set[tuple[str, int]] = {start_node}
    paths = []
    while frontier and len(paths) < 2:
        vertex, path = frontier.popleft()
        if vertex == finish_node:
            paths.append(path)
            continue
        for other, site in edges[vertex]:
            if other in visited:
                continue
            visited.add(other)
            frontier.append((other, path + [site]))
    found = paths[0] if paths else []
    return {
        **no_new_via, "status": (
            "multilayer_topology_proposed_not_DRC_qualified" if paths
            else "no_four_via_or_existing_via_component_path_in_window"),
        "topological_via_paths": paths,
        "minimum_transition_count": len(found) if paths else None,
        "new_legal_via_sites_sampled": len(sites),
        "existing_same_net_vias": existing[:40],
        "existing_CH027_anchor_preserved": any(
            row["uuid"] == CH027_ALT_VIA for row in existing
        ) if net == "CH027_N_MUX" else None,
        "native_L3_pair_qualified": False,
        "proposals_are_routed": False,
        "native_DRC_qualified": False,
        "guarded_VCM_Block1_unchanged": True,
        "power_via_copper_clearance_mm": .505,
        "edge_clearance_mm": .25,
    }


def run(source_archive: Path) -> dict[str, Any]:
    import pcbnew
    out: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started",
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_PCB_SHA256": PINNED_CANDIDATE_SHA,
        "source_PCB_untouched": False,
        "native_candidate_baseline": None,
        "CH019_MUX_EN_frozen": False,
        "original_tracks_restored": False,
        "protected_vias_pads_zones_unchanged": False,
        "L3_native_control_exact_zero": False,
        "net_trials": [],
    }
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Native KiCad 8.0.9 required")
    archive_sha = hashlib.sha256(source_archive.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="CH025-CH027-via-graph-") as td:
        root = Path(td)
        with zipfile.ZipFile(source_archive) as z:
            expected = set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}
            if set(z.namelist()) != expected:
                raise RuntimeError("Engineering ZIP has unreviewed members")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if any(audit.get(k) is not False
                   for k in ("accepted", "fabrication_release",
                             "routing_completed",
                             "routing_replay_byteidentical_verified")):
                raise RuntimeError("Engineering candidate incorrectly promoted")
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 source checkpoint mismatch")
            for name in MEMBERS:
                (root / name).write_bytes(z.read(name))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Engineering candidate byte hash mismatch")
        before_drc = native(pcb_path, root / "baseline.json")
        out["native_candidate_baseline"] = metrics(before_drc)
        if metrics(before_drc) != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "native_DRC_baseline_failed"
            return out
        board = pcbnew.LoadBoard(str(pcb_path))
        originals = track_inventory(board)
        fingerprint = unchanged_fingerprints(board)
        current = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        for uid in UNCHANGED:
            if uid not in current:
                raise RuntimeError("Protected S2/CH028 original missing")
        if CH027_ALT_VIA not in current:
            raise RuntimeError("CH027 existing via lost")
        movable = {
            NET: current[CUT],
            "CH027_N_MUX": current[next(
                u for u, n in NEIGHBORS.items()
                if n == "CH027_N_MUX")],
        }
        for net, item in movable.items():
            if item.GetNetname() != net:
                raise RuntimeError("Reviewed changeable track does not match")
            if net == NET and item.GetLayer() != pcbnew.In2_Cu:
                raise RuntimeError("Original CH025 In2.Cu cut changed")
            if net != NET and item.GetLayer() != pcbnew.F_Cu:
                raise RuntimeError("Original CH027 F.Cu cut changed")
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Protected native 3V3A zone missing")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        l3_baseline = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        l3_again = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        out["L3_native_control_exact_zero"] = (
            exact_native_difference(
                l3_baseline, l3_again)["native_both_empty"])
        if not out["L3_native_control_exact_zero"]:
            raise RuntimeError("Same-board native L3 refill drift")
        for net in TARGETS:
            original = movable[net]
            if net == NET:
                start, end = (49.45, 14.90), (36.105, 48.85)
            else:
                start = xy(original.GetStart())
                # Use the UUID-pinned PHYSICAL B.Cu via, not the legacy
                # nearby proposed F.Cu landing point CH027_ALT_TARGET.
                end = xy(current[CH027_ALT_VIA].GetPosition())
            board.Remove(original)
            try:
                result = graph_components(
                    board, net, start, end,
                    target_layer="B" if net == "CH027_N_MUX" else "F")
                if net == "CH027_N_MUX":
                    result["original_reviewed_FCu_landing_mm"] = (
                        list(CH027_ALT_TARGET))
                    result["protected_actual_BCu_via_xy_mm"] = list(end)
                    result["reviewed_landing_to_physical_via_mm"] = (
                        math.dist(CH027_ALT_TARGET, end))
                    result["protected_CH027_via_position_was_modified"] = False
                result["net"] = net
                result["original_cut_UUID"] = original.m_Uuid.AsString()
                result["original_copper_removed_only_on_scratch"] = True
                result["native_L3_full_route_qualified"] = False
                out["net_trials"].append(result)
            finally:
                board.Add(original)
                if track_inventory(board) != originals:
                    raise RuntimeError("Scratch copper restitution failed")
        out["original_tracks_restored"] = (
            track_inventory(board) == originals)
        out["protected_vias_pads_zones_unchanged"] = (
            unchanged_fingerprints(board) == fingerprint)
        out["CH019_MUX_EN_frozen"] = (
            out["original_tracks_restored"]
            and out["protected_vias_pads_zones_unchanged"])
        out["status"] = "two_net_transition_graph_readonly_no_release"
    out["source_PCB_untouched"] = (
        hashlib.sha256(source_archive.read_bytes()).hexdigest() == archive_sha)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = run(args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "status": report["status"],
        "targets": [(row["net"], row["status"],
                     row.get("minimum_transition_count"))
                    for row in report["net_trials"]],
        "accepted": False, "fabrication_release": False,
    }))


if __name__ == "__main__":
    main()

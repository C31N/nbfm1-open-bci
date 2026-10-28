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



def component_cut_diagnostic(
        edges: dict, source: tuple[str, int], target: tuple[str, int],
        fparts: list, bparts: list) -> dict[str, Any]:
    """Graph partition and shortest same-layer gap; NOT a routing/DRC proof."""
    from shapely.ops import nearest_points

    def flood(root: tuple[str, int]) -> set[tuple[str, int]]:
        queue = deque([root])
        seen = {root}
        while queue:
            for neighbor, _ in edges.get(queue.popleft(), ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen

    left, right = flood(source), flood(target)

    def partition(nodes: set[tuple[str, int]]) -> dict[str, list[int]]:
        return {
            "F.Cu": sorted(i for layer, i in nodes if layer == "F"),
            "B.Cu": sorted(i for layer, i in nodes if layer == "B"),
        }

    result = {
        "status": ("connected_topology_only" if target in left
                   else "disconnected_component_graph"),
        "source_reachable": partition(left),
        "target_reachable": partition(right),
        "minimum_same_layer_gap": None,
        "native_DRC_qualified": False,
        "protected_restitution_qualified": False,
        "exact_L3_qualified": False,
        "not_a_legal_route": True,
    }
    if target in left:
        return result
    best = None
    for layer, label, components in (
            ("F", "F.Cu", fparts), ("B", "B.Cu", bparts)):
        for i in sorted(idx for lay, idx in left if lay == layer):
            for j in sorted(idx for lay, idx in right if lay == layer):
                if i == j:
                    continue
                distance = components[i].distance(components[j])
                rank = (round(distance, 9), label, i, j)
                if best is None or rank < best[0]:
                    best = (rank, label, components, i, j)
    if best is not None:
        _, label, components, i, j = best
        a, b = nearest_points(components[i], components[j])
        result["minimum_same_layer_gap"] = {
            "layer": label,
            "source_component": i,
            "target_component": j,
            "distance_mm": round(a.distance(b), 9),
            "from_xy_mm": [round(a.x, 6), round(a.y, 6)],
            "to_xy_mm": [round(b.x, 6), round(b.y, 6)],
            "barrier_objects_not_yet_qualified": True,
        }
    return result



def gap_blocker_inventory(board: Any, net: str, gap: dict[str, Any] | None) -> dict[str, Any]:
    """Original-copper UUID proximity, not an authorized ripup or native DRC."""
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from route_targeted_closure import POWER, ANALOG_REFERENCE, pad_copper_shape

    if gap is None:
        return {"status": "no_disconnected_gap", "layers": {},
                "native_DRC_qualified": False}
    a, b = tuple(gap["from_xy_mm"]), tuple(gap["to_xy_mm"])
    segment = LineString((a, b))
    allowed = {
        uid: name for uid, name in NEIGHBORS.items()
        if name in ("MUX_S0", "MUX_S1", "CH030_P_MUX")
    }
    rows: dict[str, list[dict[str, Any]]] = {"F.Cu": [], "B.Cu": []}

    def add(uid: str, name: str, kind: str, shape: Any,
            layers: tuple[str, ...], reference: str | None = None,
            endpoints: list[list[float]] | None = None) -> None:
        if name == net:
            return
        movable = (kind == "track" and allowed.get(uid) == name
                   and layers == ("F.Cu",))
        for layer in layers:
            # Conserve native search clearance; L3 power is a separate gate.
            pad = (.505 + .075 if name in POWER and layer == "F.Cu"
                   else max(.15, .20 if name in POWER | ANALOG_REFERENCE
                            else .15) + .075 - 1e-9)
            envelope = shape.buffer(pad)
            dist = segment.distance(envelope)
            if dist > .100001:
                continue
            rows[layer].append({
                "uuid": uid, "net": name, "kind": kind,
                "reference": reference, "layer": layer,
                "original_endpoints_mm": endpoints,
                "envelope_intersects_gap": bool(envelope.intersects(segment)),
                "distance_from_gap_mm": round(dist, 9),
                "classification": ("reviewed_Block2_FCu_track_candidate"
                                   if movable else "immutable_do_not_ripup"),
                "ripup_authorized": False,
            })

    for t in board.GetTracks():
        via = isinstance(t, pcbnew.PCB_VIA)
        arc = isinstance(t, pcbnew.PCB_ARC)
        if via:
            shape = Point(xy(t.GetPosition())).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
            layers = ("F.Cu", "B.Cu")
        elif t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            layers = (("F.Cu",) if t.GetLayer() == pcbnew.F_Cu
                      else ("B.Cu",))
            if arc:
                bb = t.GetBoundingBox()
                shape = box(pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                            pcbnew.ToMM(bb.GetRight()),
                            pcbnew.ToMM(bb.GetBottom()))
            else:
                shape = LineString((xy(t.GetStart()), xy(t.GetEnd()))).buffer(
                    pcbnew.ToMM(t.GetWidth()) / 2)
        else:
            continue
        ends = (None if via or arc else
                [list(xy(t.GetStart())), list(xy(t.GetEnd()))])
        add(t.m_Uuid.AsString(), t.GetNetname(),
            "via" if via else "arc" if arc else "track",
            shape, layers, endpoints=ends)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            for label, layer in (("F.Cu", pcbnew.F_Cu),
                                 ("B.Cu", pcbnew.B_Cu)):
                if pad.IsOnLayer(layer):
                    add(pad.m_Uuid.AsString(), pad.GetNetname(), "pad",
                        pad_copper_shape(pad, layer), (label,),
                        reference=fp.GetReference() + "." + pad.GetNumber())

    for layer in rows:
        rows[layer].sort(key=lambda r: (
            not r["envelope_intersects_gap"], r["distance_from_gap_mm"],
            r["classification"] != "immutable_do_not_ripup", r["uuid"]))
    active = [r for r in rows[gap["layer"]] if r["envelope_intersects_gap"]]
    return {
        "status": "native_object_proximity_not_causal_proof",
        "gap_layer": gap["layer"],
        "gap_start_xy_mm": list(a), "gap_end_xy_mm": list(b),
        "layers": rows,
        "gap_layer_intersecting_uuids": [r["uuid"] for r in active],
        "gap_layer_immutable_count": sum(
            r["classification"] == "immutable_do_not_ripup" for r in active),
        "candidate_movable_uuid_whitelist": allowed,
        "physical_route_verified": False, "native_DRC_qualified": False,
        "routing_completed": False, "fabrication_release": False,
    }


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
                     target_layer: str = "F",
                     sample_step_mm: float = .5) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box
    from shapely.strtree import STRtree
    from shapely.ops import unary_union
    from escape_mesh_505 import polygons
    from route_targeted_closure import obstacles, routing_domain

    if not .10 <= sample_step_mm <= .5:
        raise ValueError("Invalid via grid precision")
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
        "via_grid_precision_mm": sample_step_mm,
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
        step = sample_step_mm
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
    # Independent exact polygon overlap screen. A 0.5-mm raster can miss
    # small via landing islands. For each legal FCu footprint, query only
    # overlapping BCu components using native-outline Shapely geometry.
    # Require 0.005-mm interior slack; this is NOT an added DRC waiver.
    exact_pairs: list[dict[str, Any]] = []
    for fi, fgeom in enumerate(fparts):
        fp = allowed.intersection(fgeom)
        if fp.is_empty or fp.area < 0.000001:
            continue
        for bidx in btree.query(fp):
            bi = int(bidx)
            overlap = fp.intersection(bparts[bi]).buffer(-.005)
            if overlap.is_empty or overlap.area < 0.000001:
                continue
            pt = overlap.representative_point()
            px, py = round(pt.x, 6), round(pt.y, 6)
            check = Point(px, py)
            if not (allowed.covers(check)
                    and fgeom.covers(check)
                    and bparts[bi].covers(check)):
                continue
            entry = {"xy_mm": [px, py],
                     "FCu_component": fi, "BCu_component": bi,
                     "preexisting": False,
                     "found_by_exact_polygon_overlap": True,
                     "landing_interior_area_mm2": round(
                         overlap.area, 9)}
            exact_pairs.append(entry)
            left, right = ("F", fi), ("B", bi)
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
        "component_cut_diagnostic": component_cut_diagnostic(
            edges, start_node, finish_node, fparts, bparts),
        "minimum_transition_count": len(found) if paths else None,
        "new_legal_via_sites_sampled": len(sites),
        "exact_polygon_via_component_pairs": len(exact_pairs),
        "exact_polygon_via_pair_inventory": sorted(
            exact_pairs, key=lambda d: (
                -d["landing_interior_area_mm2"],
                d["FCu_component"], d["BCu_component"]))[:80],
        "direct_source_to_target_BCu_via_sites": [
            item for item in [*sites, *exact_pairs]
            if item["FCu_component"] == fsource
            and item["BCu_component"] == btarget][:200],
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
        "cooperative_removed_originals_only_topology": [],
        "cooperative_all_originals_restored": False,
        "CH027_one_via_native_L3_and_mesh_trial": None,
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
                result["gap_blocker_inventory"] = gap_blocker_inventory(
                    board, net,
                    result["component_cut_diagnostic"]["minimum_same_layer_gap"])
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
        # Deliberately remove ONLY five reviewed editable original segments
        # together, without writing any new copper. This tests whether a
        # coupled reroute could unlock CH025 and CH027. MUX_EN, CH019, S2/S3
        # and every protected Block-1/VCM original remain in place.
        other_names = {"MUX_S0", "MUX_S1", "CH030_P_MUX"}
        removable_other = [
            current[uid] for uid, net in NEIGHBORS.items()
            if net in other_names]
        joint = [movable[NET], movable["CH027_N_MUX"],
                 *removable_other]
        if len(joint) != 5 or len({t.m_Uuid.AsString() for t in joint}) != 5:
            raise RuntimeError("Invalid five-track cooperative cut identities")
        if any(t.GetNetname() not in {
                NET, "CH027_N_MUX", *other_names} for t in joint):
            raise RuntimeError("Protected network selected for virtual cut")
        for track in joint:
            board.Remove(track)
        try:
            for net in TARGETS:
                source = ((49.45, 14.90) if net == NET
                          else xy(movable[net].GetStart()))
                target = ((36.105, 48.85) if net == NET
                          else xy(current[CH027_ALT_VIA].GetPosition()))
                evidence = graph_components(
                    board, net, source, target,
                    target_layer="B" if net == "CH027_N_MUX" else "F")
                evidence["gap_blocker_inventory"] = gap_blocker_inventory(
                    board, net,
                    evidence["component_cut_diagnostic"]["minimum_same_layer_gap"])
                evidence["net"] = net
                evidence["virtually_removed_UUIDs"] = [
                    t.m_Uuid.AsString() for t in joint]
                evidence["only_reviewed_Block_2_removables"] = True
                evidence["CH019_MUX_EN_frozen"] = True
                evidence["no_concurrent_schematic_parity_claim"] = True
                evidence["new_copper_not_placed"] = True
                out["cooperative_removed_originals_only_topology"].append(
                    evidence)
        finally:
            for track in joint:
                board.Add(track)
            if track_inventory(board) != originals:
                raise RuntimeError(
                    "Coupled virtual ripup did not restore exact originals")
            out["cooperative_all_originals_restored"] = True
        # After the cooperative feasibility result, restore CH025's
        # original In2.Cu segment and temporarily remove ONLY four FCu
        # editable originals. Check whether CH027's single new through
        # via is L3-neutral and whether both signal legs exist as copper
        # centreline paths. Original MUX_EN, CH019, S2/S3, VCM and Block1
        # stay untouched. No PCB save/release is permitted here.
        from shapely.geometry import GeometryCollection, box
        from escape_mesh_505 import mesh_route
        from route_targeted_closure import (
            make_via, routing_domain)
        from analyze_ch025_l3_native_refill import filled
        other_names = {"MUX_S0", "MUX_S1", "CH030_P_MUX"}
        four = [movable["CH027_N_MUX"], *[
            current[uid] for uid, name in NEIGHBORS.items()
            if name in other_names]]
        trial: dict[str, Any] = {
            "status": "not_tested", "new_via_xy_mm": None,
            "native_L3_loss_mm2": None, "native_L3_gain_mm2": None,
            "native_L3_both_exactly_zero": False,
            "source_FCu_leg_found": False,
            "existing_via_BCu_leg_found": False,
            "native_DRC_qualified": False,
            "native_L3_via_site_trials": [],
            "originals_all_restituted": False,
            "only_four_reviewed_FCu_tracks_virtually_absent": True,
            "no_In1_Cu": True, "accepted": False,
            "fabrication_release": False,
        }
        for item in four:
            board.Remove(item)
        created = None
        try:
            net = "CH027_N_MUX"
            source = xy(movable[net].GetStart())
            target = xy(current[CH027_ALT_VIA].GetPosition())
            topology = graph_components(
                board, net, source, target, target_layer="B",
                sample_step_mm=.25)
            trial["four_track_virtual_cut_topology"] = {
                "status": topology["status"],
                "paths": topology["topological_via_paths"][:2],
                "new_legal_via_sites_sampled":
                    topology["new_legal_via_sites_sampled"],
                "exact_polygon_via_component_pairs":
                    topology.get("exact_polygon_via_component_pairs", 0),
                "number_of_direct_via_sites": len(
                    topology.get("direct_source_to_target_BCu_via_sites", [])),
            }
            sites = topology.get(
                "direct_source_to_target_BCu_via_sites", [])
            if not sites:
                trial["status"] = "no_one_via_path_with_CH025_original_present"
            else:
                # The first 0.5mm-raster site had tiny nonzero L3 deltas.
                # Select spatially diverse legal sites, never adjust copper.
                by_coord = {tuple(entry["xy_mm"]): entry
                            for entry in sites
                            if not entry["preexisting"]}
                from shapely.geometry import Point
                power_shape = filled(zone)
                ordered = sorted(by_coord, key=lambda p: (
                    -round(power_shape.distance(Point(p)), 7),
                    math.dist(p, source) + math.dist(p, target), p))
                sample_count = min(64, len(ordered))
                shortlist = ordered[:sample_count]
                trial["sampled_sites_sorted_by_power_zone_distance"] = True
                trial["L3_trial_count_limit"] = 64
                trial["all_topological_direct_sites_considered"] = (len(ordered) <= 64)
                trial["sample_step_mm"] = .25
                code = board.FindNet(net).GetNetCode()
                original_vias = {
                    t.m_Uuid.AsString() for t in board.GetTracks()
                    if isinstance(t, pcbnew.PCB_VIA)}
                for at in shortlist:
                    try:
                        make_via(board, at, code, .65)
                        new_vias = [
                            t for t in board.GetTracks()
                            if isinstance(t, pcbnew.PCB_VIA)
                            and t.m_Uuid.AsString() not in original_vias]
                        if len(new_vias) != 1:
                            raise RuntimeError(
                                "CH027 single new-via identity drift")
                        created = new_vias[0]
                        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                        candidate_l3 = pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                        diff = exact_native_difference(
                            l3_baseline, candidate_l3)
                        trial["native_L3_via_site_trials"].append({
                            "xy_mm": list(at),
                            "loss_native_mm2": diff["loss_native_mm2"],
                            "gain_native_mm2": diff["gain_native_mm2"],
                            "exact_native_both_empty": diff["native_both_empty"],
                            "native_DRC_qualified": False,
                        })
                        if diff["native_both_empty"]:
                            trial["new_via_xy_mm"] = list(at)
                            trial["native_L3_loss_mm2"] = 0.0
                            trial["native_L3_gain_mm2"] = 0.0
                            trial["native_L3_both_exactly_zero"] = True
                            # Find copper paths only once a zero-delta
                            # trial is identified; still do not write PCB.
                            power = filled(zone)
                            area = routing_domain(board, .075, .25)
                            legs = [
                                ("source_FCu", source, at,
                                 (pcbnew.F_Cu, pcbnew.B_Cu),
                                 [power_fcu_obstacles(board),
                                  GeometryCollection()]),
                                ("target_BCu", at, target,
                                 (pcbnew.B_Cu, pcbnew.F_Cu),
                                 [power_via_guard(board, pcbnew.B_Cu),
                                  GeometryCollection()]),
                            ]
                            for label, a, b, layers, guard in legs:
                                proposal = None
                                for margin in (3.0, 6.0, 10.0):
                                    search = area.intersection(box(
                                        min(a[0], b[0]) - margin,
                                        min(a[1], b[1]) - margin,
                                        max(a[0], b[0]) + margin,
                                        max(a[1], b[1]) + margin))
                                    route = mesh_route(
                                        board, a, b, code, layers, power,
                                        search, start_layer=0, goal_layer=0,
                                        allow_vias=False,
                                        extra_obstacles=guard)
                                    if (route and len(route) >= 2
                                            and tuple(route[0]) == (0, *a)
                                            and tuple(route[-1]) == (0, *b)
                                            and all(p[0] == 0 for p in route)):
                                        proposal = route
                                        break
                                trial[label + "_vertices"] = (
                                    [list(x) for x in proposal]
                                    if proposal else None)
                                trial[label + "_found"] = bool(proposal)
                            trial["source_FCu_leg_found"] = (
                                trial["source_FCu_found"])
                            trial["existing_via_BCu_leg_found"] = (
                                trial["target_BCu_found"])
                            trial["status"] = (
                                "one_via_exact_zero_and_two_mesh_legs_only"
                                if (trial["source_FCu_leg_found"]
                                    and trial["existing_via_BCu_leg_found"])
                                else "exact_zero_via_but_copper_leg_missing")
                            break
                    finally:
                        if created is not None:
                            board.Remove(created)
                            created = None
                        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                        restored_l3 = pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                        if not exact_native_difference(
                                l3_baseline, restored_l3)["native_both_empty"]:
                            raise RuntimeError(
                                "CH027 site trial failed exact native L3 rollback")
                if not trial["native_L3_both_exactly_zero"]:
                    trial["status"] = "all_sampled_one_via_L3_gates_failed"
        finally:
            if created is not None:
                board.Remove(created)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                recovered = pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
                if not exact_native_difference(
                        l3_baseline, recovered)["native_both_empty"]:
                    raise RuntimeError("CH027 test failed exact L3 rollback")
            for item in four:
                board.Add(item)
            if track_inventory(board) != originals:
                raise RuntimeError("CH027 one-via original restitution failed")
            trial["originals_all_restituted"] = True
        out["CH027_one_via_native_L3_and_mesh_trial"] = trial
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

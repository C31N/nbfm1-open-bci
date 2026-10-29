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

def precise_bcu_barrier_inventory(board: Any, parts: list[Any],
                                  source_index: int, target_index: int
                                  ) -> dict[str, Any]:
    """Identify native UUID blockers at a polygon-gap, never authorize
    protected copper ripup. Geometric screening is not a causal DRC proof.
    """
    import pcbnew
    import re
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points

    a, b = nearest_points(parts[source_index], parts[target_index])
    gap = LineString((a, b))
    # 0.225 mm captures a 0.15-mm trace plus 0.15-mm clearance
    # for proximity only; actual KiCad DRC remains mandatory.
    corridor = gap.buffer(.225)
    rows: list[dict[str, Any]] = []

    def record(uid: str, net: str, kind: str, copper: Any,
               layer: str) -> None:
        if net == NET:
            return
        distance = float(gap.distance(copper))
        if not copper.intersects(corridor):
            return
        eligible = (kind == "track" and layer == "B.Cu"
                    and re.fullmatch(
                        r"CH0(?:1[6-9]|2[0-9]|3[01])_.*", net) is not None
                    and net not in POWER and net not in (
                        "VCM", "MUX_EN", "AGND", "MUX_S0"))
        rows.append({
            "uuid": uid, "net": net, "kind": kind, "layer": layer,
            "distance_to_gap_mm": round(distance, 9),
            "intersects_225um_survey_corridor": True,
            "classification": ("reviewed_Block2_BCu_track_candidate"
                               if eligible else "immutable_do_not_ripup"),
            "micro_ripup_candidate": bool(eligible),
            "DRC_qualified": False,
        })

    for track in board.GetTracks():
        uid = track.m_Uuid.AsString()
        net = track.GetNetname()
        if isinstance(track, pcbnew.PCB_VIA):
            copper = Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
            record(uid, net, "via", copper, "through")
        elif track.GetLayer() == pcbnew.B_Cu:
            if isinstance(track, pcbnew.PCB_ARC):
                bb = track.GetBoundingBox()
                copper = box(
                    pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                    pcbnew.ToMM(bb.GetRight()),
                    pcbnew.ToMM(bb.GetBottom()))
                record(uid, net, "arc", copper, "B.Cu")
            else:
                copper = LineString((
                    xy(track.GetStart()), xy(track.GetEnd()))).buffer(
                    pcbnew.ToMM(track.GetWidth()) / 2)
                record(uid, net, "track", copper, "B.Cu")
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.IsOnLayer(pcbnew.B_Cu):
                record(pad.m_Uuid.AsString(), pad.GetNetname(),
                       "pad", pad_copper_shape(pad, pcbnew.B_Cu),
                       "B.Cu")
    rows.sort(key=lambda x: (x["distance_to_gap_mm"],
                             x["classification"] !=
                             "immutable_do_not_ripup", x["uuid"]))
    allowed = [x for x in rows if x["micro_ripup_candidate"]]
    immutable = [x for x in rows if not x["micro_ripup_candidate"]]
    return {
        "source_component": source_index,
        "target_component": target_index,
        "minimum_gap_mm": round(float(a.distance(b)), 9),
        "from_mm": [round(a.x, 6), round(a.y, 6)],
        "to_mm": [round(b.x, 6), round(b.y, 6)],
        "blocker_count": len(rows),
        "immutable_count": len(immutable),
        "eligible_Block2_track_count": len(allowed),
        "eligible_UUIDs": [x["uuid"] for x in allowed],
        "nearby_immutable_UUIDs": [x["uuid"] for x in immutable],
        "nearest_barrier_objects": rows[:45],
        "native_DRC_qualified": False,
        "causal_copper_removal_verified": False,
    }


def bcu_alternative_component_graph(board: Any, parts: list[Any],
                                    source_index: int, target_index: int
                                    ) -> dict[str, Any]:
    """Exhaustive topology-only survey of locally adjacent BCu free islands.

    Never authorizes removal of protected copper; transition edges are
    ONLY gap/proximity hypotheses, not electrically valid copper routes.
    """
    from heapq import heappop, heappush
    from shapely.strtree import STRtree

    tree = STRtree(parts)
    candidates: list[tuple[float, int, int]] = []
    for i, poly in enumerate(parts):
        for idx in tree.query(poly.buffer(1.0)):
            j = int(idx)
            if j <= i:
                continue
            distance = float(poly.distance(parts[j]))
            if 0 < distance <= 1.0:
                candidates.append((distance, i, j))
    candidates.sort()
    # Examine EVERY geometrically adjacent gap, including longer ones.
    # Previous 120-edge cap discarded 67 of 187 candidates and could hide
    # a protected-free detour; a negative result was not exhaustive.
    edges = []
    graph: dict[int, list[tuple[int, int, float]]] = {}
    for distance, a, b in candidates:
        row = precise_bcu_barrier_inventory(board, parts, a, b)
        item = {
            "components": [a, b],
            "gap_mm": round(distance, 9),
            "from_mm": row["from_mm"], "to_mm": row["to_mm"],
            "eligible_UUIDs": row["eligible_UUIDs"],
            "immutable_count": row["immutable_count"],
            "protected_transition": bool(row["immutable_count"]),
            "native_DRC_qualified": False,
        }
        edge_id = len(edges)
        edges.append(item)
        if not item["protected_transition"]:
            cost = 1 + 10 * len(item["eligible_UUIDs"]) + distance
            graph.setdefault(a, []).append((b, edge_id, cost))
            graph.setdefault(b, []).append((a, edge_id, cost))
    frontier: list[tuple[float, int, tuple[int, ...]]] = [
        (0.0, source_index, ())]
    best: dict[int, float] = {}
    candidate_path = []
    while frontier:
        score, node, path = heappop(frontier)
        if node in best and best[node] <= score:
            continue
        best[node] = score
        if node == target_index:
            candidate_path = [edges[k] for k in path]
            break
        for other, edge_id, cost in graph.get(node, []):
            if score + cost < best.get(other, float("inf")):
                heappush(frontier, (score + cost, other,
                                    (*path, edge_id)))
    # Reachability and the immutable frontier from BOTH terminals,
    # on the complete protected-free graph only.
    def reachable(start: int) -> set[int]:
        pending = [start]
        found = set()
        while pending:
            node = pending.pop()
            if node in found:
                continue
            found.add(node)
            pending.extend(other for other, _, _ in graph.get(node, [])
                           if other not in found)
        return found

    source_reach = reachable(source_index)
    target_reach = reachable(target_index)
    frontier_edges = [
        e for e in edges
        if e["protected_transition"] and (
            (e["components"][0] in source_reach) !=
            (e["components"][1] in source_reach))]
    frontier_edges.sort(key=lambda row: (
        row["immutable_count"], len(row["eligible_UUIDs"]),
        row["gap_mm"], row["components"]))
    return {
        "evaluated_gap_count": len(edges),
        "candidate_gap_count": len(candidates),
        "survey_truncated": False,
        "source_reachable_components": sorted(source_reach),
        "target_reachable_components": sorted(target_reach),
        "source_frontier_protected_count": len(frontier_edges),
        "source_frontier_protected_examples": frontier_edges[:15],
        "unprotected_transition_count": sum(
            not row["protected_transition"] for row in edges),
        "route_of_free_islands_found": bool(candidate_path),
        "unprotected_transition_path": candidate_path,
        "nearby_transitions": edges[:30],
        "topology_only_not_physical_route": True,
        "native_DRC_qualified": False,
    }


def screen_reversible_bcu_victims(
        board: Any, positions: dict[str, tuple[float, float]],
        region: Any, code: int, original: dict[str, Any],
        protected: dict[str, Any]) -> dict[str, Any]:
    """Probe ONLY reviewed B.Cu Block2 tracks, restoring every UUID.

    This tests B.Cu annulus component reachability, NOT a physical route.
    VCM, all vias, BANK1, pads, zones, MUX_EN and Block1 remain untouched.
    """
    import itertools
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles

    eligible = {
        "1af03929-f221-4ea1-ab5e-ddff36173f8f": "MUX_S1",
        "d290f858-1074-4d29-ba47-ef2b8dd84658": "MUX_S2",
        "b452e6ba-e3e6-4670-a83d-48fb38f528de": "CH027_N_MUX",
    }
    locked = {tr.m_Uuid.AsString(): tr for tr in board.GetTracks()}
    for uid, net in eligible.items():
        track = locked.get(uid)
        if (track is None or track.GetNetname() != net
                or track.GetLayer() != pcbnew.B_Cu
                or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise RuntimeError("Unreviewed Block2 B.Cu cut " + uid)
    rows = []
    source_vias = (SRC_VIA, SRC_ALT_VIA)
    target_vias = (DST_VIA, DST_ALT_VIA)
    ids = tuple(eligible)
    for size in (1, 2, 3):
        for subset in itertools.combinations(ids, size):
            row: dict[str, Any] = {
                "virtually_removed_UUIDs": list(subset),
                "nets": [eligible[uid] for uid in subset],
                "restored_originals": False,
                "physical_route_qualified": False,
                "no_new_vias": True,
                "In1_Cu_used": False,
            }
            for uid in subset:
                board.Remove(locked[uid])
            try:
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Protected vias/pads/zones touched")
                foreign, _ = obstacles(
                    board, code, .15, .15, region, .65,
                    (pcbnew.B_Cu, pcbnew.F_Cu))
                free = region.difference(unary_union([
                    foreign[0], bcu_power_copper_guard(board)])).buffer(-.000005)
                regions = polygons(free)
                contacts = {}
                for uid in (*source_vias, *target_vias):
                    annulus = Point(positions[uid]).buffer(.315)
                    contacts[uid] = [
                        index for index, area in enumerate(regions)
                        if area.intersection(annulus).area > .000001]
                pairs = [
                    {"source_UUID": source, "target_UUID": target,
                     "free_components": sorted(set(contacts[source])
                                               & set(contacts[target]))}
                    for source in source_vias for target in target_vias
                ]
                row["BCu_free_components"] = len(regions)
                row["via_pair_reachability"] = pairs
                row["geometric_pair_connected"] = any(
                    pair["free_components"] for pair in pairs)
                row["status"] = (
                    "geometric_path_only_needs_native_reroute"
                    if row["geometric_pair_connected"] else
                    "VCM_protected_BCu_partition_remains")
            finally:
                for uid in subset:
                    board.Add(locked[uid])
                if track_inventory(board) != original:
                    raise RuntimeError("BCu trial failed exact track rollback")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("BCu trial changed protected geometry")
                row["restored_originals"] = True
            rows.append(row)
    return {
        "case_count": len(rows),
        "all_originals_restituted": all(r["restored_originals"] for r in rows),
        "any_geometric_pair_connected": any(
            r["geometric_pair_connected"] for r in rows),
        "native_DRC_qualified": False,
        "virtual_ripup_only": True,
        "victim_subsets": rows,
    }


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
        "BCu_gap_barrier_inventory": None,
        "BCu_alternative_component_graph": None,
        "BCu_reversible_Block2_victim_subsets": None,
        "micro_ripup_trial": {
            "performed": False, "restored": True,
            "new_vias": False, "DRC_qualified": False,
            "physical_closure_qualified": False,
        },
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
        source_component = next(
            x["BCu_centre_component"]
            for x in report["existing_CH025_vias"]
            if x["uuid"] == SRC_VIA)
        target_component = next(
            x["BCu_centre_component"]
            for x in report["existing_CH025_vias"]
            if x["uuid"] == DST_VIA)
        if source_component is None or target_component is None:
            raise RuntimeError("Bestands-Vias outside BCu free-space polygon")
        report["BCu_gap_barrier_inventory"] = precise_bcu_barrier_inventory(
            board, parts, source_component, target_component)
        report["BCu_alternative_component_graph"] = (
            bcu_alternative_component_graph(
                board, parts, source_component, target_component))
        report["BCu_reversible_Block2_victim_subsets"] = (
            screen_reversible_bcu_victims(
                board, positions, region, code, before, protected))
        # Micro-selective candidate screening is deliberately fail-closed:
        # moving any protected copper is prohibited, even on a scratch board.
        barrier = report["BCu_gap_barrier_inventory"]
        micro = report["micro_ripup_trial"]
        if (barrier["immutable_count"] == 0
                and barrier["eligible_Block2_track_count"] == 1):
            uid = barrier["eligible_UUIDs"][0]
            eligible = tracks[uid]
            if (eligible.GetLayer() != pcbnew.B_Cu
                    or isinstance(eligible, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                raise RuntimeError("Block2 candidate changed identity")
            endpoints = (xy(eligible.GetStart()), xy(eligible.GetEnd()))
            signal_name = eligible.GetNetname()
            micro.update(
                performed=True, removed_UUID=uid,
                moved_signal=signal_name,
                original_endpoints_mm=[list(x) for x in endpoints],
                proposed_BCu_CH025_path=False,
                proposed_BCu_neighbor_restitution=False,
                restored=False)
            board.Remove(eligible)
            temporary_tracks: list[Any] = []
            try:
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Ripup changed protected pad/via/zone")
                # A single reversible rip-up; CH025 is routed from existing
                # through-via to existing through-via. No via placement.
                candidate_path = mesh_route(
                    board, positions[SRC_VIA], positions[DST_VIA], code,
                    (pcbnew.B_Cu, pcbnew.F_Cu),
                    filled(next(z for z in board.Zones()
                                if z.m_Uuid.AsString() == ZONE)),
                    region, start_layer=0, goal_layer=0,
                    allow_vias=False,
                    extra_obstacles=[
                        bcu_power_copper_guard(board),
                        GeometryCollection()])
                if (candidate_path is not None and len(candidate_path) >= 2
                        and all(x[0] == 0 for x in candidate_path)):
                    micro["proposed_BCu_CH025_path"] = True
                    original_track_ids = {
                        track.m_Uuid.AsString()
                        for track in board.GetTracks()}
                    for first, second in zip(
                            candidate_path, candidate_path[1:]):
                        make_track(
                            board, tuple(first[1:]), tuple(second[1:]),
                            code, .15, pcbnew.B_Cu)
                    # make_track returns None: capture only actual SWIG
                    # PCB_TRACK items, and remove those before restitution.
                    temporary_tracks = [
                        track for track in board.GetTracks()
                        if track.m_Uuid.AsString()
                        not in original_track_ids]
                    # Independent same-layer restitution must fit AFTER CH025.
                    replacement = mesh_route(
                        board, endpoints[0], endpoints[1],
                        board.FindNet(signal_name).GetNetCode(),
                        (pcbnew.B_Cu, pcbnew.F_Cu),
                        filled(next(z for z in board.Zones()
                                    if z.m_Uuid.AsString() == ZONE)),
                        region, start_layer=0, goal_layer=0,
                        allow_vias=False,
                        extra_obstacles=[
                            bcu_power_copper_guard(board),
                            GeometryCollection()])
                    if (replacement is not None and len(replacement) >= 2
                            and all(x[0] == 0 for x in replacement)):
                        micro["proposed_BCu_neighbor_restitution"] = True
                        micro["new_neighbor_path_mm"] = [
                            list(x) for x in replacement]
            finally:
                for item in temporary_tracks:
                    board.Remove(item)
                board.Add(eligible)
                if track_inventory(board) != before:
                    raise RuntimeError("Micro ripup fails exact track restore")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Protected copper changed after micro trial")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                if not (every_zero(polygon_delta(
                        base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
                        and every_zero(polygon_delta(
                            base_l3, polygon_snapshot(board, pcbnew.In2_Cu)))):
                    raise RuntimeError("In1 or L3 changed in scratch rollback")
                micro["restored"] = True
        else:
            micro["not_attempted_reason"] = (
                "protected_barriers_present" if barrier["immutable_count"]
                else "not_exactly_one_reviewed_Block2_BCu_track")
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

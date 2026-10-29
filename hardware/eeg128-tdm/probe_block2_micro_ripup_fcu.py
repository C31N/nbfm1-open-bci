#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded virtual Block2 micro-ripup, F.Cu reachability, guarded restitution.

Native original is SHA-pinned. Only a fixed, reviewed UUID whitelist can be
temporarily removed. All originals must be reinstalled byte-geometrically
on rollback. Physical route qualification requires restoration of EVERY
selected Block2 signal, exact L3, and native KiCad 8.0.9 DRC.
Never promote a checkpoint or output fabrication assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from escape_mesh_505 import polygons
from native_connectivity import regressed_nets
from probe_ch025_cooperative8 import (
    CH027_ALT_VIA, unchanged_fingerprints,
)
from probe_ch025_fcu_l3_exact import (
    ZONE, track_inventory, power_fcu_obstacles,
)
from probe_ch025_neighbor_restitution7 import NEIGHBORS
from probe_ch027_annulus_s0_native import (
    CH027, CUT, S0_UUIDS, CH027_VIA_LANDINGS_MM,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    add_path, search, metrics, native, obstacles, routing_domain, xy,
)

S1 = "2ac3aecb-9a62-4bc7-846a-75a782ad0474"
S2 = "d63cd5b4-9b79-4d97-8e66-1895bb81d615"
CH030 = "3a4fd855-0c62-4287-b912-c9d8725d2b24"
# Initial three trials retain original long S0 and all its existing copper.
# Subsequent trials remove S0-long ONLY on scratch and require restitution.
CASE_VICTIMS = (
    (S1,), (S2,), (CH030,),
    (S0_UUIDS[0], S1), (S0_UUIDS[0], S2),
    (S0_UUIDS[0], CH030),
    (*S0_UUIDS, S1), (*S0_UUIDS, CH030),
    (S1, *S0_UUIDS), (S1, *S0_UUIDS),
)
FLAGS = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "In1_Cu_used": False,
}

def run(candidate: Path, index: int, report_path: Path | None = None) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box, LineString
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    if index not in range(len(CASE_VICTIMS)):
        raise ValueError("Unreviewed micro-ripup order")
    victims = CASE_VICTIMS[index]
    out: dict[str, Any] = {
        **FLAGS, "status": "not_started",
        "case_index": index, "selected_UUIDs": list(victims),
        "source_archive_untouched": False,
        "baseline_native_DRC": None,
        "protected_originals_restituted": False,
        "S0_originals_restituted": False,
        "native_3V3A_loss_mm2": None,
        "native_3V3A_gain_mm2": None,
        "native_3V3A_exact_zero": False,
        "native_DRC_qualified": False,
        "complete_restitution_geometry_found": False,
        "native_CH027_closed": False,
        "no_new_vias": True,
        "topology_only": True,
        "FCu_reachability": [],
        "new_track_count": 0,
    }
    def save_progress(stage: str) -> None:
        out["last_native_stage"] = stage
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(out, indent=2) + "\n")

    save_progress("native_preflight")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Native KiCad 8.0.9 required")
    locked_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="block2-micro-ripup-") as tmp:
        folder = Path(tmp)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unreviewed engineering input members")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Pinned 139 source identity mismatch")
            if any(audit.get(k) is not False
                   for k in ("accepted", "fabrication_release",
                             "routing_completed",
                             "routing_replay_byteidentical_verified")):
                raise RuntimeError("Unsafe engineering input release state")
            for name in MEMBERS:
                (folder / name).write_bytes(z.read(name))
        pcb_path = folder / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("Pinned MUX_EN/CH019 board mismatch")
        baseline = native(pcb_path, folder / "baseline-native.json")
        out["baseline_native_DRC"] = metrics(baseline)
        save_progress("baseline_native_DRC_recorded")
        if out["baseline_native_DRC"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            out["status"] = "baseline_139_gate_failed"
            return out
        board = pcbnew.LoadBoard(str(pcb_path))
        initial = track_inventory(board)
        protected = unchanged_fingerprints(board)
        existing_ids = set(initial)
        current = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        selected = (CUT, *victims)
        if len(set(selected)) != len(selected):
            raise RuntimeError("Duplicate original selected")
        via = current.get(CH027_ALT_VIA)
        if not isinstance(via, pcbnew.PCB_VIA) or via.GetNetname() != CH027:
            raise RuntimeError("Existing CH027 via changed")
        via_pos = xy(via.GetPosition())
        via_radius = pcbnew.ToMM(via.GetWidth()) / 2
        immutable_start = None
        endpoint_map: dict[str, tuple[Any, Any]] = {}
        for uid in selected:
            tr = current.get(uid)
            expected = (
                CH027 if uid == CUT else
                "MUX_S0" if uid in S0_UUIDS else NEIGHBORS[uid])
            if (tr is None or tr.GetNetname() != expected
                    or tr.GetLayer() != pcbnew.F_Cu
                    or isinstance(tr, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                raise RuntimeError("Unreviewed original UUID " + uid)
            endpoint_map[uid] = (
                xy(tr.GetStart()), xy(tr.GetEnd()))
            if uid == CUT:
                immutable_start = endpoint_map[uid][0]
        assert immutable_start is not None
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Protected In2 3V3A zone absent")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        original_l3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        start_code = board.FindNet(CH027).GetNetCode()
        domain = routing_domain(board, .075, .25)
        # Only short-window contours are used for this diagnostic.
        region = domain.intersection(box(
            min(immutable_start[0], via_pos[0]) - 4.5,
            min(immutable_start[1], via_pos[1]) - 4.5,
            max(immutable_start[0], via_pos[0]) + 4.5,
            max(immutable_start[1], via_pos[1]) + 4.5))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        out["selected_originals_verified"] = True
        for uid in selected:
            board.Remove(current[uid])
        try:
            save_progress("virtual_micro_ripup_started")
            save_progress("protected_fingerprint_read_started")
            post_protected = unchanged_fingerprints(board)
            save_progress("protected_fingerprint_read_completed")
            if post_protected != protected:
                raise RuntimeError("Immutable via, pad or zone changed")
            save_progress("track_inventory_read_started")
            inventory_after_cut = track_inventory(board)
            save_progress("track_inventory_read_completed")
            if any(inventory_after_cut.get(uid) != val
                   for uid, val in initial.items()
                   if uid not in selected):
                raise RuntimeError("Unselected original changed")
            save_progress("foreign_copper_geometry_started")
            foreign, _ = obstacles(
                board, start_code, .15, .15, region, .60,
                (pcbnew.F_Cu, pcbnew.B_Cu))
            guard = power_fcu_obstacles(board)
            free = region.difference(
                unary_union([foreign[0], guard])).buffer(-.000005)
            parts = polygons(free)
            tree = STRtree(parts)

            def component(pt: tuple[float, float]) -> int | None:
                point = Point(pt)
                return next((int(i) for i in tree.query(point)
                             if parts[int(i)].covers(point)), None)

            save_progress("BCu_FCu_free_component_scan_complete")
            source_part = component(immutable_start)
            reachable_contact = None
            for contact in CH027_VIA_LANDINGS_MM:
                if math.dist(via_pos, contact) >= via_radius - .01:
                    raise RuntimeError("Contact not inside unchanged via")
                target_part = component(contact)
                linked = (source_part is not None
                          and source_part == target_part)
                out["FCu_reachability"].append({
                    "contact_mm": list(contact),
                    "source_part": source_part,
                    "target_part": target_part,
                    "same_free_FCu_component": linked,
                })
                if linked and reachable_contact is None:
                    reachable_contact = contact
            out["free_FCu_component_count"] = len(parts)
            out["source_free_FCu_component"] = source_part
            out["geometric_contact_reachable"] = (
                reachable_contact is not None)
            if reachable_contact is None:
                out["status"] = "virtual_cuts_do_not_open_CH027_FCu"
            else:
                out["status"] = "CH027_FCu_component_open_only_topology"
                out["chosen_contact_mm"] = list(reachable_contact)
                # Triangulate only an already connected, local, simple
                # polygon. This is a hard budget, NOT a negative route proof.
                shape = parts[source_part]
                vertices = (
                    len(shape.exterior.coords)
                    + sum(len(r.coords) for r in shape.interiors))
                out["selected_component_vertices"] = vertices
                save_progress("CH027_topological_reachability_recorded")
                # A bounded deterministic single-layer A* replaces the
                # 9238-vertex Delaunay mesh that exceeded its complexity cap.
                # The original copper changes remain confined to reviewed
                # net UUIDs. Native DRC is mandatory for final geometry.
                save_progress("bounded_CH027_FCu_Astar_started")
                # Reserve S1's original corridor as a soft priority
                # in alternate schedule 9; it is not protected copper
                # but restitution must succeed for any accepted proposal.
                s1_soft_guard = LineString(
                    endpoint_map[S1]).buffer(.32)
                cost_regions = (
                    ((0, s1_soft_guard, 60.0),)
                    if index == 9 else ())
                out["S1_soft_reservation_applied"] = index == 9
                out["victim_restitution_order"] = list(victims)
                save_progress("S1_restitution_priority_selected")
                proposal = search(
                    board, immutable_start, reachable_contact, start_code,
                    .15, .15, False, 4.5, step=.18,
                    max_nodes=40000, deadline=time.monotonic() + 24,
                    start_layer=0, goal_layer=0,
                    layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                    cost_regions=cost_regions)
                if (proposal is not None and len(proposal) >= 2
                        and all(pt[0] == 0 for pt in proposal)):
                    out["CH027_Astar_proposal"] = [list(p) for p in proposal]
                    save_progress("CH027_FCu_Astar_geometry_found")
                    add_path(board, proposal, start_code, .15,
                             layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    full_restitution = True
                    for uid in victims:
                        start, end = endpoint_map[uid]
                        victim_code = board.FindNet(
                            current[uid].GetNetname()).GetNetCode()
                        out["active_victim_restitution_UUID"] = uid
                        save_progress("bounded_FCu_neighbor_Astar_started")
                        replacement = search(
                            board, start, end, victim_code,
                            .15, .15, False, 5.0, step=.18,
                            max_nodes=45000,
                            deadline=time.monotonic() + 22,
                            start_layer=0, goal_layer=0,
                            layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        if (replacement is None or len(replacement) < 2
                                or any(pt[0] != 0 for pt in replacement)):
                            full_restitution = False
                            out["failed_victim_restitution"] = uid
                            save_progress("victim_restitution_search_failed")
                            break
                        add_path(board, replacement, victim_code, .15,
                                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        save_progress("victim_FCu_track_added")
                    out["complete_restitution_geometry_found"] = (
                        full_restitution)
                    if not full_restitution:
                        out["status"] = "victim_FCu_restitution_incomplete"
                    if full_restitution:
                        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                        delta = exact_native_difference(
                            original_l3,
                            pcbnew.SHAPE_POLY_SET(
                                zone.GetFilledPolysList(pcbnew.In2_Cu)))
                        out["native_3V3A_loss_mm2"] = (
                            delta["loss_native_mm2"])
                        out["native_3V3A_gain_mm2"] = (
                            delta["gain_native_mm2"])
                        out["native_3V3A_exact_zero"] = (
                            delta["native_both_empty"])
                        if delta["native_both_empty"]:
                            scratch_dir = folder / "scratch"
                            scratch_dir.mkdir()
                            for name in MEMBERS[1:]:
                                shutil.copyfile(folder / name,
                                                scratch_dir / name)
                            scratch = scratch_dir / MEMBERS[0]
                            pcbnew.SaveBoard(str(scratch), board)
                            post = native(scratch, folder / "post.json")
                            out["native_post_DRC"] = metrics(post)
                            out["regressed_nets"] = regressed_nets(
                                baseline, post)
                            out["native_DRC_qualified"] = (
                                metrics(post)["violations"] == 0
                                and metrics(post)["warnings"] == 0
                                and metrics(post)["unconnected"] < 139
                                and not out["regressed_nets"])
                            out["native_CH027_closed"] = (
                                out["native_DRC_qualified"])
                            out["status"] = (
                                "native_CH027_and_all_victims_DRC_qualified"
                                if out["native_DRC_qualified"] else
                                "post_native_DRC_or_connectivity_failed")
        finally:
            extra_tracks = [
                item for item in board.GetTracks()
                if item.m_Uuid.AsString() not in existing_ids]
            out["new_track_count"] = len(extra_tracks)
            for tr in extra_tracks:
                board.Remove(tr)
            for uid in selected:
                board.Add(current[uid])
            if track_inventory(board) != initial:
                raise RuntimeError("Original tracks not exactly restituted")
            if unchanged_fingerprints(board) != protected:
                raise RuntimeError("Protected vias pads or zones changed")
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            delta = exact_native_difference(
                original_l3,
                pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu)))
            if not delta["native_both_empty"]:
                raise RuntimeError("Native L3 rollback not exact")
            out["protected_originals_restituted"] = True
            save_progress("originals_and_L3_native_restituted")
            out["S0_originals_restituted"] = all(
                track_inventory(board).get(uid) == initial[uid]
                for uid in S0_UUIDS)
        if not out["S0_originals_restituted"]:
            raise RuntimeError("Unmodified S0 originals not restored")
    out["source_archive_untouched"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == locked_hash)
    save_progress("micro_case_complete")
    return out

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-index", type=int,
                        choices=tuple(range(len(CASE_VICTIMS))),
                        required=True)
    args = parser.parse_args()
    result = run(args.candidate, args.case_index, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "case": result["case_index"],
        "contact_open": result.get("geometric_contact_reachable"),
        "native_DRC_qualified": result["native_DRC_qualified"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

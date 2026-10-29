#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native CH025 In2.Cu via-only topology and guarded routing, no release.

Same-net existing through vias only. In1 untouched, VCM/Block1/MUX_EN/
CH022 unchanged, no new vias or keepouts. A new In2.Cu track may ONLY be
qualified when native 3V3A loss AND gain are identically zero, and native
KiCad 8.0.9 reports 0 violations and 0 warnings with improved connectivity.
Even a passing *single-net* candidate is NOT 136-accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from analyze_ch025_l3_native_refill import filled
from escape_mesh_505 import polygons
from native_connectivity import regressed_nets
from probe_ch025_cooperative8 import (
    SRC_VIA, DST_VIA, unchanged_fingerprints,
)
from probe_ch025_existing_vias_bcu import SRC_ALT_VIA, DST_ALT_VIA
from probe_ch025_fcu_l3_exact import NET, ZONE, track_inventory
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    metrics, native, obstacles, routing_domain, search, add_path, xy,
)

SOURCES = (SRC_VIA, SRC_ALT_VIA)
TARGETS = (DST_VIA, DST_ALT_VIA)
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "In1_Cu_used": False,
    "CH022_qualified": False, "native_136_qualified": False,
}

def in2_uuid_gap_inventory(
        board: Any, parts: list[Any], source: int, target: int,
        power: Any) -> dict[str, Any]:
    """Nearest native In2 component gap with protected UUID inventory.

    Proximity is a diagnostic, never a proof that a selected track caused
    the partition. Power-fill remains immutable and cannot be ripped up.
    """
    import pcbnew
    import re
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points
    from route_targeted_closure import pad_copper_shape

    first, second = nearest_points(parts[source], parts[target])
    gap = LineString((first, second))
    corridor = gap.buffer(.225)
    rows: list[dict[str, Any]] = []

    def insert(uid: str, net: str, kind: str, shape: Any,
               reference: str | None = None) -> None:
        if net == NET or not shape.intersects(corridor):
            return
        movable = (
            kind == "track"
            and (re.fullmatch(r"CH0(?:1[6-9]|2[0-9]|3[01])_.*", net)
                 is not None or net in ("MUX_S1", "MUX_S2", "MUX_S3"))
            and net not in ("VCM", "AGND", "MUX_EN", "3V3A"))
        rows.append({
            "uuid": uid, "net": net, "kind": kind,
            "footprint_reference": reference,
            "distance_to_component_gap_mm": round(
                float(shape.distance(gap)), 9),
            "temporary_ripup_eligible": bool(movable),
            "classification": (
                "Block2_In2_track_only_conditional"
                if movable else "protected_do_not_ripup"),
            "native_DRC_qualified": False,
        })

    for item in board.GetTracks():
        uid = item.m_Uuid.AsString()
        net = item.GetNetname()
        if isinstance(item, pcbnew.PCB_VIA):
            geom = Point(xy(item.GetPosition())).buffer(
                pcbnew.ToMM(item.GetWidth()) / 2)
            insert(uid, net, "via", geom)
        elif item.GetLayer() == pcbnew.In2_Cu:
            if isinstance(item, pcbnew.PCB_ARC):
                bounds = item.GetBoundingBox()
                geom = box(pcbnew.ToMM(bounds.GetX()),
                           pcbnew.ToMM(bounds.GetY()),
                           pcbnew.ToMM(bounds.GetRight()),
                           pcbnew.ToMM(bounds.GetBottom()))
                insert(uid, net, "arc", geom)
            else:
                from shapely.geometry import LineString
                geom = LineString((xy(item.GetStart()),
                                   xy(item.GetEnd()))).buffer(
                                       pcbnew.ToMM(item.GetWidth()) / 2)
                insert(uid, net, "track", geom)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.IsOnLayer(pcbnew.In2_Cu):
                insert(pad.m_Uuid.AsString(), pad.GetNetname(), "pad",
                       pad_copper_shape(pad, pcbnew.In2_Cu),
                       footprint.GetReference())
    rows.sort(key=lambda row: (
        row["distance_to_component_gap_mm"], row["uuid"]))
    power_overlap = power.buffer(.58).intersects(corridor)
    return {
        "source_In2_component": source,
        "target_In2_component": target,
        "minimum_gap_mm": round(float(first.distance(second)), 9),
        "gap_from_xy_mm": [round(first.x, 6), round(first.y, 6)],
        "gap_to_xy_mm": [round(second.x, 6), round(second.y, 6)],
        "native_3V3A_power_buffer_intersects_gap": bool(power_overlap),
        "protected_3V3A_is_unmodifiable": True,
        "candidate_track_UUIDs": [
            item["uuid"] for item in rows
            if item["temporary_ripup_eligible"]],
        "protected_copper_UUIDs": [
            item["uuid"] for item in rows
            if not item["temporary_ripup_eligible"]],
        "reviewed_copper_objects": rows[:60],
        "inventory_object_count": len(rows),
        "physical_route_qualified": False,
        "proof_of_causal_barrier": False,
    }


def reversible_in2_track_cut(
        board: Any, eligible: list[str],
        original: dict[str, Any], protected: dict[str, Any],
        base_in1: dict[str, Any], baseline_L3: Any,
        zone: Any, region: Any, positions: dict[str, Any],
        power: Any) -> dict[str, Any]:
    """Strict single-track isolated trial, no new via or protected edits.

    Never route through changed 3V3A polygons; only report if same-net
    existing-via annuli meet within an immutable free In2 component.
    """
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from probe_ch025_neutral_via_sites import (
        polygon_snapshot, polygon_delta, every_zero)
    from shapely.strtree import STRtree

    out: dict[str, Any] = {
        "selected_UUID": None,
        "attempted": False,
        "originals_restituted": True,
        "protected_geometry_unchanged": True,
        "native_In1_exact_after_rollback": False,
        "native_L3_exact_after_rollback": False,
        "all_4_vias_unchanged": False,
        "geometrically_connected_after_cut": False,
        "native_DRC_qualified": False,
    }
    # A single exact reviewed segment is the only first-stage cut.
    if len(eligible) != 1:
        out["not_attempted_reason"] = (
            "no_eligible_In2_track" if not eligible
            else "multiple_eligible_In2_tracks_need_independent_review")
        return out
    uid = eligible[0]
    tracks = {item.m_Uuid.AsString(): item
              for item in board.GetTracks()}
    victim = tracks[uid]
    if (victim.GetLayer() != pcbnew.In2_Cu
            or isinstance(victim, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
            or victim.GetNetname() in (
                "VCM", "MUX_EN", "AGND", "3V3A")):
        raise RuntimeError("In2 victim is not an approved signal track")
    original_vias = {
        key for key, t in tracks.items() if isinstance(t, pcbnew.PCB_VIA)}
    out["selected_UUID"] = uid
    out["attempted"] = True
    board.Remove(victim)
    try:
        if unchanged_fingerprints(board) != protected:
            raise RuntimeError("Protected pads/vias/zones mutated")
        if any(track_inventory(board).get(k) != val
               for k, val in original.items() if k != uid):
            raise RuntimeError("Unselected original track changed")
        code = board.FindNet(NET).GetNetCode()
        foreign, _ = obstacles(
            board, code, .15, .15, region, .65,
            (pcbnew.In2_Cu, pcbnew.B_Cu))
        free = region.difference(unary_union([
            foreign[0], power.buffer(.58)])).buffer(-.000005)
        candidate_regions = polygons(free)
        tree = STRtree(candidate_regions)
        contact = {}
        for key in (*SOURCES, *TARGETS):
            pad = Point(positions[key]).buffer(.29)
            contact[key] = {
                int(i) for i in tree.query(pad)
                if candidate_regions[int(i)].intersects(pad)}
        out["geometrically_connected_after_cut"] = any(
            contact[a] & contact[b]
            for a in SOURCES for b in TARGETS)
        out["component_count_after_cut"] = len(candidate_regions)
    finally:
        board.Add(victim)
        out["originals_restituted"] = track_inventory(board) == original
        out["protected_geometry_unchanged"] = (
            unchanged_fingerprints(board) == protected)
        out["all_4_vias_unchanged"] = all(
            k in {item.m_Uuid.AsString() for item in board.GetTracks()}
            for k in (*SOURCES, *TARGETS))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        out["native_In1_exact_after_rollback"] = every_zero(
            polygon_delta(base_in1,
                          polygon_snapshot(board, pcbnew.In1_Cu)))
        out["native_L3_exact_after_rollback"] = (
            exact_native_difference(
                baseline_L3,
                pcbnew.SHAPE_POLY_SET(
                    zone.GetFilledPolysList(pcbnew.In2_Cu))
            )["native_both_empty"])
        if not all(out[key] for key in (
                "originals_restituted",
                "protected_geometry_unchanged",
                "all_4_vias_unchanged",
                "native_In1_exact_after_rollback",
                "native_L3_exact_after_rollback")):
            raise RuntimeError("Reversible In2 micro-ripup rollback failed")
    return out


def run(candidate: Path, report_path: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    report: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started",
        "source_archive_unchanged": False,
        "source_PCB_sha256": PINNED_CANDIDATE_SHA,
        "native_139_baseline": None,
        "source_originals_unchanged": False,
        "all_existing_vias_unchanged": False,
        "native_In1_exact": False, "native_3V3A_exact": False,
        "new_vias_added": 0,
        "candidate_in2_route_qualified": False,
        "existing_CH025_vias": [],
        "existing_via_pairs": [],
        "In2_component_count": 0,
        "In2_power_buffer_mm": .58,
        "geometrically_connected_pairs": 0,
        "search_attempted": False,
        "In2_candidate_gap_inventories": [],
        "In2_reversible_micro_ripup_trials": [],
    }

    def save(stage: str) -> None:
        report["stage"] = stage
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    save("preflight")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    archive_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="CH025-existing-In2-") as d:
        folder = Path(d)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unreviewed source engineering ZIP")
            audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if audit.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Source 139 checkpoint mismatch")
            if any(audit.get(flag) is not False
                   for flag in ("accepted", "fabrication_release",
                                "routing_completed",
                                "routing_replay_byteidentical_verified")):
                raise RuntimeError("Source engineering release flags changed")
            for name in MEMBERS:
                (folder / name).write_bytes(z.read(name))
        pcb_file = folder / MEMBERS[0]
        if hashlib.sha256(pcb_file.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Protected MUX_EN source PCB SHA mismatch")
        baseline = native(pcb_file, folder / "before.json")
        report["native_139_baseline"] = metrics(baseline)
        save("baseline_DRC")
        if report["native_139_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            report["status"] = "baseline_gate_failed"
            return report
        board = pcbnew.LoadBoard(str(pcb_file))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        original_via_ids = {
            t.m_Uuid.AsString() for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)
        }
        current = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        positions = {}
        for uid in (*SOURCES, *TARGETS):
            via = current.get(uid)
            if (not isinstance(via, pcbnew.PCB_VIA)
                    or via.GetNetname() != NET
                    or via.GetViaType() != pcbnew.VIATYPE_THROUGH):
                raise RuntimeError("CH025 existing through-via changed: " + uid)
            positions[uid] = xy(via.GetPosition())
            report["existing_CH025_vias"].append({
                "uuid": uid, "xy_mm": list(positions[uid]),
                "diameter_mm": pcbnew.ToMM(via.GetWidth()),
                "type": "existing_through_via",
            })
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Protected 3V3A native zone missing")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        base_L3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        from probe_ch025_neutral_via_sites import polygon_snapshot, polygon_delta, every_zero
        base_in1 = polygon_snapshot(board, pcbnew.In1_Cu)
        domain = routing_domain(board, .075, .25)
        region = domain.intersection(box(24.0, 8.0, 57.0, 57.0))
        code = board.FindNet(NET).GetNetCode()
        foreign, _ = obstacles(
            board, code, .15, .15, region, .65,
            (pcbnew.In2_Cu, pcbnew.B_Cu))
        # A 0.15-mm track must remain at least 0.505 mm away from the
        # existing L3 3V3A polygon. Buffer by .505+.075 exactly.
        power = filled(zone)
        prohibited = unary_union([
            foreign[0], power.buffer(.58)])
        free = region.difference(prohibited).buffer(-.000005)
        components = polygons(free)
        report["In2_component_count"] = len(components)
        tree = STRtree(components)

        def contacts(uid: str) -> list[dict[str, Any]]:
            via = current[uid]
            annulus = Point(positions[uid]).buffer(
                pcbnew.ToMM(via.GetWidth()) / 2 - .01)
            options = []
            for idx in tree.query(annulus):
                overlap = components[int(idx)].intersection(annulus)
                if overlap.area > 0.000001:
                    location = overlap.representative_point()
                    options.append({
                        "component": int(idx),
                        "contact_xy_mm": [
                            round(location.x, 6), round(location.y, 6)],
                        "overlap_mm2": round(overlap.area, 9),
                    })
            return sorted(options, key=lambda v: (
                -v["overlap_mm2"], v["component"]))

        via_contacts = {uid: contacts(uid) for uid in positions}
        for a in SOURCES:
            for b in TARGETS:
                ac = {x["component"] for x in via_contacts[a]}
                bc = {x["component"] for x in via_contacts[b]}
                common = sorted(ac & bc)
                row = {
                    "source_uuid": a, "target_uuid": b,
                    "source_xy_mm": list(positions[a]),
                    "target_xy_mm": list(positions[b]),
                    "source_In2_components": sorted(ac),
                    "target_In2_components": sorted(bc),
                    "common_In2_components": common,
                    "geometrically_connected": bool(common),
                    "native_DRC_qualified": False,
                    "physical_In2_route_qualified": False,
                    "requires_new_vias": False,
                    "In1_Cu_modified": False,
                }
                report["existing_via_pairs"].append(row)
        report["geometrically_connected_pairs"] = sum(
            x["geometrically_connected"] for x in report["existing_via_pairs"])
        # Resolve both distinct source-to-target free-component gaps.
        # This screen is a proximity inventory, NOT ripup authorization.
        for target in sorted({
                idx for row in report["existing_via_pairs"]
                for idx in row["target_In2_components"]}):
            source_ids = sorted({
                idx for row in report["existing_via_pairs"]
                for idx in row["source_In2_components"]})
            if not source_ids:
                raise RuntimeError("Missing source In2 free copper")
            for source_idx in source_ids:
                gap = in2_uuid_gap_inventory(
                    board, components, source_idx, target, power)
                report["In2_candidate_gap_inventories"].append(gap)
                if (not gap["native_3V3A_power_buffer_intersects_gap"]
                        and not gap["protected_copper_UUIDs"]
                        and len(gap["candidate_track_UUIDs"]) == 1):
                    trial = reversible_in2_track_cut(
                        board, gap["candidate_track_UUIDs"],
                        original, protected, base_in1, base_L3,
                        zone, region, positions, power)
                    trial["source_In2_component"] = source_idx
                    trial["target_In2_component"] = target
                    report["In2_reversible_micro_ripup_trials"].append(
                        trial)
                else:
                    report["In2_reversible_micro_ripup_trials"].append({
                        "source_In2_component": source_idx,
                        "target_In2_component": target,
                        "attempted": False,
                        "native_DRC_qualified": False,
                        "reason": (
                            "protected_3V3A_or_other_copper_at_gap"
                            if gap["native_3V3A_power_buffer_intersects_gap"]
                            or gap["protected_copper_UUIDs"]
                            else "requires_more_than_one_reviewed_In2_track"),
                    })
        save("In2_UUID_gap_and_reversible_copper_cut_screen_complete")
        save("In2_same_net_via_topology_complete")
        # Probe at most ONE reachable pair on the already-pinned PCB.
        # This search is native DRC gated; absence within deadline is NOT
        # a mathematical proof of a disconnected corridor.
        qualified = False
        for row in report["existing_via_pairs"]:
            if not row["geometrically_connected"]:
                continue
            report["search_attempted"] = True
            save("bounded_In2_A_star_started")
            candidate_path = search(
                board, positions[row["source_uuid"]],
                positions[row["target_uuid"]], code,
                .15, .15, False, 5.0, step=.20,
                max_nodes=35000, deadline=time.monotonic()+25,
                start_layer=1, goal_layer=1,
                reserved_bottom=power.buffer(.505),
                layers=(pcbnew.B_Cu, pcbnew.In2_Cu))
            if candidate_path is None or len(candidate_path) < 2:
                row["status"] = "bounded_In2_search_no_path"
                save("bounded_In2_A_star_no_path")
                break
            if any(pt[0] != 1 for pt in candidate_path):
                raise RuntimeError("Unexpected B.Cu / via transition")
            row["candidate_In2_waypoints"] = [list(pt) for pt in candidate_path]
            old_uids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            try:
                add_path(board, candidate_path, code, .15,
                         layers=(pcbnew.B_Cu, pcbnew.In2_Cu))
                if any(track_inventory(board).get(uid) != val
                       for uid, val in original.items()):
                    raise RuntimeError("Original copper changed")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Protected pads / vias / zones changed")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                delta = exact_native_difference(
                    base_L3, pcbnew.SHAPE_POLY_SET(
                        zone.GetFilledPolysList(pcbnew.In2_Cu)))
                row["L3_loss_native_mm2"] = delta["loss_native_mm2"]
                row["L3_gain_native_mm2"] = delta["gain_native_mm2"]
                row["L3_exact_zero"] = delta["native_both_empty"]
                row["In1_exact_zero"] = every_zero(polygon_delta(
                    base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
                save("native_In2_zone_fill_examined")
                if row["L3_exact_zero"] and row["In1_exact_zero"]:
                    scratch = folder / "scratch"
                    scratch.mkdir()
                    for name in MEMBERS[1:]:
                        shutil.copyfile(folder / name, scratch / name)
                    scratch_pcb = scratch / MEMBERS[0]
                    pcbnew.SaveBoard(str(scratch_pcb), board)
                    drc = native(scratch_pcb, folder / "post.json")
                    row["post_native_DRC"] = metrics(drc)
                    row["regressed_nets"] = regressed_nets(baseline, drc)
                    qualified = (
                        metrics(drc)["violations"] == 0
                        and metrics(drc)["warnings"] == 0
                        and metrics(drc)["unconnected"] < 139
                        and not row["regressed_nets"])
                    row["native_DRC_qualified"] = qualified
                    row["physical_In2_route_qualified"] = qualified
                    save("native_In2_DRC_completed")
            finally:
                additions = [t for t in board.GetTracks()
                             if t.m_Uuid.AsString() not in old_uids]
                for tr in additions:
                    board.Remove(tr)
                if track_inventory(board) != original:
                    raise RuntimeError("Original tracks not restituted")
                if unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Original vias, pads, zone not restituted")
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                if not exact_native_difference(
                        base_L3, pcbnew.SHAPE_POLY_SET(
                            zone.GetFilledPolysList(pcbnew.In2_Cu))
                        )["native_both_empty"]:
                    raise RuntimeError("In2 3V3A native rollback not exact")
            break
        report["source_originals_unchanged"] = (
            track_inventory(board) == original
            and unchanged_fingerprints(board) == protected)
        new_vias = {t.m_Uuid.AsString() for t in board.GetTracks()
                    if isinstance(t, pcbnew.PCB_VIA)}
        report["all_existing_vias_unchanged"] = new_vias == original_via_ids
        report["native_In1_exact"] = every_zero(polygon_delta(
            base_in1, polygon_snapshot(board, pcbnew.In1_Cu)))
        report["native_3V3A_exact"] = exact_native_difference(
            base_L3, pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu)))["native_both_empty"]
        report["candidate_in2_route_qualified"] = qualified
        report["status"] = (
            "CH025_single_net_In2_native_DRC_pass_no_release"
            if qualified else
            "CH025_In2_existing_via_route_not_qualified")
        save("native_original_and_zone_rollback_completed")
    report["source_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == archive_hash)
    save("complete")
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = run(args.candidate, args.output)
    print(json.dumps({
        "status": data["status"],
        "In2_pair_count": len(data["existing_via_pairs"]),
        "connected_pair_count": data["geometrically_connected_pairs"],
        "native_DRC_qualified": data["candidate_in2_route_qualified"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

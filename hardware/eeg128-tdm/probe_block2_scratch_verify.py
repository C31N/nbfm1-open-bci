#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only native KiCad 8.0.9 geometry at the ACTUAL post-201-cut PCB.

All points and route prefixes are immutable samples from native run #77.
No Set*, SaveBoard, fill, routing, restitution, or release operation.
Positive clearance means only an F.Cu copper precheck, never full DRC.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point
from probe_block2_native_fcu_bottleneck import collect
from probe_block2_search_choke_uuid import rank_fcu_witnesses

STEP = .22
TRACK = .15
CLEAR = .15
PITCH = .300
NETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
U3_UUIDS = {
    "dd561592-853d-47ee-a2f3-f824a719d539": ("U3/14", "MUX_S2"),
    "f4b26f43-58b6-4dc4-8789-dcc2834acc56": ("U3/13", "MUX_S3"),
}
DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1),
        (-1, 0), (-1, -1), (0, -1), (1, -1))
# From run #77 native 0.22-mm raster. This is NOT a fresh route proposal.
RUN77 = {
    "MAX_GOAL_PROGRESS": (
        ((93, 99),),
        ((95, 99),),
        ((97, 99), (98, 100), (98, 101)),
    ),
    "STAGGERED_EVADE": (
        ((93, 99), (94, 98), (95, 97), (96, 98)),
        ((95, 99),),
        ((97, 99), (98, 100), (98, 101)),
    ),
    "LATERAL_EVADE": (
        ((93, 99),),
        ((95, 99), (94, 98), (95, 98), (96, 98)),
        ((97, 99), (98, 100), (98, 101)),
    ),
}
# Native #77 uses origin x=25.265, y=12.650: derive from
# (grid 93,99) -> (45.725,34.430), never round to pad centres.
ORIGIN = (45.725 - 93 * STEP, 34.430 - 99 * STEP)


def pos(node: tuple[int, int]) -> tuple[float, float]:
    return (round(ORIGIN[0] + STEP * node[0], 6),
            round(ORIGIN[1] + STEP * node[1], 6))


def route_geom(route: tuple[tuple[int, int], ...]) -> Any:
    coords = [pos(node) for node in route]
    return Point(coords[0]) if len(coords) == 1 else LineString(coords)


def find_uuids(board: Any, pcbnew: Any) -> dict[str, dict[str, Any]]:
    """Real PCB UUIDs, not a static JSON index or 139-board assumption."""
    result: dict[str, dict[str, Any]] = {}
    for foot in board.GetFootprints():
        for pad in foot.Pads():
            uid = pad.m_Uuid.AsString()
            result[uid] = {
                "uuid": uid, "kind": "PAD",
                "name": foot.GetReference() + "/" + pad.GetNumber(),
                "net": pad.GetNetname() or "",
                "layer": "F.Cu" if pad.IsOnLayer(pcbnew.F_Cu)
                else "other_pad_layer",
            }
    for track in board.GetTracks():
        uid = track.m_Uuid.AsString()
        is_via = isinstance(track, pcbnew.PCB_VIA)
        result[uid] = {
            "uuid": uid,
            "kind": "VIA" if is_via else "TRACK",
            "name": "VIA" if is_via else "TRACK",
            "net": track.GetNetname() or "",
            "layer": "F.Cu" if track.IsOnLayer(pcbnew.F_Cu)
            else "non_F.Cu",
        }
    for zone in board.Zones():
        uid = zone.m_Uuid.AsString()
        result[uid] = {
            "uuid": uid, "kind": "ZONE", "name": "ZONE",
            "net": zone.GetNetname() or "",
            "layer": "F.Cu" if zone.IsOnLayer(pcbnew.F_Cu)
            else "non_F.Cu",
        }
    return result


def directions_at_scratch(
    objects: list[Any], *, max_witnesses: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    states: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    for role, routes in RUN77.items():
        if len(routes) != 3:
            raise RuntimeError("Invalid three-net source sample")
        lines = [route_geom(route) for route in routes]
        heads = [pos(route[-1]) for route in routes]
        single = []
        by_net_heading = {}
        for i, net in enumerate(NETS):
            for h, (dx, dy) in enumerate(DIRS):
                start = routes[i][-1]
                dest = (start[0] + dx, start[1] + dy)
                a, b = pos(start), pos(dest)
                segment = LineString((a, b))
                blocked_by_revisit = dest in routes[i]
                # The same 0.300-mm hard centreline clearance against
                # the full existing other-net route histories.
                peer_pitch = min(segment.distance(other) for j, other
                                 in enumerate(lines) if i != j)
                peer_deficit = max(0., PITCH - peer_pitch)
                witnesses = [
                    {**item, "provenance": "actual_post_201_cut_scratch_PCB"}
                    for item in rank_fcu_witnesses(
                        objects, net, a, b, set(), limit=max_witnesses)]
                verified_blockers = [
                    o for o in witnesses
                    if o["measurement_method"] !=
                    "unqualified_display_polygon_estimate"
                    and o["new_trace_copper_gap_mm"] < CLEAR - 1e-8]
                approximate_blockers = [
                    o for o in witnesses
                    if o["measurement_method"] ==
                    "unqualified_display_polygon_estimate"
                    and o["new_trace_copper_gap_mm"] < CLEAR - 1e-8]
                if blocked_by_revisit:
                    category = "SELF_REVISIT"
                elif verified_blockers:
                    category = "SCRATCH_FIXED_FCU_COPPER"
                elif peer_pitch < PITCH - 1e-8:
                    category = "THREE_NET_HISTORY_PITCH"
                elif approximate_blockers:
                    category = "UNQUALIFIED_COPPER_ESTIMATE"
                else:
                    category = "FCU_SINGLE_STEP_PRECHECK_ONLY"
                totals[category] = totals.get(category, 0) + 1
                data = {
                    "net": net, "heading_index": h,
                    "direction_grid": [dx, dy],
                    "from_mm": list(a), "to_mm": list(b),
                    "scratch_classification": category,
                    "peer_history_min_centreline_mm":
                        round(peer_pitch, 6),
                    "peer_pitch_deficit_mm": round(peer_deficit, 6),
                    "route_self_revisit": blocked_by_revisit,
                    "closest_fcu_objects": witnesses,
                    "unqualified_copper_or_mask_unchecked": True,
                    "standalone_step_not_a_three_net_solution": True,
                }
                single.append(data)
                by_net_heading[(i, h)] = data
        joint = joint_probe_variants(routes, by_net_heading)
        states.append({
            "sample_role": role,
            "heads": [{
                "net": net, "xy_mm": list(heads[i]),
                "route_grid": [list(p) for p in routes[i]],
                "heading_index": (DIRS.index((
                    routes[i][-1][0] - routes[i][-2][0],
                    routes[i][-1][1] - routes[i][-2][1]))
                    if len(routes[i]) >= 2 else 0),
            } for i, net in enumerate(NETS)],
            "direction_probes": single,
            "joint_scratch_probes": joint,
        })
    return states, dict(sorted(totals.items()))


def joint_probe_variants(
    routes: tuple[tuple[tuple[int, int], ...], ...],
    lookup: dict[tuple[int, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    from itertools import combinations
    headings = []
    for route in routes:
        delta = ((route[-1][0] - route[-2][0],
                  route[-1][1] - route[-2][1])
                 if len(route) > 1 else (1, 0))
        headings.append(DIRS.index(delta))
    variants: list[tuple[str, dict[int, int]]] = []
    for hold in range(3):
        moving = [i for i in range(3) if i != hold]
        for da, db in ((0, 0), (-1, 0), (1, 0),
                       (0, -1), (0, 1), (-2, 0), (0, 2)):
            variants.append((
                "STAGGERED_HOLD_" + NETS[hold],
                {moving[0]: (headings[moving[0]] + da) % 8,
                 moving[1]: (headings[moving[1]] + db) % 8},
            ))
    for da, db, dc in ((-1, 0, 1), (1, 0, -1),
                       (0, -1, 1), (0, 1, -1),
                       (-2, 0, 2), (2, 0, -2)):
        variants.append(("ASYMMETRIC", {
            i: (headings[i] + shift) % 8
            for i, shift in enumerate((da, db, dc))
        }))
    results = []
    for family, movement in variants:
        segments = {}
        blocked = []
        for i, heading in movement.items():
            probe = lookup[(i, heading)]
            if probe["scratch_classification"] != "FCU_SINGLE_STEP_PRECHECK_ONLY":
                blocked.append({
                    "net": NETS[i],
                    "reason": probe["scratch_classification"],
                })
            segments[i] = LineString((
                probe["from_mm"], probe["to_mm"]))
        # An additional simultaneous conflict can exist even if all
        # independent moves cleared the old other-net traces.
        for i, j in combinations(segments, 2):
            if segments[i].distance(segments[j]) < PITCH - 1e-8:
                blocked.append({
                    "nets": [NETS[i], NETS[j]],
                    "reason": "SIMULTANEOUS_NEW_SEGMENT_PITCH",
                })
        results.append({
            "family": family,
            "headings": {NETS[i]: h for i, h in movement.items()},
            "held_nets": [NETS[i] for i in range(3) if i not in movement],
            "scratch_one_step_precheck": (
                "NOT_BLOCKED_BY_MODELED_FCU_COPPER_OR_HISTORY"
                if not blocked else "BLOCKED"),
            "blockers": blocked[:8],
            "not_full_route_qualification": True,
        })
    return results


def analyze_scratch(
    board_path: Path, removed_victims: set[str],
    replaced_ch038: set[str],
    *,
    expected_sha256: str | None = None,
    removed_victim_net_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Inspects exact persisted post-cut scratch bytes; no PCB write."""
    import pcbnew

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Wrong native KiCad version")
    if len(removed_victims) != 201 or len(replaced_ch038) != 2:
        raise RuntimeError("Unqualified victim/CH038 UUID inventory")
    if removed_victims & replaced_ch038:
        raise RuntimeError("Protected CH038 overlap with victim whitelist")
    if (removed_victim_net_map is not None
            and set(removed_victim_net_map) != removed_victims):
        raise RuntimeError("Victim UUID-to-net map does not match cut")
    before = hashlib.sha256(board_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and expected_sha256 != before:
        raise RuntimeError("Scratch board changed since verified post-cut gate")
    board = pcbnew.LoadBoard(str(board_path))
    all_items = find_uuids(board, pcbnew)
    actually_remaining = sorted(removed_victims.intersection(all_items))
    if actually_remaining:
        raise RuntimeError(
            "201-cut failed; victim UUIDs remain: "
            + ",".join(actually_remaining[:5]))
    present_replaced = sorted(replaced_ch038.intersection(all_items))
    if present_replaced:
        raise RuntimeError("Old CH038 protected UUIDs unexpectedly remain")
    u3 = []
    for uid, (name, net) in U3_UUIDS.items():
        observed = all_items.get(uid)
        u3.append({
            "uuid": uid, "required_ref": name, "required_net": net,
            "present_in_scratch": observed is not None,
            "removed_in_201_cut": uid in removed_victims,
            "actual_object": observed,
            "name_and_net_match": (
                observed is not None
                and observed["name"] == name
                and observed["net"] == net
                and observed["layer"] == "F.Cu"),
        })
    if not all(w["name_and_net_match"] for w in u3):
        raise RuntimeError("U3 identity missing or incorrect in scratch PCB")

    points = [pos(r[-1]) for routes in RUN77.values() for r in routes]
    centre = ((min(p[0] for p in points) + max(p[0] for p in points)) / 2,
              (min(p[1] for p in points) + max(p[1] for p in points)) / 2)
    span = max(
        max(abs(p[0]-centre[0]) for p in points),
        max(abs(p[1]-centre[1]) for p in points)) + 1.5
    copper, warnings = collect(board, centre, span, pcbnew)
    states, counts = directions_at_scratch(copper)
    # Every witness UUID comes directly from the loaded scratch board.
    if any(obj.uid not in all_items for obj in copper):
        raise RuntimeError("Copper witness missing from scratch board inventory")
    after = hashlib.sha256(board_path.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("Read-only scratch verification mutated board bytes")
    return {
        "schema": "block2_actual_scratch_post201_geometry_v1",
        "scratch_board_sha256_before_and_after": before,
        "post_cut_sha256_pinned": expected_sha256 == before
        if expected_sha256 is not None else None,
        "pcb_source": "actual_NBODY_0_post_201_cut_scratch_PCB",
        "kicad_version": pcbnew.Version(),
        "u3_witnesses": u3,
        "removed_victim_uuids_count": len(removed_victims),
        "victim_uuids_present_after_cut": actually_remaining,
        "old_ch038_uuids_present_after_replacement": present_replaced,
        "scratch_fcu_object_count": len(copper),
        "scratch_fcu_objects": [
            {**item.describe(), "layer": "F.Cu"} for item in copper],
        "ch031_scratch_fcu_objects_in_roi": [
            {**item.describe(), "layer": "F.Cu"}
            for item in copper if item.net == "CH031_N_MUX"],
        "ch031_scratch_fcu_uuids_anywhere": sorted(
            uid for uid, item in all_items.items()
            if item["net"] == "CH031_N_MUX"
            and item["layer"] == "F.Cu"),
        "ch031_removed_victim_uuids": (
            sorted(uid for uid, net in removed_victim_net_map.items()
                   if net == "CH031_N_MUX")
            if removed_victim_net_map is not None else None),
        "scratch_fcu_geometry_warnings": warnings,
        "three_net_state_count": len(states),
        "scratch_direction_counts": counts,
        "states": states,
        "three_track_global_cut_proven": False,
        "all_keepouts_and_roi_gates_included": False,
        "single_step_pass_is_not_full_route_proof": True,
        "new_vias_added": 0,
        "restoration_attempted": False,
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
    }

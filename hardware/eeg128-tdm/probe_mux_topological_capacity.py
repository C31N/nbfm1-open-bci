#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only F.Cu cross-section upper-bound capacity for three MUX controls.

The result is a necessary local capacity bound, NOT a proof that a complete
three-net route exists. An insufficient sampled cut disproves routing within
the stated Y band. An ample sampled cut never licenses placement or release.
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

from shapely.geometry import LineString, box
from shapely.ops import unary_union

from analyze_ch025_fcu_blocker_uuids import (
    ARCHIVE_SHA256, BOARD_SHA256, MEMBERS, copper_shapes,
)
from probe_ch025_cooperative8 import pinned_items, unchanged_fingerprints
from ch025_mux_joint import TRIPLET, MIN_CENTER_SEPARATION_MM

WIDTH_MM = .15
CLEARANCE_MM = .15
POWER_CLEARANCE_MM = .505
EDGE_CLEARANCE_MM = .25
NEEDED_CENTRE_SPAN_MM = 2 * MIN_CENTER_SEPARATION_MM
# Tested native original terminal anchors (not speculative A* geometry).
TERMINALS = {
    "MUX_EN": ((27.8179, 37.1976), (43.8939, 37.1976)),
    "MUX_S2": ((44.9121, 37.4994), (27.6930, 37.4994)),
    "MUX_S3": ((26.4572, 37.8222), (45.8284, 37.8222)),
}
FLAGS = dict(
    accepted=False, routing_completed=False, fabrication_release=False,
    manufacturing_files=False, manufacturing_export_invoked=False,
    checkpoint_promoted=False, independent_replay_verified=False,
    native_DRC_qualified=False, native_parity_pass=False,
    source_copper_modified=False, In1_Cu_used=False,
)


def read_slices(domain: Any, obstacles: list[Any], x0: float, x1: float,
                low: float, high: float, increment: float = .2
                ) -> list[dict[str, Any]]:
    """Exact Shapely vertical cut geometry; finite sampling is only a bound."""
    if not (x0 < x1 and low < high and increment > 0):
        raise ValueError("Invalid cross-section range")
    covered = unary_union(obstacles) if obstacles else None
    rows = []
    count = int(math.ceil((x1 - x0) / increment))
    for index in range(count + 1):
        x = min(x1, x0 + index * increment)
        section = LineString(((x, low), (x, high))).intersection(domain)
        if covered is not None:
            section = section.difference(covered)
        intervals = []
        stack = [section]
        while stack:
            item = stack.pop()
            if item.is_empty:
                continue
            if item.geom_type in ("MultiLineString", "GeometryCollection"):
                stack.extend(item.geoms)
            elif item.geom_type == "LineString":
                lo, hi = sorted(p[1] for p in item.coords)
                if hi - lo > .000001:
                    intervals.append([round(lo, 6), round(hi, 6)])
        intervals.sort()
        lanes = sum(
            max(0, int(math.floor((b - a - .000002) /
                                  MIN_CENTER_SEPARATION_MM)) + 1)
            for a, b in intervals
        )
        rows.append(dict(x_mm=round(x, 6),
                         free_centerline_intervals_y_mm=intervals,
                         maximum_independent_centerline_slots=lanes,
                         widest_interval_mm=round(
                             max((b-a for a,b in intervals), default=0), 6)))
    return rows



def assess_straight_bundle(domain: Any,
                           retained: list[tuple[Any, dict[str, Any]]]
                           ) -> dict[str, Any]:
    """Prove or reject the immutable-copper straight three-lane candidate.

    Existing same-net copper may connect at an endpoint, but foreign copper
    must not intersect the clearance-expanded candidate centreline. All
    selected temporary original tracks are excluded by the caller. This is
    only a read-only candidate classification; filled zones and native DRC
    remain separate release gates.
    """
    lines = {net: LineString(TERMINALS[net]) for net in TRIPLET}
    pairwise = {
        a + ":" + b: round(lines[a].distance(lines[b]), 9)
        for i, a in enumerate(TRIPLET)
        for b in TRIPLET[i + 1:]
    }
    rows = []
    for net in TRIPLET:
        line = lines[net]
        hits = []
        for geom, entry in retained:
            if entry["net"] == net or not geom.intersects(line):
                continue
            contact = geom.intersection(line)
            spot = contact.representative_point()
            hits.append(dict(
                uuid=entry["uuid"], net=entry["net"],
                protected=entry["protected"], kind=entry["kind"],
                contact_xy_mm=[round(spot.x, 6), round(spot.y, 6)],
            ))
        hits.sort(key=lambda x: (not x["protected"],
                                 x["net"], x["uuid"]))
        rows.append(dict(
            net=net, original_start_xy_mm=list(TERMINALS[net][0]),
            original_end_xy_mm=list(TERMINALS[net][1]),
            straight_length_mm=round(line.length, 6),
            board_edge_valid=bool(domain.covers(line)),
            fixed_copper_blocker_count=len(hits),
            protected_blocker_count=sum(x["protected"] for x in hits),
            blocking_original_uuids=hits[:32],
            blocker_list_truncated=len(hits) > 32,
        ))
    separated = all(distance >= MIN_CENTER_SEPARATION_MM
                    for distance in pairwise.values())
    clear = separated and all(row["board_edge_valid"] and
                              row["fixed_copper_blocker_count"] == 0
                              for row in rows)
    return dict(
        status=("flat_three_lane_candidate_prequalified_only"
                if clear else "flat_three_lane_candidate_blocked"),
        candidate_lines=rows, pairwise_centerline_distances_mm=pairwise,
        pairwise_separation_pass=separated,
        static_copper_straight_bundle_feasible=clear,
        additional_mesh_turns_needed=not clear,
        model_is_FCu_polygon_geometry_only=True,
        verified_full_native_DRC=False, native_parity_qualified=False,
        complete_eight_net_qualified=False,
        allowed_CH022_closure=False, checkpoint_promotion_allowed=False,
        fabrication_release=False,
    )



def assess_en_bypass(domain: Any,
                     retained: list[tuple[Any, dict[str, Any]]]
                     ) -> dict[str, Any]:
    """Read-only connectivity of the EN free-space with S2/S3 kept straight.

    Polygon connectivity is a necessary *topological* condition for a legal
    route in a chosen rectangular band, not a routed copper or DRC proof.
    The S2 and S3 tracks are hypothetical fixed obstacles, never written.
    """
    from shapely.geometry import Point, Polygon

    src = Point(TERMINALS["MUX_EN"][0])
    dst = Point(TERMINALS["MUX_EN"][1])
    s2 = LineString(TERMINALS["MUX_S2"])
    s3 = LineString(TERMINALS["MUX_S3"])
    locked_guards = [
        path.buffer(WIDTH_MM / 2 + CLEARANCE_MM + .00001)
        for path in (s2, s3)
    ]
    mx = (TERMINALS["MUX_EN"][0][1] +
          TERMINALS["MUX_S2"][0][1] +
          TERMINALS["MUX_S3"][0][1]) / 3
    west = min(p[0] for p in TERMINALS["MUX_EN"]) - 1.0
    east = max(p[0] for p in TERMINALS["MUX_EN"]) + 1.0
    pad = next((shape for shape, entry in retained
                if entry["uuid"] ==
                "5be286e6-1938-4e59-b1de-fce18e9c3615"), None)
    bands: list[dict[str, Any]] = []
    for halfheight in (1.5, 3.0, 5.0):
        local = box(west, mx - halfheight,
                    east, mx + halfheight).intersection(domain)
        blockers = [
            shape.intersection(local) for shape, entry in retained
            if entry["net"] != "MUX_EN" and shape.intersects(local)
        ]
        blocked = unary_union([*blockers, *locked_guards])
        available = local.difference(blocked).buffer(-.000005)
        if available.geom_type == "Polygon":
            components = [available]
        elif available.geom_type == "MultiPolygon":
            components = list(available.geoms)
        elif available.geom_type == "GeometryCollection":
            components = [g for g in available.geoms
                          if isinstance(g, Polygon)]
        else:
            components = []
        connected = any(part.covers(src) and part.covers(dst)
                        for part in components)
        bands.append(dict(
            halfheight_mm=halfheight,
            y_range_mm=[round(mx - halfheight, 6),
                        round(mx + halfheight, 6)],
            fixed_copper_obstacle_count=len(blockers),
            free_components=len(components),
            source_in_free_space=any(part.covers(src)
                                     for part in components),
            target_in_free_space=any(part.covers(dst)
                                     for part in components),
            source_and_target_in_same_component=connected,
            straight_S2_S3_copper_held_fixed=True,
            guaranteed_trace_construction=False,
            native_DRC_qualified=False,
        ))
    return dict(
        status="en_fixed_s2_s3_bypass_component_survey",
        source_anchors_unchanged=True,
        S2_S3_reserved_without_PCB_changes=True,
        power_pad_UUID="5be286e6-1938-4e59-b1de-fce18e9c3615",
        power_pad_clearance_envelope_bounds_mm=(
            [round(x, 6) for x in pad.bounds] if pad is not None else None),
        bands=bands,
        all_bands_disconnected=all(
            not band["source_and_target_in_same_component"]
            for band in bands),
        global_board_topological_impossibility_proven=False,
        byte_identical_replay_proven=False,
        allowed_CH022_closure=False,
        accepted=False, fabrication_release=False,
    )




def via_side(x: float, left: float, right: float) -> str:
    """A 0.65-mm drill landing must clear the power pad by 0.505 mm."""
    radius = 0.325
    if x + radius + .505 < left:
        return "west"
    if x - radius - .505 > right:
        return "east"
    return "power_pad_exclusion"


def mux_en_bcu_via_hop(board: Any, zone: Any) -> dict[str, Any]:
    """Read-only existing-via inventory and two-side through-via windows.

    Uses KiCad native track/pad/zone geometry, not a saved routing candidate.
    B.Cu polygon connectivity does not imply an executable native route.
    """
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    from escape_mesh_505 import polygons
    from route_targeted_closure import (
        xy, obstacles, pad_copper_shape, routing_domain,
    )
    from analyze_ch025_l3_native_refill import filled
    from probe_ch025_cooperative8 import (
        CH027_ALT_VIA, unchanged_fingerprints,
    )

    snapshot = unchanged_fingerprints(board)
    pads = [pad for footprint in board.GetFootprints()
            for pad in footprint.Pads()
            if pad.m_Uuid.AsString() ==
            "5be286e6-1938-4e59-b1de-fce18e9c3615"]
    if len(pads) != 1 or pads[0].GetNetname() != "3V3A":
        raise ValueError("Pinned 3V3A pad changed")
    power_pad = pad_copper_shape(pads[0], pcbnew.F_Cu)
    left, _, right, _ = power_pad.bounds
    vias = [t for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)]
    if not any(v.m_Uuid.AsString() == CH027_ALT_VIA
               and v.GetNetname() == "CH027_N_MUX" for v in vias):
        raise ValueError("Protected CH027 via changed")
    power = filled(zone)
    if power.is_empty or not power.is_valid:
        raise ValueError("Pinned saved L3 copper unavailable")
    legal = routing_domain(board, .325, .25)
    region = legal.intersection(box(26.2, 34.5, 45.5, 40.5))
    code = board.FindNet("MUX_EN").GetNetCode()
    walls, via_block = obstacles(
        board, code, .15, .15, region, .65,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    # New vias cross F.Cu, In1.Cu, In2.Cu, and B.Cu. Never use In1
    # for traces and never carve power copper to justify a candidate.
    guards = [LineString(TERMINALS[name]).buffer(.325 + .075 + .15 + .00001)
              for name in ("MUX_S2", "MUX_S3")]
    blocked = unary_union([
        via_block, power.buffer(.325 + .505 + .00001),
        power_pad.buffer(.325 + .505 + .00001), *guards,
    ])
    via_free = region.difference(blocked).buffer(-.000005)
    fcu_free = region.difference(walls[0]).buffer(-.000005)
    bcu_free = region.difference(walls[1]).buffer(-.000005)
    components = polygons(bcu_free)

    def component(point: tuple[float, float]) -> int | None:
        p = Point(point)
        return next((i for i, shape in enumerate(components)
                     if shape.covers(p)), None)

    retained = [
        {"uuid": via.m_Uuid.AsString(),
         "xy_mm": list(xy(via.GetPosition())),
         "side": via_side(xy(via.GetPosition())[0], left, right),
         "through": via.GetViaType() == pcbnew.VIATYPE_THROUGH,
         "BCu_component": component(xy(via.GetPosition())),
         "source_target_connected_after_ripup": False}
        for via in vias if via.GetNetname() == "MUX_EN"
    ]
    samples: dict[str, list[dict[str, Any]]] = {"west": [], "east": []}
    for xi in range(65):
        x = round(27.5 + xi * .25, 6)
        side = via_side(x, left, right)
        if side not in samples:
            continue
        for yi in range(19):
            y = round(35.0 + yi * .25, 6)
            point = Point(x, y)
            if not (via_free.covers(point) and fcu_free.covers(point)
                    and bcu_free.covers(point)):
                continue
            index = component((x, y))
            if index is None:
                continue
            samples[side].append({
                "xy_mm": [x, y], "BCu_component": index,
                "distance_to_original_EN_mm": round(abs(y - 37.1976), 6),
                "native_DRC_qualified": False,
            })
    for side in samples:
        samples[side].sort(key=lambda value: (
            value["distance_to_original_EN_mm"], value["xy_mm"]))
    east = {}
    for row in samples["east"]:
        east.setdefault(row["BCu_component"], row)
    pairs = []
    for west in samples["west"]:
        other = east.get(west["BCu_component"])
        if other is None:
            continue
        direct = LineString((west["xy_mm"], other["xy_mm"]))
        pairs.append({
            "west_xy_mm": west["xy_mm"],
            "east_xy_mm": other["xy_mm"],
            "BCu_component": west["BCu_component"],
            "direct_BCu_clear": bcu_free.covers(direct),
            "distance_mm": round(direct.length, 6),
            "BCu_mesh_DRC_and_L3_exact_not_proven": True,
        })
    pairs.sort(key=lambda item: (
        not item["direct_BCu_clear"], item["distance_mm"],
        item["west_xy_mm"]))
    # Escalate only the B.Cu connectivity window. Existing F.Cu via samples
    # remain pinned; a wider B.Cu component is not native DRC proof.
    expanded: list[dict[str, Any]] = []
    for label, bounds in (
            ("local_6mm", (26.2, 34.5, 45.5, 40.5)),
            ("expanded_13mm", (25.0, 31.0, 47.0, 44.0)),
            ("expanded_27mm", (23.0, 24.0, 49.0, 51.0))):
        wide_region = legal.intersection(box(*bounds))
        wide_walls, _ = obstacles(
            board, code, .15, .15, wide_region, .65,
            (pcbnew.F_Cu, pcbnew.B_Cu))
        wide_free = wide_region.difference(wide_walls[1]).buffer(-.000005)
        wide_components = polygons(wide_free)

        def wide_index(point: list[float]) -> int | None:
            p = Point(point)
            return next((i for i, g in enumerate(wide_components)
                         if g.covers(p)), None)

        western = [(entry, wide_index(entry["xy_mm"]))
                   for entry in samples["west"]]
        eastern = [(entry, wide_index(entry["xy_mm"]))
                   for entry in samples["east"]]
        match = next((
            (w, e, wi) for w, wi in western for e, ei in eastern
            if wi is not None and wi == ei
        ), None)
        nearby_cut: dict[str, Any] | None = None
        if label == "expanded_27mm" and match is None:
            # One nearest disjoint free-space pair, NOT a global minimum
            # cut. UUID inventory guides further review without rip-up.
            separated = sorted((
                (wide_components[wi].distance(wide_components[ei]),
                 wi, ei)
                for _, wi in western for _, ei in eastern
                if wi is not None and ei is not None
            ), key=lambda row: (row[0], row[1], row[2]))
            if separated:
                from analyze_ch025_bcu_cut_uuids import survey as gap_survey
                _, west_id, east_id = separated[0]
                nearby_cut = gap_survey(
                    board, wide_components[west_id],
                    wide_components[east_id], target_net="MUX_EN")
        expanded.append({
            "nearest_BCu_gap_UUID_inventory": nearby_cut,
            "window_name": label,
            "bounds_mm": list(bounds),
            "free_BCu_components": len(wide_components),
            "west_components": sorted({
                index for _, index in western if index is not None}),
            "east_components": sorted({
                index for _, index in eastern if index is not None}),
            "same_free_BCu_component_found": match is not None,
            "example_west_east_mm": (
                [match[0]["xy_mm"], match[1]["xy_mm"]]
                if match is not None else None),
            "native_DRC_qualified": False,
            "zero_L3_area_change_qualified": False,
        })
    if unchanged_fingerprints(board) != snapshot:
        raise RuntimeError("Protected original pads, vias, zones modified")
    return {
        "status": "native_read_only_mux_en_bcu_via_window_inventory",
        "existing_same_net_vias": sorted(retained,
                                         key=lambda v: v["uuid"]),
        "new_via_windows_sampled": {
            k: len(v) for k, v in samples.items()},
        "via_samples": {k: v[:12] for k, v in samples.items()},
        "same_BCu_component_pairs": len(pairs),
        "expanded_BCu_component_survey": expanded,
        "proposed_BCu_via_pairs": pairs[:12],
        "power_pad_uuid": "5be286e6-1938-4e59-b1de-fce18e9c3615",
        "power_pad_bounds_mm": [round(v, 6) for v in power_pad.bounds],
        "CH027_via_fixed": CH027_ALT_VIA,
        "S2_S3_straight_reservations": True,
        "existing_BCu_zone_pours_not_independently_qualified": True,
        "new_vias_placed": False,
        "FCu_to_BCu_transition_DRC_qualified": False,
        "L3_power_loss_zero_qualified": False,
        "L3_power_gain_zero_qualified": False,
        "original_copper_changed": False,
        "sampling_step_mm": .25,
        "via_diameter_mm": .65,
        "power_clearance_mm": .505,
        "In1_Cu_used": False,
        "accepted": False, "fabrication_release": False,
        "routing_completed": False,
    }


def capacity(board: Any) -> dict[str, Any]:
    import pcbnew
    from route_targeted_closure import routing_domain, xy
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Native KiCad 8.0.9 required")
    start_fingerprint = unchanged_fingerprints(board)
    originals, zone, _ = pinned_items(board)
    if zone.GetNetname() != "3V3A" or set(TRIPLET) - set(originals):
        raise RuntimeError("Pinned native copper inventory mismatch")
    for net, anchors in TERMINALS.items():
        p = xy(originals[net].GetStart())
        q = xy(originals[net].GetEnd())
        if min(math.dist(p, anchors[0]) + math.dist(q, anchors[1]),
               math.dist(p, anchors[1]) + math.dist(q, anchors[0])) > .002:
            raise RuntimeError("Original MUX terminals drifted: " + net)
    excluded_uuids = {t.m_Uuid.AsString() for t in originals.values()}
    # Query copper polygons ON THE ORIGINAL BOARD. Do not actually rip up.
    shapes, entries = copper_shapes(board)
    retained = [(s, e) for s, e in zip(shapes, entries)
                if e["uuid"] not in excluded_uuids]
    # The general blocker helper intentionally skips all CH025 copper.
    # Existing non-selected CH025 F.Cu is an obstacle to the three MUX nets.
    for t in board.GetTracks():
        if (t.GetNetname() != "CH025_N_MUX" or
                t.GetLayer() != pcbnew.F_Cu or
                t.m_Uuid.AsString() in excluded_uuids):
            continue
        if isinstance(t, pcbnew.PCB_ARC):
            raise RuntimeError("Unmodelled original CH025 F.Cu arc")
        from shapely.geometry import Point
        if isinstance(t, pcbnew.PCB_VIA):
            geometry = Point(xy(t.GetPosition())).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
        else:
            geometry = LineString((xy(t.GetStart()), xy(t.GetEnd()))).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
        retained.append((geometry.buffer(CLEARANCE_MM + WIDTH_MM/2),
                         dict(uuid=t.m_Uuid.AsString(), net=t.GetNetname(),
                              kind="fixed_ch025", protected=True)))
    domain = routing_domain(board, WIDTH_MM/2, EDGE_CLEARANCE_MM)
    flat_bundle = assess_straight_bundle(domain, retained)
    en_bypass = assess_en_bypass(domain, retained)
    en_via_hop = mux_en_bcu_via_hop(board, zone)
    left = max(min(a[0], b[0]) for a, b in TERMINALS.values()) + .2
    right = min(max(a[0], b[0]) for a, b in TERMINALS.values()) - .2
    mid_y = sum((a[1]+b[1])/2 for a,b in TERMINALS.values())/3
    bands = []
    # Wider bands expose possible detours rather than asserting a global cut.
    for halfheight in (1.0, 2.0, 3.0, 5.0):
        low, high = mid_y - halfheight, mid_y + halfheight
        window = box(left-.1, low-.1, right+.1, high+.1)
        included = [(s,e) for s,e in retained if s.intersects(window)]
        rows = read_slices(domain, [s for s,_ in included],
                           left, right, low, high, .2)
        narrowest = min(rows, key=lambda r: (
            r["maximum_independent_centerline_slots"],
            r["widest_interval_mm"]))
        cut = LineString(((narrowest["x_mm"], low),
                          (narrowest["x_mm"], high)))
        touching = [dict(uuid=e["uuid"], net=e["net"],
                         kind=e["kind"], protected=e["protected"])
                    for s,e in included if s.intersects(cut)]
        bands.append(dict(
            y_range_mm=[round(low,6), round(high,6)],
            halfheight_mm=halfheight,
            sampled_sections=len(rows),
            upper_bound_minimum_slots=min(
                row["maximum_independent_centerline_slots"] for row in rows),
            sampled_local_three_lane_capacity_ruled_out=any(
                row["maximum_independent_centerline_slots"] < 3
                for row in rows),
            bottleneck=narrowest,
            blocker_inventory_on_bottleneck=touching[:60],
            blocker_inventory_truncated=len(touching)>60,
            nonblocking_sections_are_not_a_feasible_route_proof=True,
        ))
    if unchanged_fingerprints(board) != start_fingerprint:
        raise RuntimeError("Protected original pads, vias or zones changed")
    return dict(
        **FLAGS, status="read_only_local_topological_capacity_bound",
        baseline_airwires=139, target_airwires=136,
        F_Cu_only=True, model="original_tracks_vias_pads_no_new_copper",
        filled_FCu_zones_not_included=True,
        inference="missing obstacles can overestimate free space; an insufficient local cut is decisive only for its stated band",
        track_width_mm=WIDTH_MM, signal_clearance_mm=CLEARANCE_MM,
        power_clearance_mm=POWER_CLEARANCE_MM,
        edge_clearance_mm=EDGE_CLEARANCE_MM,
        pairwise_centerline_separation_mm=MIN_CENTER_SEPARATION_MM,
        required_three_centerline_span_mm=NEEDED_CENTRE_SPAN_MM,
        required_three_track_bare_copper_gap_mm=3*WIDTH_MM+4*CLEARANCE_MM,
        terminal_geometry_verified=True,
        selected_original_tracks_excluded=len(excluded_uuids),
        included_fixed_obstacle_count=len(retained),
        immutable_vias_verified=True,
        triplet=list(TRIPLET), flat_bundle=flat_bundle,
        en_bypass=en_bypass, EN_BCu_via_hop=en_via_hop, x_interval_mm=[round(left,6),round(right,6)],
        y_center_mm=round(mid_y,6), bands=bands,
        full_FCu_global_impossibility_proven=False,
        complete_three_net_route_proven=False,
        via_hop_feasibility_proven=False,
        pin_swap_schematic_parity_verified=False,
        native_DRC=None, L3_loss_mm2=None, L3_gain_mm2=None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    archive = a.archive.resolve()
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Refusing changed 139 checkpoint ZIP")
    with tempfile.TemporaryDirectory(prefix="mux-capacity-readonly-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as z:
            if sorted(z.namelist()) != sorted(MEMBERS):
                raise SystemExit("Unreviewed archive member list")
            for name in MEMBERS:
                (root/name).write_bytes(z.read(name))
        pcb_path = root / MEMBERS[0]
        if hashlib.sha256(pcb_path.read_bytes()).hexdigest() != BOARD_SHA256:
            raise SystemExit("Refusing changed native PCB")
        import pcbnew
        board = pcbnew.LoadBoard(str(pcb_path))
        result = capacity(board)
        if (hashlib.sha256(pcb_path.read_bytes()).hexdigest() != BOARD_SHA256
                or hashlib.sha256(archive.read_bytes()).hexdigest() !=
                ARCHIVE_SHA256):
            raise SystemExit("Immutable source changed")
        result["source_archive_sha256"] = ARCHIVE_SHA256
        result["source_pcb_sha256"] = BOARD_SHA256
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(dict(status=result["status"],
                              bands=[(b["halfheight_mm"],
                                      b["upper_bound_minimum_slots"])
                                     for b in result["bands"]],
                              accepted=False, fabrication_release=False)))


if __name__ == "__main__":
    main()

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


def read_slices(domain, obstacles, x0, x1, low, high, increment=.2):
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


def capacity(board):
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
        triplet=list(TRIPLET), x_interval_mm=[round(left,6),round(right,6)],
        y_center_mm=round(mid_y,6), bands=bands,
        full_FCu_global_impossibility_proven=False,
        complete_three_net_route_proven=False,
        via_hop_feasibility_proven=False,
        pin_swap_schematic_parity_verified=False,
        native_DRC=None, L3_loss_mm2=None, L3_gain_mm2=None,
    )


def main():
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

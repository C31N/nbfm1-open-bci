#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact native UUID inventory at CH022 In2.Cu 0.60001mm multihop gap.

Only read original KiCad copper; no board mutation or hardware promotion.
The gap connects FREE-SPACE components, not necessarily copper edges.
Vias, pads and reserved L3 power outline may be immovable blockers.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

KEEP_OUT_MM = .505
PROTECTED = frozenset({
    'VCM', 'AGND', 'CH017_N_ELECTRODE',
    'CH019_P_MUX', 'CH019_P_ELECTRODE',
    'CH024_P_MUX', 'CH024_P_ELECTRODE',
    'CH024_N_ELECTRODE', 'CH025_N_ELECTRODE',
    'CH026_P_ELECTRODE', 'CH026_P_MUX',
    'CH022_N_ELECTRODE',
})
POWER_HINTS = ('VCC', 'VDD', '3V3', 'VREG', 'AGND', 'GND', 'POWER')
FLAGS = {
    'model_only': True, 'accepted': False,
    'routing_completed': False, 'fabrication_release': False,
    'native_qualification': False, 'independent_replay_verified': False,
    'manufacturing_files': False,
}


def movement_class(net: str, kind: str, layer: str,
                   pad_distance: float, via_distance: float) -> str:
    """Conservative classification; never means a route is accepted."""
    if (net in PROTECTED or any(net.upper().startswith(s) for s in POWER_HINTS)
            or kind != 'track' or layer != 'In2.Cu'):
        return 'IMMUTABLE'
    if pad_distance < 1.0 or via_distance < .65:
        return 'PAD_OR_VIA_ESCAPE_PROTECTED'
    return 'CANDIDATE_REQUIRES_FULL_NATIVE_RESTITUTION'


def inventory(board: Any, graph: dict[str, Any], power: Any,
              ch022_net: str = 'CH022_N_ELECTRODE',
              lookaround_mm: float = 1.25) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    from route_targeted_closure import xy

    edges = graph.get('closest_disconnected_In2_gap_edges_mm')
    pair = graph.get('nearby_disconnected_In2_component_pair')
    report: dict[str, Any] = {
        **FLAGS, 'status': 'no_gap_edges', 'gap_free_space_not_copper': True,
        'gap_edges_mm': edges, 'component_pair': pair,
        'power_outline_keepout_mm': KEEP_OUT_MM,
        'VCM_modified': False, 'other_nets_modified': False,
        'proposed_restitution_validated': False,
        'lookaround_mm': lookaround_mm,
    }
    if (not isinstance(edges, list) or len(edges) != 2
            or not all(isinstance(p, list) and len(p) == 2 for p in edges)):
        return report
    gap = LineString([tuple(edges[0]), tuple(edges[1])])
    if gap.length < .00001:
        raise ValueError('Unexpected collapsed In2 gap')
    region = gap.buffer(lookaround_mm)
    pad_points: dict[str, list[Any]] = defaultdict(list)
    via_points: dict[str, list[Any]] = defaultdict(list)
    objects: list[dict[str, Any]] = []
    samples = [gap.interpolate(f, normalized=True) for f in (0, .25, .5, .75, 1)]
    power_keepout = power.buffer(KEEP_OUT_MM)
    report['gap_length_mm'] = round(gap.length, 8)
    report['gap_power_keepout_overlap_mm'] = round(
        gap.intersection(power_keepout).length, 8)
    report['gap_power_keepout_intersects'] = power_keepout.intersects(gap)
    report['gap_sample_centre_covered_by_power'] = [
        power_keepout.covers(p) for p in samples
    ]
    report['nearest_L3_outline_mm'] = round(gap.distance(power), 8)
    report['gap_midpoint_mm'] = [
        round(gap.interpolate(.5, normalized=True).x, 6),
        round(gap.interpolate(.5, normalized=True).y, 6),
    ]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad_points[pad.GetNetname()].append(Point(xy(pad.GetPosition())))
    tracks = list(board.GetTracks())
    for t in tracks:
        if isinstance(t, pcbnew.PCB_VIA):
            via_points[t.GetNetname()].append(Point(xy(t.GetPosition())))
    for t in tracks:
        net = t.GetNetname()
        if net == ch022_net:
            continue
        is_via = isinstance(t, pcbnew.PCB_VIA)
        if is_via:
            kind, layer = 'via', 'THROUGH'
            center = Point(xy(t.GetPosition()))
            geom = center.buffer(pcbnew.ToMM(t.GetWidth()) / 2)
            coords = [list(xy(t.GetPosition()))]
        elif t.GetLayer() == pcbnew.In2_Cu:
            kind, layer = ('arc' if isinstance(t, pcbnew.PCB_ARC)
                           else 'track'), 'In2.Cu'
            if kind == 'arc':
                bounds = t.GetBoundingBox()
                geom = box(pcbnew.ToMM(bounds.GetX()),
                           pcbnew.ToMM(bounds.GetY()),
                           pcbnew.ToMM(bounds.GetRight()),
                           pcbnew.ToMM(bounds.GetBottom()))
            else:
                geom = LineString([xy(t.GetStart()), xy(t.GetEnd())])
                geom = geom.buffer(pcbnew.ToMM(t.GetWidth()) / 2)
            coords = [list(xy(t.GetStart())), list(xy(t.GetEnd()))]
        else:
            continue
        if not geom.intersects(region):
            continue
        clear = .20 if net.upper().startswith(POWER_HINTS) else .15
        inflation = clear + .075
        barrier = geom.buffer(inflation)
        nearest_pad = min(
            (geom.distance(p) for p in pad_points[net]), default=1e6)
        nearest_via = min(
            (geom.distance(p) for p in via_points[net]), default=1e6)
        classification = movement_class(net, kind, layer, nearest_pad,
                                        nearest_via)
        item = {
            'uuid': t.m_Uuid.AsString(),
            'net': net, 'kind': kind, 'layer': layer,
            'coords_mm': coords, 'width_mm': round(pcbnew.ToMM(t.GetWidth()), 6),
            'distance_copper_to_gap_mm': round(geom.distance(gap), 8),
            'distance_inflated_to_gap_mm': round(barrier.distance(gap), 8),
            'inflated_barrier_intersects_gap': barrier.intersects(gap),
            'nearest_same_net_pad_mm': round(nearest_pad, 8),
            'nearest_same_net_via_mm': round(nearest_via, 8),
            'classification': classification,
        }
        objects.append(item)
    # Capture In2 pads and their UUIDs, including plated through-hole pads.
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not p.IsOnLayer(pcbnew.In2_Cu):
                continue
            bounds = p.GetBoundingBox()
            copper = box(pcbnew.ToMM(bounds.GetX()),
                         pcbnew.ToMM(bounds.GetY()),
                         pcbnew.ToMM(bounds.GetRight()),
                         pcbnew.ToMM(bounds.GetBottom()))
            if not copper.intersects(region):
                continue
            objects.append({
                'uuid': p.m_Uuid.AsString(),
                'net': p.GetNetname(), 'kind': 'pad', 'layer': 'In2.Cu',
                'footprint': fp.GetReference(), 'pad_number': p.GetNumber(),
                'distance_copper_to_gap_mm': round(copper.distance(gap), 8),
                'distance_inflated_to_gap_mm': round(
                    copper.buffer(.225).distance(gap), 8),
                'inflated_barrier_intersects_gap': copper.buffer(.225).intersects(gap),
                'classification': 'IMMUTABLE',
            })
    # Zone UUID and net are as important as track UUID; only complete zone
    # outlines are considered forbidden for In2 copper and new through vias.
    for z in board.Zones():
        if not z.IsOnLayer(pcbnew.In2_Cu):
            continue
        polylines = z.Outline()
        outlines = []
        for idx in range(polylines.OutlineCount()):
            line = polylines.Outline(idx)
            if line.PointCount() < 3:
                continue
            shape = Polygon([xy(line.CPoint(j)) for j in range(line.PointCount())])
            if not shape.is_valid:
                shape = shape.buffer(0)
            if not shape.is_empty:
                outlines.append(shape)
        if not outlines:
            continue
        zone_geom = unary_union(outlines)
        if not zone_geom.buffer(KEEP_OUT_MM).intersects(region):
            continue
        objects.append({
            'uuid': z.m_Uuid.AsString(), 'net': z.GetNetname(),
            'kind': 'zone_outline', 'layer': 'In2.Cu',
            'distance_copper_to_gap_mm': round(zone_geom.distance(gap), 8),
            'distance_inflated_to_gap_mm': round(
                zone_geom.buffer(KEEP_OUT_MM).distance(gap), 8),
            'inflated_barrier_intersects_gap': zone_geom.buffer(
                KEEP_OUT_MM).intersects(gap),
            'classification': 'IMMUTABLE',
        })
    objects.sort(key=lambda obj: (
        not obj['inflated_barrier_intersects_gap'],
        obj['distance_inflated_to_gap_mm'],
        obj['distance_copper_to_gap_mm'],
        obj['kind'], obj['net'], obj['uuid']))
    report['objects_in_1p25mm_neighbourhood'] = objects
    report['object_count'] = len(objects)
    report['gap_intersecting_barrier_count'] = sum(
        x['inflated_barrier_intersects_gap'] for x in objects)
    report['candidate_requiring_restitution_uuids'] = [
        x['uuid'] for x in objects
        if x['classification'] == 'CANDIDATE_REQUIRES_FULL_NATIVE_RESTITUTION'
        and x['inflated_barrier_intersects_gap']
    ]
    report['protected_barrier_uuids'] = [
        x['uuid'] for x in objects
        if x['classification'] == 'IMMUTABLE'
        and x['inflated_barrier_intersects_gap']
    ]
    report['status'] = 'UUID_inventory_only_no_mutation'
    return report

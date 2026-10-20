#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact-blocker inventory for a failed protected CH022 B.Cu mesh route.

Pure read-only KiCad/Shapely analysis on an in-memory candidate.
No released PCB, manufacturing outputs, or external copper mutations.
"""
from __future__ import annotations

from typing import Any


def inspect(board: Any, rvia: tuple[float, float],
            jvia: tuple[float, float], code: int,
            power: Any, region: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from shapely.ops import unary_union
    from route_targeted_closure import xy, obstacles
    from escape_mesh_505 import polygons

    line = LineString([rvia, jvia])
    layers = (pcbnew.B_Cu, pcbnew.In2_Cu)
    front_blockers, _ = obstacles(
        board, code, .15, .15, region, .60, (pcbnew.F_Cu, pcbnew.B_Cu))
    layer_shapes, via_obstacle = obstacles(
        board, code, .15, .15, region, .60, layers)
    out: dict[str, Any] = {
        'endpoints': {'R302_via': list(rvia), 'J2_via': list(jvia)},
        'direct_length_mm': round(line.length, 6),
        'protected_power_buffer_mm': .505,
        'blocked_layer_summary': {},
        'nearby_foreign_tracks': [],
        'nearby_foreign_pads': [],
        'via_area_mm2_in_corridor': 0.,
    }
    for layer_name, geom, protected in (
            ('F.Cu', front_blockers[0], False),
            ('B.Cu', layer_shapes[0], False),
            ('In2.Cu', layer_shapes[1], True)):
        forbidden = unary_union([geom, power.buffer(.505)]) if protected else geom
        free = region.difference(forbidden).buffer(-.000005)
        comps = polygons(free)
        ids = [next((i for i, p in enumerate(comps)
                     if p.distance(Point(x)) < .00001), None)
               for x in (rvia, jvia)]
        comp_gap = (comps[ids[0]].distance(comps[ids[1]])
                    if ids[0] is not None and ids[1] is not None else None)
        out['blocked_layer_summary'][layer_name] = {
            'R302_endpoint_legal': ids[0] is not None,
            'J2_endpoint_legal': ids[1] is not None,
            'same_component': ids[0] is not None and ids[0] == ids[1],
            'separated_component_gap_mm': round(comp_gap, 6)
            if comp_gap is not None else None,
            'direct_line_free': bool(free.covers(line)),
            'near_direct_free_area_mm2': round(
                free.intersection(line.buffer(2.5)).area, 6),
            'area_R302_component_mm2': round(comps[ids[0]].area, 6)
            if ids[0] is not None else None,
            'area_J2_component_mm2': round(comps[ids[1]].area, 6)
            if ids[1] is not None else None,
        }
    legal_new_via = region.difference(
        unary_union([via_obstacle, power.buffer(.505)])).buffer(-.000005)
    out['via_area_mm2_in_corridor'] = round(
        legal_new_via.intersection(line.buffer(2.5)).area, 6)

    # An uninterrupted board-width AGND B.Cu trace at y=11.0
    # separates the two retained CH022 via endpoints. Identify
    # legal candidate through-via windows on both sides, but never
    # treat a geometric window as native-DCR qualification.
    bands = {
        'before_AGND_y11': box(34, 11.6, 49, 20),
        'after_AGND_y11': box(34, 6.5, 49, 10.4),
    }
    out['new_via_bands'] = {}
    for name, band in bands.items():
        sites = legal_new_via.intersection(band).intersection(line.buffer(5.0))
        parts = [p for p in polygons(sites) if p.area > 1e-7]
        parts.sort(key=lambda p: (p.distance(line), -p.area))
        out['new_via_bands'][name] = {
            'legal_area_mm2': round(sites.area, 7),
            'sample_sites': [{
                'xy': [round(q, 6) for q in p.representative_point().coords[0]],
                'area_mm2': round(p.area, 7),
            } for p in parts[:8]],
        }

    corridor = line.buffer(3.0).union(
        Point(rvia).buffer(2.5)).union(Point(jvia).buffer(2.5))
    def distance_item(shape: Any) -> float:
        return round(shape.distance(line), 6)
    for t in board.GetTracks():
        if t.GetNetCode() == code:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            layers_used = ['B.Cu', 'In2.Cu']
            shape = Point(xy(t.GetPosition()))
            kind = 'via'
        elif isinstance(t, pcbnew.PCB_ARC):
            continue
        elif t.GetLayer() in layers:
            layers_used = [board.GetLayerName(t.GetLayer())]
            shape = LineString([xy(t.GetStart()), xy(t.GetEnd())])
            kind = 'track'
        else:
            continue
        if not shape.intersects(corridor):
            continue
        out['nearby_foreign_tracks'].append({
            'uuid': t.m_Uuid.AsString(),
            'net': t.GetNetname(),
            'layer': layers_used,
            'kind': kind,
            'width_mm': round(pcbnew.ToMM(t.GetWidth()), 4),
            'distance_to_straight_ch022_mm': distance_item(shape),
            'from': list(xy(t.GetStart())),
            'to': list(xy(t.GetEnd())),
        })
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == code or not any(
                    pad.IsOnLayer(layer) for layer in layers):
                continue
            p=Point(xy(pad.GetPosition()))
            if p.distance(line) <= 2.5:
                out['nearby_foreign_pads'].append({
                    'pad': fp.GetReference()+'.'+pad.GetNumber(),
                    'net': pad.GetNetname(),
                    'center': list(xy(pad.GetPosition())),
                    'distance_mm': distance_item(p),
                    'on_BCu': bool(pad.IsOnLayer(pcbnew.B_Cu)),
                    'on_In2': bool(pad.IsOnLayer(pcbnew.In2_Cu)),
                })
    out['nearby_foreign_tracks'].sort(
        key=lambda x:(x['distance_to_straight_ch022_mm'],x['net'],x['uuid']))
    out['nearby_foreign_pads'].sort(
        key=lambda x:(x['distance_mm'],x['pad']))
    out['nearby_foreign_tracks'] = out['nearby_foreign_tracks'][:120]
    out['nearby_foreign_pads'] = out['nearby_foreign_pads'][:50]
    return out

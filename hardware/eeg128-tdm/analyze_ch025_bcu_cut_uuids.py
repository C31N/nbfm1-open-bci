#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""UUID-precise, strictly read-only inventory of CH025 B.Cu free-space cut."""
from __future__ import annotations

from typing import Any

PROTECTED = ('VCM', 'AGND', 'CH017_N', 'CH019_P', 'CH021_P',
             'CH010_N', 'CH024_P',
             'CH026_P', '3V3', 'VCC', 'VDD', 'VREG', 'GND')


def distance_gap(source: Any, target: Any) -> dict[str, Any]:
    from shapely.ops import nearest_points
    a, b = nearest_points(source, target)
    return {'gap_mm': round(source.distance(target), 9),
            'source_edge_mm': [round(a.x, 6), round(a.y, 6)],
            'target_edge_mm': [round(b.x, 6), round(b.y, 6)]}


def survey(board: Any, source: Any, target: Any,
           *, target_net: str = 'CH025_N_MUX') -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from route_targeted_closure import xy

    gap = distance_gap(source, target)
    line = LineString([gap['source_edge_mm'], gap['target_edge_mm']])
    vicinity = line.buffer(1.0)
    result: dict[str, Any] = {
        'read_only': True, 'accepted': False,
        'routing_completed': False, 'fabrication_release': False,
        'BCu_gap': gap, 'survey_target_net': target_net,
        'not_a_topological_minimum_cut_proof': True,
        'protected_uuids': [],
        'movable_candidate_uuids': [], 'nearby_objects': [],
    }
    for item in board.GetTracks():
        if item.GetNetname() == target_net:
            continue
        is_via = isinstance(item, pcbnew.PCB_VIA)
        if not is_via and item.GetLayer() != pcbnew.B_Cu:
            continue
        if is_via:
            shape = Point(xy(item.GetPosition())).buffer(
                pcbnew.ToMM(item.GetWidth()) / 2)
        elif isinstance(item, pcbnew.PCB_ARC):
            b = item.GetBoundingBox()
            shape = box(pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
                        pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))
        else:
            shape = LineString([xy(item.GetStart()),
                                xy(item.GetEnd())]).buffer(
                pcbnew.ToMM(item.GetWidth()) / 2)
        if not shape.intersects(vicinity):
            continue
        name = item.GetNetname()
        kind = ('via' if is_via else
                'arc' if isinstance(item, pcbnew.PCB_ARC) else 'track')
        result['nearby_objects'].append({
            'uuid': item.m_Uuid.AsString(), 'net': name,
            'kind': kind, 'layer': 'THROUGH' if is_via else 'B.Cu',
            'distance_to_cut_mm': round(shape.distance(line), 8),
            'immutable': kind != 'track' or name.startswith(PROTECTED),
        })
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() == target_net or not pad.IsOnLayer(pcbnew.B_Cu):
                continue
            b = pad.GetBoundingBox()
            shape = box(pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
                        pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))
            if shape.intersects(vicinity):
                result['nearby_objects'].append({
                    'uuid': pad.m_Uuid.AsString(), 'net': pad.GetNetname(),
                    'kind': 'pad', 'layer': 'B.Cu',
                    'footprint': footprint.GetReference(),
                    'distance_to_cut_mm': round(shape.distance(line), 8),
                    'immutable': True,
                })
    result['nearby_objects'].sort(key=lambda o: (
        o['distance_to_cut_mm'], o['kind'], o['uuid']))
    result['nearby_objects'] = result['nearby_objects'][:100]
    result['protected_uuids'] = [o['uuid'] for o in result['nearby_objects']
                                 if o['immutable']]
    result['movable_candidate_uuids'] = [
        o['uuid'] for o in result['nearby_objects'] if not o['immutable']]
    return result

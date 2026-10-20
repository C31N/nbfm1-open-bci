#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only B.Cu obstacle inventory for the *actual seeded* CH022 via route.

Only diagnose the temporary native KiCad trial after CH026 early restitution,
CH024 three-pad proposal, and CH019 existing-via proposal. No PCB writes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

PROTECTED = frozenset({
    'CH022_N_ELECTRODE', 'CH026_P_ELECTRODE', 'CH026_P_MUX',
    'CH024_P_MUX', 'CH019_P_MUX', 'CH018_N_MUX', 'VCM',
})
FLAGS = {'model_only': True, 'accepted': False,
         'routing_completed': False, 'fabrication_release': False,
         'independent_replay_verified': False, 'native_qualification': False,
         'manufacturing_exports': False}


def survey(board: Any, a: tuple[float, float], b: tuple[float, float],
           corridor_width: float = 1.2) -> dict[str, Any]:
    """Catalog exact obstructing B.Cu objects without modifying copper."""
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import xy

    direct = LineString([a, b])
    pad_points: dict[str, list[Any]] = defaultdict(list)
    via_points: dict[str, list[Any]] = defaultdict(list)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pad_points[pad.GetNetname()].append(Point(xy(pad.GetPosition())))
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            via_points[track.GetNetname()].append(Point(xy(track.GetPosition())))

    obstacles: list[dict[str, Any]] = []
    for track in board.GetTracks():
        if track.GetNetname() == 'CH022_N_ELECTRODE':
            continue
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition()))
            kind = 'via'
        elif isinstance(track, pcbnew.PCB_ARC):
            continue
        elif track.GetLayer() == pcbnew.B_Cu:
            shape = LineString([xy(track.GetStart()), xy(track.GetEnd())])
            kind = 'segment'
        else:
            continue
        distance = shape.distance(direct)
        if distance > corridor_width:
            continue
        net = track.GetNetname()
        closest_pad = min((shape.distance(p) for p in pad_points[net]), default=1e6)
        closest_via = min((shape.distance(v) for v in via_points[net]), default=1e6)
        locked = (net in PROTECTED or kind != 'segment' or
                  closest_pad < 1.0 or closest_via < 0.65)
        obstacles.append({
            'net': net,
            'uuid': track.m_Uuid.AsString(),
            'layer': ('THROUGH' if kind == 'via' else 'B.Cu'),
            'kind': kind,
            'start_mm': list(xy(track.GetStart())),
            'end_mm': list(xy(track.GetEnd())),
            'track_width_mm': pcbnew.ToMM(track.GetWidth()),
            'distance_to_direct_mm': round(distance, 8),
            'nearest_pad_mm': round(closest_pad, 8),
            'nearest_via_mm': round(closest_via, 8),
            'locally_movable': not locked,
        })
    obstacles.sort(key=lambda t: (not t['locally_movable'], t['distance_to_direct_mm'],
                                  t['net'], t['uuid']))
    return {
        **FLAGS,
        'CH022_vias_mm': [list(a), list(b)],
        'inventory_corridor_half_width_mm': corridor_width,
        'movable_count': sum(t['locally_movable'] for t in obstacles),
        'protected_count': sum(not t['locally_movable'] for t in obstacles),
        'all_nearby_bcu_objects': obstacles,
        'safety': 'All protected nets, through-vias and pad/via escapes stay unchanged',
    }

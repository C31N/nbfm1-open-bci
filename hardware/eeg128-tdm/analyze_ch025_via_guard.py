#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only, UUID-precise CH025_N via-guarded F.Cu interior survey.

Never removes copper, changes pad or via anchors, writes a PCB, or promotes
an unqualified routing candidate.
"""
from __future__ import annotations

from typing import Any

PINNED = '156ba77d-5f3e-4c18-88ee-0f2763e31dfd'
NET = 'CH025_N_ELECTRODE'
FLAGS = {
    'model_only': True, 'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'native_qualification': False,
    'independent_replay_verified': False, 'manufacturing_files': False,
}


def free_intervals(start: tuple[float, float], end: tuple[float, float],
                   vias: list[tuple[float, float]],
                   pads: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Potential mathematical interior cuts with untouched original contacts."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    line = LineString([start, end])
    if line.length < .000001:
        raise ValueError('Degenerate pinned CH025_N segment')
    protected = [Point(x).buffer(.65) for x in vias]
    protected.extend(Point(x).buffer(1.0) for x in pads)
    protected.extend((Point(start).buffer(.15), Point(end).buffer(.15)))
    remaining = line.difference(unary_union(protected))
    pieces = ([remaining] if remaining.geom_type == 'LineString'
              else [g for g in getattr(remaining, 'geoms', ())
                    if g.geom_type == 'LineString'])
    windows = []
    for piece in pieces:
        if piece.length < .05:
            continue
        a, b = piece.coords[0], piece.coords[-1]
        if (any(piece.distance(Point(v)) < .65 - .000001 for v in vias)
                or any(piece.distance(Point(p)) < 1.0 - .000001
                       for p in pads)):
            raise RuntimeError('Protected CH025_N anchor overlap')
        windows.append({
            'start_mm': [round(a[0], 6), round(a[1], 6)],
            'end_mm': [round(b[0], 6), round(b[1], 6)],
            'length_mm': round(piece.length, 6),
        })
    return windows


def survey(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import xy

    t = next((t for t in board.GetTracks()
              if t.m_Uuid.AsString() == PINNED), None)
    if (t is None or t.GetNetname() != NET
            or t.GetLayer() != pcbnew.F_Cu
            or isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
        raise ValueError('Exact CH025_N target identity changed')
    start, end = xy(t.GetStart()), xy(t.GetEnd())
    line = LineString([start, end])
    vias = [(v.m_Uuid.AsString(), xy(v.GetPosition()))
            for v in board.GetTracks()
            if isinstance(v, pcbnew.PCB_VIA)
            and v.GetNetname() == NET]
    pads = [(fp.GetReference() + '.' + p.GetNumber(), xy(p.GetPosition()))
            for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == NET]
    windows = free_intervals(start, end,
                             [p for _, p in vias], [p for _, p in pads])
    return {
        **FLAGS,
        'status': ('interior_only_geometric_option_unqualified'
                   if windows else 'no_via_safe_interior_cut'),
        'segment_uuid': PINNED, 'net': NET, 'layer': 'F.Cu',
        'segment_start_mm': list(start), 'segment_end_mm': list(end),
        'segment_length_mm': round(line.length, 6),
        'via_anchors': [
            {'uuid': uid, 'position_mm': list(p),
             'distance_to_segment_mm': round(Point(p).distance(line), 6)}
            for uid, p in vias if Point(p).distance(line) <= .650001
        ],
        'pad_anchors': [
            {'pad': name, 'position_mm': list(p),
             'distance_to_segment_mm': round(Point(p).distance(line), 6)}
            for name, p in pads if Point(p).distance(line) <= 1.000001
        ],
        'interior_cut_windows': windows,
        'via_keepout_mm': .65,
        'pad_keepout_mm': 1.0,
        'endpoint_keepout_mm': .15,
        'full_segment_displacement_allowed': False,
        'copper_changed': False,
    }

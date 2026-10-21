#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Diagnostic native KiCad 8 zone-refill L3 area delta from pinned CH025 cut.

All operations are in memory. Reinsert the exact original trace and refill
again, with mandatory rollback proof. This removal-only study is NOT a
DRC/parity/replay qualification for a final simultaneous CH022/CH025 route.
"""
from __future__ import annotations

from typing import Any

TARGET_UUID = '748cc9c4-2d8f-4ec6-9714-133d79d4c7cb'
ZONE_UUID = '06a28b70-5141-41e4-bdb1-c8324bc06fcb'
FLAGS = {'accepted': False, 'routing_completed': False,
         'fabrication_release': False, 'manufacturing_files': False,
         'L3_final_qualified': False, 'independent_replay_verified': False}


def classify_delta(loss: float, gain: float) -> str:
    if loss < 0 or gain < 0:
        raise ValueError('Negative L3 power area delta')
    return ('removal_only_zero_delta'
            if loss == 0.0 and gain == 0.0 else 'removal_only_nonzero_delta')


def filled(zone: Any) -> Any:
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from route_targeted_closure import xy

    p = zone.GetFilledPolysList(pcbnew.In2_Cu)
    shapes = []
    for i in range(p.OutlineCount()):
        outer = p.Outline(i)
        if outer.PointCount() < 3:
            continue
        holes = []
        for j in range(p.HoleCount(i)):
            h = p.Hole(i, j)
            if h.PointCount() >= 3:
                holes.append([xy(h.CPoint(k)) for k in range(h.PointCount())])
        g = Polygon([xy(outer.CPoint(k))
                     for k in range(outer.PointCount())], holes)
        shapes.append(g if g.is_valid else g.buffer(0))
    return unary_union(shapes)


def audit(board: Any) -> dict[str, Any]:
    import pcbnew
    from route_targeted_closure import xy

    out: dict[str, Any] = {
        **FLAGS, 'status': 'native_refill_not_started',
        'power_zone_uuid': ZONE_UUID, 'removed_track_uuid': TARGET_UUID,
        'loss_mm2': None, 'gain_mm2': None,
        'loss_exact_zero': False, 'gain_exact_zero': False,
        'native_zone_fill_executed': False,
        'tracks_restored': False, 'native_zone_fill_restored': False,
        'removal_only_not_full_two_net_copper': True,
    }
    zones = [z for z in board.Zones()
             if z.m_Uuid.AsString() == ZONE_UUID
             and z.GetNetname() == '3V3A'
             and z.IsOnLayer(pcbnew.In2_Cu)]
    tracks = [t for t in board.GetTracks()
              if t.m_Uuid.AsString() == TARGET_UUID]
    if len(zones) != 1 or len(tracks) != 1:
        out['status'] = 'missing_exact_zone_or_trace'
        return out
    z, t = zones[0], tracks[0]
    if t.GetNetname() != 'CH025_N_MUX' or t.GetLayer() != pcbnew.In2_Cu:
        out['status'] = 'pinned_trace_mismatch'
        return out
    if sorted((xy(t.GetStart()), xy(t.GetEnd()))) != sorted(
            ((44.505, 25.129999), (44.505, 39.129999))):
        out['status'] = 'pinned_trace_endpoints_mismatch'
        return out

    def snapshot() -> dict[str, tuple[Any, ...]]:
        return {x.m_Uuid.AsString(): (
            x.GetNetCode(), x.GetLayer(), xy(x.GetStart()),
            xy(x.GetEnd()), x.GetWidth())
            for x in board.GetTracks()}

    before = snapshot()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    initial = filled(z)
    out['native_zone_fill_executed'] = True
    out['baseline_3V3A_mm2'] = initial.area
    board.Remove(t)
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        after_cut = filled(z)
        lost = initial.difference(after_cut).area
        gained = after_cut.difference(initial).area
        out['loss_mm2'] = lost
        out['gain_mm2'] = gained
        out['loss_exact_zero'] = lost == 0.0
        out['gain_exact_zero'] = gained == 0.0
        out['status'] = classify_delta(lost, gained)
    finally:
        board.Add(t)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        out['tracks_restored'] = snapshot() == before
        out['native_zone_fill_restored'] = filled(z).equals(initial)
        if not (out['tracks_restored'] and out['native_zone_fill_restored']):
            raise RuntimeError('CH025 native refill rollback failed')
    return out

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Strictly in-memory KiCad 8 trial of an In2.Cu 3V3A growth-mask keepout.

The polygon is generated from actual native filled copper recovered after
the pinned CH025 track is cut; no hand-calculated area or arbitrary box.
Any attempt is removed and the board is refilled before returning.
Never claim final dual-net DRC, replay or fabrication release.
"""
from __future__ import annotations

from typing import Any


def exact_gate(loss: float, gain: float, equal: bool) -> bool:
    return loss == 0.0 and gain == 0.0 and equal


def trial(board: Any, power_zone: Any, initial: Any,
          removed: Any, get_fill: Any) -> dict[str, Any]:
    import pcbnew
    from escape_mesh_505 import polygons

    growth = removed.difference(initial)
    pieces = [p for p in polygons(growth) if p.area > 1e-11]
    out: dict[str, Any] = {
        'accepted': False, 'routing_completed': False,
        'fabrication_release': False, 'manufacturing_files': False,
        'status': 'mask_not_created', 'mask_from_native_growth': True,
        'growth_mm2': growth.area, 'component_count': len(pieces),
        'loss_mm2': None, 'gain_mm2': None, 'exact_zero': False,
        'polygon_equal': False, 'mask_removed': False,
        'filled_copper_restored': False,
        'original_zone_UUIDs_restored': False,
    }
    if not pieces:
        return out
    shape = pcbnew.SHAPE_POLY_SET()
    count = 0
    for p in pieces:
        verts = list(p.exterior.coords)[:-1]
        count += len(verts) + sum(len(h.coords)-1 for h in p.interiors)
        if count > 7000:
            out['status'] = 'too_many_vertices'
            return out
        oi = shape.NewOutline()
        for x, y in verts:
            shape.Append(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y)), oi)
        for hole in p.interiors:
            hi = shape.NewHole(oi)
            for x, y in list(hole.coords)[:-1]:
                shape.Append(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y)), oi, hi)
    if count < 3:
        out['status'] = 'invalid_mask_polygon'
        return out
    out['mask_vertices'] = count
    original_zones = sorted(z.m_Uuid.AsString() for z in board.Zones())
    mask = pcbnew.ZONE(board)
    mask.SetIsRuleArea(True)
    mask.SetLayer(pcbnew.In2_Cu)
    mask.SetDoNotAllowCopperPour(True)
    mask.SetDoNotAllowTracks(False)
    mask.SetDoNotAllowVias(False)
    mask.SetDoNotAllowPads(False)
    mask.SetDoNotAllowFootprints(False)
    mask.SetOutline(shape)
    board.Add(mask)
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        filled = get_fill(power_zone)
        loss = initial.difference(filled).area
        gain = filled.difference(initial).area
        same = filled.equals(initial)
        out['loss_mm2'] = loss
        out['gain_mm2'] = gain
        out['polygon_equal'] = same
        out['exact_zero'] = exact_gate(loss, gain, same)
        out['status'] = ('temporary_exact_mask_meets_area_gate'
                         if out['exact_zero']
                         else 'temporary_mask_nonzero_area_delta')
    finally:
        board.Remove(mask)
        out['mask_removed'] = True
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        out['filled_copper_restored'] = get_fill(power_zone).equals(removed)
        out['original_zone_UUIDs_restored'] = (
            sorted(z.m_Uuid.AsString() for z in board.Zones()) == original_zones)
        if not (out['filled_copper_restored']
                and out['original_zone_UUIDs_restored']):
            raise RuntimeError('Native In2 keepout rollback mismatch')
    return out

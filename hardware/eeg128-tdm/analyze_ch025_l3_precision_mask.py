#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""KiCad 8.0.9 in-memory precision rule-area mask against native 3V3A gain.

Derive the gained L3 fill geometry from native SHAPE_POLY_SET BooleanSubtract.
Reject overlap with the reviewed 23-vertex CH022 route, then optionally
construct a *temporary* In2.Cu copper-pour-only rule area of the exact native
gain contours. After native refill, qualify both directional polygon diffs.
The candidate rule-area is removed in a finally clause; it is NEVER saved.
No release/checkpoint promotion or manufacturing outputs.
"""
from __future__ import annotations

from typing import Any

PROBE_28_CH022_LAYERS: tuple[tuple[int, float, float], ...] = (
    (0,38.686865,16.948734),(0,38.930489,14.838249),
    (0,38.940375,13.653926),(0,38.836808,12.973030),
    (0,38.919773,12.289178),(0,39.636331,12.334683),
    (0,40.107204,12.811843),(0,40.275408,28.259683),
    (0,40.580735,30.076493),(1,40.580735,30.076493),
    (1,42.929843,32.762393),(1,45.698784,31.783857),
    (1,46.023750,31.080574),(1,45.890003,30.385028),
    (0,45.890003,30.385028),(0,47.241724,29.970944),
    (1,47.241724,29.970944),(1,47.968099,27.594042),
    (1,51.764600,23.574938),(1,56.846847,6.440702),
    (0,56.846847,6.440702),(0,49.827106,9.810378),
    (0,44.026050,9.208768),
)
MM2_TO_NATIVE_IU2 = 1_000_000_000_000
FLAGS = {
    'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'manufacturing_files': False,
    'L3_power_gate_final_qualified': False,
    'independent_replay_verified': False,
    'mask_persisted_to_board': False,
}


def exact_native_difference(before: Any, after: Any) -> dict[str, Any]:
    """Return native integer-coordinate polygon differences both ways."""
    import pcbnew

    loss = pcbnew.SHAPE_POLY_SET(before)
    loss.BooleanSubtract(after, pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
    gain = pcbnew.SHAPE_POLY_SET(after)
    gain.BooleanSubtract(before, pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
    return {
        'loss_polyset': loss, 'gain_polyset': gain,
        'loss_native_outlines': loss.OutlineCount(),
        'gain_native_outlines': gain.OutlineCount(),
        'loss_native_mm2': loss.Area() / MM2_TO_NATIVE_IU2,
        'gain_native_mm2': gain.Area() / MM2_TO_NATIVE_IU2,
        'native_both_empty': (
            loss.OutlineCount() == 0 and gain.OutlineCount() == 0),
    }


def native_gain_compatibility(mask: Any, track_path: Any
                              = PROBE_28_CH022_LAYERS) -> dict[str, Any]:
    """No cover-up of CH022 In2 trace or its four through-via transitions."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    keepout_corridors = []
    via_centres = []
    for a, b in zip(track_path, track_path[1:]):
        if a[0] != b[0]:
            if a[1:] != b[1:]:
                raise ValueError('Invalid CH022 via position')
            via_centres.append(Point(a[1:]).buffer(.505))
        elif a[0] == 1:
            keepout_corridors.append(LineString([a[1:], b[1:]]).buffer(.075))
    combined = unary_union([*keepout_corridors, *via_centres])
    overlap = mask.intersection(combined).area
    return {
        'reviewed_CH022_waypoints': len(track_path),
        'reviewed_CH022_transitions': len(via_centres),
        'in2_trace_and_via_mask_overlap_mm2': overlap,
        'protects_reviewed_CH022_in2_corridor': overlap == 0.0,
    }


def try_keepout(board: Any, zone: Any, baseline: Any, cut: Any,
                baseline_shapely: Any, cut_shapely: Any) -> dict[str, Any]:
    import pcbnew

    diff = exact_native_difference(baseline, cut)
    gain = diff['gain_polyset']
    mask = cut_shapely.difference(baseline_shapely)
    route_check = native_gain_compatibility(mask)
    out: dict[str, Any] = {
        **FLAGS, 'status': 'no_keepout_candidate',
        'loss_native_outlines': diff['loss_native_outlines'],
        'gain_native_outlines': diff['gain_native_outlines'],
        'loss_native_mm2': diff['loss_native_mm2'],
        'gain_native_mm2': diff['gain_native_mm2'],
        'baseline_and_cut_native_equal': diff['native_both_empty'],
        'ideal_gain_mask_mm2': mask.area,
        'gain_mask_bounds_mm': list(mask.bounds),
        'ch022_corridor': route_check,
        'zone_uuid_3V3A': zone.m_Uuid.AsString(),
        'native_trial_performed': False,
        'trial_loss_mm2': None, 'trial_gain_mm2': None,
        'trial_native_both_empty': False,
        'new_keepout_removed': True,
        'original_power_refill_restored': False,
    }
    if diff['native_both_empty']:
        out['status'] = 'native_cut_already_zero_delta'
        out['original_power_refill_restored'] = True
        return out
    if not route_check['protects_reviewed_CH022_in2_corridor']:
        out['status'] = 'ideal_gain_mask_intersects_CH022_corridor'
        out['original_power_refill_restored'] = True
        return out
    if (diff['loss_native_outlines'] or not diff['gain_native_outlines']
            or diff['gain_native_outlines'] > 20
            or gain.VertexCount() > 1200):
        out['status'] = 'gain_mask_not_safe_for_exact_rule_area'
        out['original_power_refill_restored'] = True
        return out
    # SetOutline preserves native integer-coordinate contours and holes.
    # Keepout blocks COPPER POUR only, never tracks, vias, pads or footprints.
    rule = pcbnew.ZONE(board)
    rule.SetLayer(pcbnew.In2_Cu)
    rule.SetIsRuleArea(True)
    rule.SetDoNotAllowCopperPour(True)
    rule.SetDoNotAllowTracks(False)
    rule.SetDoNotAllowVias(False)
    rule.SetDoNotAllowPads(False)
    rule.SetDoNotAllowFootprints(False)
    rule.SetOutline(gain)
    out['native_trial_performed'] = True
    board.Add(rule)
    out['new_keepout_removed'] = False
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        candidate = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        post = exact_native_difference(baseline, candidate)
        out['trial_loss_mm2'] = post['loss_native_mm2']
        out['trial_gain_mm2'] = post['gain_native_mm2']
        out['trial_native_both_empty'] = post['native_both_empty']
        out['status'] = (
            'in_memory_exact_mask_candidate_still_native_unqualified'
            if post['native_both_empty'] else
            'in_memory_mask_fails_exact_native_L3_gate')
    finally:
        board.Remove(rule)
        out['new_keepout_removed'] = True
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        restored = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        out['original_power_refill_restored'] = (
            exact_native_difference(cut, restored)['native_both_empty'])
        if not out['original_power_refill_restored']:
            raise RuntimeError('Strict L3 rule-area rollback mismatch')
    return out

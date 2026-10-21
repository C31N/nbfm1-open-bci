#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""One UUID-pinned, reversible CH039_P_MUX B.Cu cut-opening experiment.

The 0.80001mm cut is bounded by protected VCM and a CH039 via as well as
the one candidate movable CH039 B.Cu trace. This temporary removal tests
whether moving that trace ALONE opens the CH025 B.Cu components. Never
modify VCM, pads, other nets, power planes or persist a candidate.
"""
from __future__ import annotations

from typing import Any

UUID = '31aaecea-198a-47c2-bcb6-c5ba10222375'
NET = 'CH039_P_MUX'
VCM_UUID = '04530298-f223-5100-ba26-ffbe00945865'


def classify(connected: bool) -> str:
    return ('ch039_trace_removal_opens_BCu_components_neighbour_restitution_required'
            if connected else 'ch039_trace_removal_does_not_open_VCM_BCu_cut')


def virtual_cut(board: Any, start: tuple[float, float],
                target: tuple[float, float], ch025_code: int,
                region: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from escape_mesh_505 import polygons
    from route_targeted_closure import obstacles, xy

    out: dict[str, Any] = {
        'accepted': False, 'routing_completed': False,
        'fabrication_release': False, 'read_only_result': True,
        'pinned_uuid': UUID, 'removed_only_in_memory': False,
        'candidate_restituted': False, 'BCu_connected_after_removal': False,
        'original_uuid_copper_restored': False,
        'protected_VCM_unchanged': False,
        'status': 'pinned_copper_not_found',
    }
    def snap() -> dict[str, tuple[Any, ...]]:
        return {t.m_Uuid.AsString(): (
            t.GetNetname(), t.GetLayer(), xy(t.GetStart()),
            xy(t.GetEnd()), t.GetWidth())
            for t in board.GetTracks()}

    matches = [t for t in board.GetTracks()
               if t.m_Uuid.AsString() == UUID]
    if len(matches) != 1:
        return out
    track = matches[0]
    if (track.GetNetname() != NET or track.GetLayer() != pcbnew.B_Cu
            or isinstance(track, (pcbnew.PCB_ARC, pcbnew.PCB_VIA))):
        out['status'] = 'pinned_track_type_layer_mismatch'
        return out
    before = snap()
    if VCM_UUID not in before:
        out['status'] = 'protected_VCM_not_found_fail_closed'
        return out
    board.Remove(track)
    out['removed_only_in_memory'] = True
    try:
        walls, _ = obstacles(board, ch025_code, .15, .15, region,
                             .60, (pcbnew.B_Cu, pcbnew.In2_Cu))
        free = region.difference(walls[0]).buffer(-.000005)
        points = [Point(start), Point(target)]
        ids = [next((i for i, p in enumerate(polygons(free))
                     if p.covers(point)), None) for point in points]
        out['BCu_component_ids_after_removal'] = ids
        connected = ids[0] is not None and ids[0] == ids[1]
        out['BCu_connected_after_removal'] = connected
        out['status'] = classify(connected)
    finally:
        board.Add(track)
        out['original_uuid_copper_restored'] = snap() == before
        out['protected_VCM_unchanged'] = (
            snap().get(VCM_UUID) == before[VCM_UUID])
        if not (out['original_uuid_copper_restored']
                and out['protected_VCM_unchanged']):
            raise RuntimeError('Virtual CH039 BCu copper rollback failed')
    return out

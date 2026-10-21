#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only CH025_N_MUX copper-connected existing-via anchor inventory.

After the pinned long trace is temporarily removed, find *only* existing
through vias connected to the original target by surviving same-net copper.
Never introduce a new via within the protected 3V3A zone outline.
Native DRC and L3-area parity remain compulsory for any proposed route.
"""
from __future__ import annotations

from typing import Any


def classify_anchor(contact: bool, existing_vias: int) -> str:
    if not contact:
        return 'CH025_target_has_no_surviving_same_net_contact'
    return ('CH025_target_has_existing_connected_via'
            if existing_vias else 'CH025_target_connected_but_no_existing_via')


def connected_existing_vias(
    board: Any, target: tuple[float, float], netcode: int,
    power: Any, max_candidates: int = 10,
) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import xy

    result: dict[str, Any] = {
        'status': 'no_candidates',
        'model_only': True, 'accepted': False,
        'routing_completed': False, 'fabrication_release': False,
        'native_qualification': False, 'manufacturing_files': False,
        'L3_loss_qualified': False, 'L3_gain_qualified': False,
        'source': list(target), 'via_candidates': [],
        'same_net_objects': 0, 'target_contact_uuids': [],
        'unknown_arc_count': 0, 'power_outline_immutable': True,
    }
    tracks = [t for t in board.GetTracks() if t.GetNetCode() == netcode]
    items: list[tuple[Any, Any, bool]] = []
    for t in tracks:
        is_via = isinstance(t, pcbnew.PCB_VIA)
        if isinstance(t, pcbnew.PCB_ARC):
            result['unknown_arc_count'] += 1
            continue
        shape = (Point(xy(t.GetPosition())).buffer(
            pcbnew.ToMM(t.GetWidth()) / 2)
            if is_via else LineString([
                xy(t.GetStart()), xy(t.GetEnd())]).buffer(
                    pcbnew.ToMM(t.GetWidth()) / 2))
        items.append((t, shape, is_via))
    result['same_net_objects'] = len(items)
    roots = [i for i, (_, geom, _) in enumerate(items)
             if geom.covers(Point(target))]
    result['target_contact_uuids'] = sorted(
        items[i][0].m_Uuid.AsString() for i in roots)
    visited = set(roots)
    frontier = list(roots)
    # Connected same-net copper on one layer, or a *through* via crossing it.
    # PCB pad contacts are not assumed to connect distant shapes.
    while frontier:
        idx = frontier.pop()
        ti, geom_i, via_i = items[idx]
        for j, (tj, geom_j, via_j) in enumerate(items):
            if j in visited:
                continue
            if not (via_i or via_j or ti.GetLayer() == tj.GetLayer()):
                continue
            if not geom_i.intersects(geom_j):
                continue
            visited.add(j)
            frontier.append(j)
    candidates: list[dict[str, Any]] = []
    for i in sorted(visited):
        t, _, is_via = items[i]
        if not is_via or t.GetViaType() != pcbnew.VIATYPE_THROUGH:
            continue
        point = xy(t.GetPosition())
        candidates.append({
            'uuid': t.m_Uuid.AsString(),
            'coordinate_mm': list(point),
            'distance_to_legacy_target_mm': round(
                Point(point).distance(Point(target)), 7),
            'inside_power_zone_outline': power.covers(Point(point)),
            'uses_existing_via_no_new_power_antipad': True,
            'net': t.GetNetname(), 'layer_type': 'THROUGH',
            'via_diameter_mm': pcbnew.ToMM(t.GetWidth()),
        })
    candidates.sort(key=lambda c: (
        c['distance_to_legacy_target_mm'], c['uuid']))
    result['via_candidates'] = candidates[:max_candidates]
    result['connected_existing_via_total'] = len(candidates)
    result['status'] = classify_anchor(bool(roots), len(candidates))
    return result

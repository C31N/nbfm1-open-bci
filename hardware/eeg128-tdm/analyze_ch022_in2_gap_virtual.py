#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""In-memory CH025_N_MUX In2 gap test. Always restore; never release."""
from __future__ import annotations

from typing import Any

PIN = '748cc9c4-2d8f-4ec6-9714-133d79d4c7cb'
EXPECTED = ((44.505, 25.129999), (44.505, 39.129999))
NET = 'CH025_N_MUX'
FLAGS = dict(model_only=True, accepted=False, routing_completed=False,
             fabrication_release=False, independent_replay_verified=False,
             native_qualification=False, manufacturing_files=False,
             CH025_N_MUX_restitution_qualified=False,
             L3_loss_qualified=False, L3_gain_qualified=False)


def pinned_ok(uid: str, net: str, layer: str,
              endpoints: tuple[tuple[float, float], tuple[float, float]],
              width: float) -> bool:
    return (uid == PIN and net == NET and layer == 'In2.Cu'
            and abs(width - .15) <= .000001
            and all(abs(x - y) < .00005
                    for p, q in zip(endpoints, EXPECTED)
                    for x, y in zip(p, q)))


def evaluate(board: Any, source: tuple[float, float],
             target: tuple[float, float], code: int, power: Any,
             region: Any, inventory: dict[str, Any]) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles, xy
    from analyze_ch022_multihop_graph import transition_graph
    from probe_ch022_ch025_dual_route import candidate as dual_route_candidate

    result: dict[str, Any] = {
        **FLAGS, 'status': 'not_run', 'pinned_uuid': PIN,
        'protected_FCu_tracks_modified': False,
        'existing_vias_modified': False,
        'original_segment_restored': False,
        'all_track_geometries_restored': False,
        'virtual_component_bridge_is_not_native_routing': True,
    }
    matches = [t for t in board.GetTracks()
               if t.m_Uuid.AsString() == PIN]
    if len(matches) != 1:
        result['status'] = 'pinned_track_count_changed'
        return result
    t = matches[0]
    if isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)) or not pinned_ok(
        t.m_Uuid.AsString(), t.GetNetname(),
        board.GetLayerName(t.GetLayer()),
        (xy(t.GetStart()), xy(t.GetEnd())),
        pcbnew.ToMM(t.GetWidth()),
    ):
        result['status'] = 'pinned_track_geometry_changed'
        return result
    if (inventory.get('candidate_requiring_restitution_uuids') != [PIN]
            or inventory.get('protected_barrier_uuids') != []
            or inventory.get('gap_power_keepout_intersects') is not False
            or abs(inventory.get('gap_length_mm', -1) - .60001) > .00001):
        result['status'] = 'gap_inventory_not_sole_movable_track'
        return result

    def snap() -> dict[str, tuple[Any, ...]]:
        return {
            x.m_Uuid.AsString(): (
                x.GetNetname(), x.GetLayer(), xy(x.GetStart()),
                xy(x.GetEnd()), x.GetWidth())
            for x in board.GetTracks()
        }

    before = snap()
    local = region.intersection(box(
        min(source[0], target[0]) - 24.,
        min(source[1], target[1]) - 24.,
        max(source[0], target[0]) + 24.,
        max(source[1], target[1]) + 24.))
    board.Remove(t)
    try:
        shapes, viaobs = obstacles(
            board, code, .15, .15, local, .60,
            (pcbnew.B_Cu, pcbnew.In2_Cu))
        reserved = power.buffer(.505)
        bcu = local.difference(shapes[0]).buffer(-.000005)
        in2 = local.difference(unary_union(
            [shapes[1], reserved])).buffer(-.000005)
        via = local.difference(unary_union(
            [viaobs, reserved])).buffer(-.000005)
        graph = transition_graph(bcu, in2, via, source, target)
        result['virtual_multihop_graph'] = graph
        result['CH022_virtual_component_connected'] = graph['multihop_connected']
        if graph['multihop_connected']:
            result['dual_routing_attempt'] = dual_route_candidate(
                board, source, target, code,
                xy(t.GetStart()), xy(t.GetEnd()), t.GetNetCode(),
                power, local)
            assert result['dual_routing_attempt']['retained_original_copper_verified']
        result['status'] = (
            'virtual_gap_connects_CH022_but_CH025_unrestored'
            if graph['multihop_connected']
            else 'virtual_gap_does_not_connect_CH022')
    finally:
        board.Add(t)
        result['original_segment_restored'] = True
        result['all_track_geometries_restored'] = snap() == before
        if not result['all_track_geometries_restored']:
            raise RuntimeError('Unsafe CH025_N_MUX rollback mismatch')
    return result

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Non-persistent two-net geometric restitution test on a KiCad working board.

The pinned CH025_N_MUX 14-mm In2 trace is already absent from the
temporary board at entry. Both routing orders are evaluated against
real foreign-net obstacles; all added copper is rolled back atomically.
Successful geometry is never treated as DRC, netlist parity, or release.
"""
from __future__ import annotations

from typing import Any

FLAGS = {
    'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'manufacturing_files': False,
    'native_drc_passed': False, 'schematic_parity_passed': False,
    'independent_replay_verified': False, 'L3_loss_qualified': False,
    'L3_gain_qualified': False, 'CH025_restitution_native_passed': False,
}
LAYERS_ALLOWED = ('B.Cu', 'In2.Cu')


def path_is_pinned(path: list[tuple[int, float, float]],
                   start: tuple[float, float], end: tuple[float, float],
                   target_layer: int) -> bool:
    if len(path) < 2 or path[0] != (target_layer, *start):
        return False
    if path[-1] != (target_layer, *end):
        return False
    if any(layer not in (0, 1) for layer, _, _ in path):
        return False
    if any(a[0] != b[0] and a[1:] != b[1:]
           for a, b in zip(path, path[1:])):
        return False
    return True


def candidate(board: Any, ch022_start: tuple[float, float],
              ch022_end: tuple[float, float], ch022_net: int,
              ch025_start: tuple[float, float],
              ch025_end: tuple[float, float], ch025_net: int,
              power: Any, region: Any) -> dict[str, Any]:
    import pcbnew
    from route_targeted_closure import xy
    from escape_mesh_505 import add_mesh_path, mesh_route

    # The 0.505-mm L3 keepout is enforced by mesh_route on each attempt.
    # Its via-obstacle model also includes foreign F.Cu tracks and all pads.
    routes = {
        'CH022_N_ELECTRODE': (
            ch022_start, ch022_end, ch022_net,
            (pcbnew.B_Cu, pcbnew.In2_Cu)),
        'CH025_N_MUX': (
            ch025_start, ch025_end, ch025_net,
            (pcbnew.In2_Cu, pcbnew.B_Cu)),
    }
    report: dict[str, Any] = {
        **FLAGS, 'status': 'no_complete_dual_geometry',
        'topological_component_path_is_not_native_connectivity': True,
        'allowed_routing_layers': list(LAYERS_ALLOWED),
        'L3_keepout_mm': .505,
        'A2_edge_clearance_mm': .25,
        'mutated_original_copper': False,
        'retained_original_copper_verified': False,
        'attempts': [],
    }

    def snapshot() -> dict[str, tuple[Any, ...]]:
        return {
            t.m_Uuid.AsString(): (
                t.GetNetCode(), t.GetLayer(), xy(t.GetStart()),
                xy(t.GetEnd()), t.GetWidth())
            for t in board.GetTracks()
        }

    baseline = snapshot()
    for order in (
        ('CH022_N_ELECTRODE', 'CH025_N_MUX'),
        ('CH025_N_MUX', 'CH022_N_ELECTRODE'),
    ):
        trial: dict[str, Any] = {
            'order': list(order), 'status': 'not_started',
            'new_copper_removed': False,
            'original_uuid_geometry_preserved': False,
            'paths': {},
        }
        report['attempts'].append(trial)
        try:
            for netname in order:
                start, end, netcode, layers = routes[netname]
                path = mesh_route(
                    board, start, end, netcode, layers,
                    power, region, start_layer=0, goal_layer=0)
                if path is None:
                    if netname == 'CH025_N_MUX':
                        from analyze_ch025_route_topology import assess
                        trial['ch025_anchor_cut_diagnostic'] = assess(
                            board, start, end, netcode, power, region)
                    trial['status'] = 'mesh_unreachable_'+netname
                    break
                if not path_is_pinned(path, start, end, 0):
                    trial['status'] = 'mesh_endpoint_or_layer_invalid_'+netname
                    break
                trial['paths'][netname] = {
                    'vertex_count': len(path),
                    'layer_changes': sum(
                        a[0] != b[0] for a, b in zip(path, path[1:])),
                    'layer_sequence': [LAYERS_ALLOWED[0] if layers[l] == pcbnew.B_Cu
                                       else LAYERS_ALLOWED[1] for l, _, _ in path],
                    'path_mm': [list(p) for p in path],
                }
                # Must be added before checking the other net so its copper
                # is a real obstacle. It is *always* removed in finally.
                add_mesh_path(board, path, netcode, layers)
            else:
                trial['status'] = 'both_geometry_paths_exist_native_unqualified'
                report['status'] = 'dual_geometry_found_restitution_not_qualified'
        finally:
            # SWIG object identity is unreliable. Compare exact native UUIDs.
            extra = [t for t in list(board.GetTracks())
                     if t.m_Uuid.AsString() not in baseline]
            if any(t.GetNetname() not in routes for t in extra):
                raise RuntimeError('Unapproved net modified in virtual test')
            for t in extra:
                board.Remove(t)
            trial['new_copper_removed'] = True
            trial['original_uuid_geometry_preserved'] = (
                snapshot() == baseline)
            if not trial['original_uuid_geometry_preserved']:
                raise RuntimeError('Dual-net trial changed protected original copper')
        if trial['status'] == 'both_geometry_paths_exist_native_unqualified':
            break
    report['retained_original_copper_verified'] = all(
        item['original_uuid_geometry_preserved']
        for item in report['attempts'])
    return report

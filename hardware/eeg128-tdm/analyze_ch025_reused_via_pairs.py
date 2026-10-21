#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Try *existing* CH025 B.Cu via pairs without adding any new through vias.

Every source/target via is first proven connected to its respective
surviving CH025_N_MUX copper branch by the read-only native-UUID
inventory. This deliberately avoids the original illegal In2.Cu target.
Do not interpret mesh output as DRC, netlist parity, or L3 acceptance.
"""
from __future__ import annotations

from typing import Any

FLAGS = {
    'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'manufacturing_files': False,
    'native_drc_passed': False, 'schematic_parity_passed': False,
    'independent_replay_verified': False,
    'L3_loss_qualified': False, 'L3_gain_qualified': False,
    'CH025_net_restituted_native': False, 'new_vias_allowed': False,
}


def pair_status(source_component: int | None,
                target_component: int | None) -> str:
    if source_component is None or target_component is None:
        return 'reused_via_outside_BCu_copper_corridor'
    if source_component != target_component:
        return 'reused_via_pair_separated_on_BCu'
    return 'BCu_component_connected_but_mesh_unqualified'


def expanded_region(region: Any, source: tuple[float, float],
                    target: tuple[float, float], copper_domain: Any,
                    margin_mm: float = 4.0) -> Any:
    """Cover both retained through-via anchors, clipped to legal A2 board domain.

    Earlier probes clipped the entire route to the CH022-local box, with
    y_max=40.949 mm; the CH025 targets at y=48.85/52.18 were excluded.
    This fixes a search-domain error, NOT a genuine copper clearance.
    """
    from shapely.geometry import Point, box

    if not 2.0 <= margin_mm <= 10.0:
        raise ValueError('Expanded B.Cu target margin out of range')
    envelope = box(min(source[0], target[0]) - margin_mm,
                   min(source[1], target[1]) - margin_mm,
                   max(source[0], target[0]) + margin_mm,
                   max(source[1], target[1]) + margin_mm)
    clipped = region.union(envelope).intersection(copper_domain)
    if not clipped.covers(Point(source)) or not clipped.covers(Point(target)):
        raise ValueError('Pinned existing CH025 via outside legal A2 domain')
    return clipped


def try_pair(board: Any, source_anchor: tuple[float, float],
             target_anchor: tuple[float, float], netcode: int,
             power: Any, region: Any, limit: int = 4,
             ) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from escape_mesh_505 import mesh_route, polygons
    from route_targeted_closure import obstacles, routing_domain
    from analyze_ch025_existing_via_anchor import connected_existing_vias

    source = connected_existing_vias(
        board, source_anchor, netcode, power, max_candidates=limit)
    target = connected_existing_vias(
        board, target_anchor, netcode, power, max_candidates=limit)
    result: dict[str, Any] = {
        **FLAGS, 'status': 'no_full_reused_via_BCu_geometry',
        'source_connected_vias': source, 'target_connected_vias': target,
        'L3_power_keepout_mm': .505, 'A2_edge_clearance_mm': .25,
        'allowed_copper_layers': ['B.Cu'],
        'no_original_tracks_modified': True,
        'candidates': [], 'best_path': None,
    }
    if (source['unknown_arc_count'] or target['unknown_arc_count']
            or not source['via_candidates'] or not target['via_candidates']):
        result['status'] = 'missing_or_unsupported_connected_via_anchors'
        return result

    # The first two probes mistakenly inherited CH022's short local
    # y-window. Measure both endpoints against the expanded *per-pair*
    # B.Cu search corridor; never bypass native clearance or board edges.
    domain = routing_domain(board, .075)

    for start in source['via_candidates']:
        for end in target['via_candidates']:
            sp = tuple(start['coordinate_mm'])
            tp = tuple(end['coordinate_mm'])
            row: dict[str, Any] = {
                'source_uuid': start['uuid'],
                'target_uuid': end['uuid'],
                'source_mm': list(sp), 'target_mm': list(tp),
                'source_existing_via': True, 'target_existing_via': True,
                'source_in_previous_local_window': region.covers(Point(sp)),
                'target_in_previous_local_window': region.covers(Point(tp)),
                'path_proposed': False,
            }
            result['candidates'].append(row)
            if not domain.covers(Point(sp)) or not domain.covers(Point(tp)):
                row['status'] = 'existing_via_outside_A2_domain'
                continue
            corridor = expanded_region(region, sp, tp, domain)
            shapes, _ = obstacles(
                board, netcode, .15, .15, corridor, .60,
                (pcbnew.B_Cu, pcbnew.In2_Cu))
            free = corridor.difference(shapes[0]).buffer(-.000005)
            parts = polygons(free)
            def component(p: tuple[float, float]) -> int | None:
                point = Point(p)
                return next((i for i, shape in enumerate(parts)
                             if shape.covers(point)), None)
            row['BCu_source_component'] = component(sp)
            row['BCu_target_component'] = component(tp)
            row['expanded_region_bounds_mm'] = list(corridor.bounds)
            row['expanded_region_contains_target'] = (
                corridor.covers(Point(tp)))
            row['BCu_target_distance_to_legal_free_mm'] = round(
                Point(tp).distance(free), 7)
            if start['uuid'] == end['uuid']:
                row['status'] = 'same_via_identity_no_new_route'
                continue
            row['status'] = pair_status(
                row['BCu_source_component'], row['BCu_target_component'])
            if row['status'] != 'BCu_component_connected_but_mesh_unqualified':
                continue
            # A new through-via would change the protected L3 power
            # antipad. B.Cu-only geometry uses retained same-net vias.
            raw = mesh_route(board, sp, tp, netcode,
                             (pcbnew.B_Cu, pcbnew.In2_Cu),
                             power, corridor, start_layer=0, goal_layer=0,
                             allow_vias=False)
            if raw is None or len(raw) < 2:
                row['status'] = 'BCu_mesh_failed_same_component'
                continue
            if (raw[0] != (0, *sp) or raw[-1] != (0, *tp)
                    or any(item[0] != 0 for item in raw)):
                row['status'] = 'BCu_path_invalid_or_changed_layer'
                continue
            row['status'] = 'BCu_reused_via_path_proposed_native_unqualified'
            row['path_proposed'] = True
            row['vertex_count'] = len(raw)
            result['best_path'] = {
                'source_uuid': start['uuid'], 'target_uuid': end['uuid'],
                'source_mm': list(sp), 'target_mm': list(tp),
                # Existing dual-router layer tuple is (In2.Cu, B.Cu).
                'dual_router_layer_index': 1,
                'path_mm': [[1, x, y] for _, x, y in raw],
            }
            result['status'] = 'BCu_path_found_no_new_via_unqualified'
            return result
    return result

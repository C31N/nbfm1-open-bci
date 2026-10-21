#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed CH025_N_MUX anchor-access and two-layer cut diagnosis.

Runs only on an already-temporary board with the pinned In2.Cu segment
removed. Every foreign copper object remains fixed. The In2.Cu anchors
are analysed as the start and goal layer; the alternate layer is B.Cu.
Native KiCad DRC is still required for any future geometry proposal.
"""
from __future__ import annotations

from typing import Any


def classify(source_available: bool, target_available: bool,
             connected: bool) -> str:
    if not source_available or not target_available:
        return 'CH025_In2_anchor_unavailable'
    return ('CH025_two_layer_topologically_reachable_mesh_unresolved'
            if connected else 'CH025_two_layer_geometric_cut')


def assess(board: Any, source: tuple[float, float],
           target: tuple[float, float], netcode: int,
           power: Any, region: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from escape_mesh_505 import polygons
    from route_targeted_closure import obstacles
    from analyze_ch022_multihop_graph import transition_graph

    obstacles_by_layer, via_obstacles = obstacles(
        board, netcode, .15, .15, region, .60,
        (pcbnew.B_Cu, pcbnew.In2_Cu))
    reserved = power.buffer(.505)
    # Same obstacle model as the failed KiCad mesh attempt. In2.Cu is
    # promoted to the graph's logical first layer because both CH025
    # anchor endpoints are physically on In2.Cu.
    bcu_free = region.difference(obstacles_by_layer[0]).buffer(-.000005)
    in2_free = region.difference(unary_union(
        [obstacles_by_layer[1], reserved])).buffer(-.000005)
    via_free = region.difference(unary_union(
        [via_obstacles, reserved])).buffer(-.000005)
    in2_shapes = polygons(in2_free)
    bcu_shapes = polygons(bcu_free)

    def anchor_data(p: tuple[float, float]) -> dict[str, Any]:
        point = Point(p)
        inside = [i for i, shape in enumerate(in2_shapes)
                  if shape.covers(point)]
        closest = min((shape.distance(point) for shape in in2_shapes),
                      default=float('inf'))
        return {
            'coordinate_mm': list(p),
            'In2_component': inside[0] if inside else None,
            'In2_anchor_legal': bool(inside),
            'In2_nearest_free_mm': (round(closest, 7)
                                  if closest != float('inf') else None),
            'within_power_keepout': reserved.covers(point),
            'power_outline_distance_mm': round(power.distance(point), 7),
            'via_at_anchor_legal': via_free.covers(point),
        }

    start_data = anchor_data(source)
    target_data = anchor_data(target)
    result: dict[str, Any] = {
        'model_only': True, 'accepted': False,
        'routing_completed': False, 'fabrication_release': False,
        'manufacturing_files': False, 'native_qualification': False,
        'L3_loss_qualified': False, 'L3_gain_qualified': False,
        'power_via_and_In2_keepout_mm': .505,
        'read_only': True,
        'source': start_data, 'target': target_data,
        'In2_component_count': len(in2_shapes),
        'BCu_component_count': len(bcu_shapes),
        'via_centre_legal_area_mm2': round(via_free.area, 7),
    }
    if not (start_data['In2_anchor_legal']
            and target_data['In2_anchor_legal']):
        result['status'] = classify(start_data['In2_anchor_legal'],
                                    target_data['In2_anchor_legal'], False)
        return result
    # transition_graph's argument names are BCu/In2, but its edges
    # are symmetrical. Swapping geometry makes its B nodes represent
    # physical In2.Cu and its I nodes represent physical B.Cu.
    graph = transition_graph(in2_free, bcu_free, via_free, source, target)
    graph['logical_first_layer'] = 'In2.Cu'
    graph['logical_second_layer'] = 'B.Cu'
    result['layer_swapped_graph'] = graph
    result['status'] = classify(True, True, graph['multihop_connected'])
    result['minimum_layer_transitions'] = graph['minimum_layer_transitions']
    result['source_reachable_BCu_components'] = (
        graph['source_reachable_In2_components'])
    result['target_reachable_BCu_components'] = (
        graph['target_reachable_In2_components'])
    result['cross_net_competition_relevant'] = (
        not graph['multihop_connected'])
    return result

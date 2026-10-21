#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed CH022_N B.Cu/In2.Cu bypass of AGND; no F.Cu modification.

This is only an ephemeral geometry candidate. Native KiCad 8.0.9 DRC,
netlist parity, identical power copper and byte-identical replay are mandatory
before any promotion. Never generate Gerber, NC drill, CPL, or BOM.
"""
from __future__ import annotations

from typing import Any

FLAGS = {
    'model_only': True,
    'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'native_qualification': False,
    'independent_replay_verified': False, 'manufacturing_files': False,
}
KEEP_OUT_MM = .505
EDGE_CLEARANCE_MM = .25
SEARCH_MARGIN_MM = 24.0


def _component_at(free: Any, point: tuple[float, float]) -> Any:
    from shapely.geometry import Point
    from escape_mesh_505 import polygons
    anchor = Point(point)
    return next((g for g in polygons(free) if g.covers(anchor)), None)


def _via_centres(window: Any, limit: int = 8) -> list[tuple[float, float]]:
    """Deterministic snapped centres strictly inside a legal via window."""
    from shapely.geometry import Point
    from escape_mesh_505 import polygons

    found = []
    for polygon in sorted(polygons(window),
                          key=lambda g: (-g.area, tuple(g.bounds))):
        if polygon.area <= 1e-8:
            continue
        x0, y0, x1, y1 = polygon.bounds
        raw = [polygon.representative_point(), polygon.centroid]
        raw += [Point(x0 + fx * (x1-x0), y0 + fy * (y1-y0))
                for fx in (.25, .5, .75) for fy in (.25, .5, .75)]
        for pos in raw:
            xy = (round(pos.x, 6), round(pos.y, 6))
            if polygon.contains(Point(xy)) and window.contains(Point(xy)):
                found.append(xy)
    return sorted(set(found))[:limit]


def propose(board: Any, source: tuple[float, float],
            target: tuple[float, float], code: int,
            layers: tuple[int, ...], power: Any, region: Any
            ) -> tuple[list[tuple[int, float, float]] | None, dict[str, Any]]:
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles, xy
    from escape_mesh_505 import mesh_route, polygons

    if layers != (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu):
        raise ValueError('Wrong KiCad 3-layer index order')
    if source[1] <= 11.0 or target[1] >= 11.0:
        raise ValueError('Pinned CH022 anchors no longer straddle AGND')
    local = region.intersection(box(
        min(source[0], target[0]) - SEARCH_MARGIN_MM,
        min(source[1], target[1]) - SEARCH_MARGIN_MM,
        max(source[0], target[0]) + SEARCH_MARGIN_MM,
        max(source[1], target[1]) + SEARCH_MARGIN_MM))
    existing = {xy(t.GetPosition()) for t in board.GetTracks()
                if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == code}
    report: dict[str, Any] = {
        **FLAGS, 'status': 'not_started',
        'source_mm': list(source), 'target_mm': list(target),
        'source_existing_CH022_via': source in existing,
        'target_existing_CH022_via': target in existing,
        'layers_only': ['B.Cu', 'In2.Cu'],
        'foreign_FCu_mutation': False,
        'power_outline_via_keepout_mm': KEEP_OUT_MM,
        'board_edge_clearance_mm': EDGE_CLEARANCE_MM,
        'L3_loss_qualified': False, 'L3_gain_qualified': False,
        'scope': 'Extended 24mm window; negative result is still local-only',
        'search_margin_mm': SEARCH_MARGIN_MM,
    }
    # No new source or target via: exact same-net retained vias only.
    if source not in existing or target not in existing:
        report['status'] = 'retained_anchor_via_missing'
        return None, report

    blocked, via_obstacle = obstacles(
        board, code, .15, .15, local, .60,
        (pcbnew.B_Cu, pcbnew.In2_Cu))
    reserved = power.buffer(KEEP_OUT_MM)
    bcufree = local.difference(blocked[0]).buffer(-.000005)
    in2free = local.difference(unary_union(
        [blocked[1], reserved])).buffer(-.000005)
    viafree = local.difference(unary_union(
        [via_obstacle, reserved])).buffer(-.000005)
    source_comp = _component_at(bcufree, source)
    target_comp = _component_at(bcufree, target)
    report['source_BCu_component_exists'] = source_comp is not None
    report['target_BCu_component_exists'] = target_comp is not None
    report['BCu_components_separated_by_AGND'] = (
        source_comp is not None and target_comp is not None
        and not source_comp.equals(target_comp))
    report['In2_free_area_mm2'] = round(in2free.area, 7)
    report['legal_via_area_mm2'] = round(viafree.area, 7)
    report['power_keepout_intersects_source_via'] = bool(
        reserved.covers(Point(source)))
    report['power_keepout_intersects_target_via'] = bool(
        reserved.covers(Point(target)))
    report['In2_components'] = len(polygons(in2free))
    if source_comp is None or target_comp is None:
        report['status'] = 'BCu_anchor_component_unavailable'
        return None, report

    candidates = []
    source_access, target_access = [], []
    for idx, part in enumerate(polygons(in2free)):
        # Through-via access needs simultaneous clearance on B.Cu, In2.Cu
        # and from the complete L3 power-zone outline; no F.Cu detour.
        upstream = (part.intersection(source_comp).intersection(viafree)
                    .buffer(-.000005))
        downstream = (part.intersection(target_comp).intersection(viafree)
                      .buffer(-.000005))
        sa, ta = upstream.area, downstream.area
        if sa > 1e-10:
            source_access.append({
                'component': idx, 'legal_transition_area_mm2': round(sa, 7),
                'via_centres_mm': [list(p) for p in _via_centres(upstream)],
            })
        if ta > 1e-10:
            target_access.append({
                'component': idx, 'legal_transition_area_mm2': round(ta, 7),
                'via_centres_mm': [list(p) for p in _via_centres(downstream)],
            })
        if sa <= 1e-10 or ta <= 1e-10:
            continue
        candidates.append({
            'component': idx,
            'upstream_transition_area_mm2': round(sa, 7),
            'downstream_transition_area_mm2': round(ta, 7),
            'upstream_samples_mm': [list(p) for p in _via_centres(upstream)],
            'downstream_samples_mm': [list(p) for p in _via_centres(downstream)],
        })
    report['source_accessible_In2_components'] = source_access
    report['target_accessible_In2_components'] = target_access
    report['source_accessible_In2_count'] = len(source_access)
    report['target_accessible_In2_count'] = len(target_access)
    report['joint_BCu_In2_transition_components'] = candidates
    report['reachable_via_component_count'] = len(candidates)
    # One common In2 island is sufficient, but not necessary: a legal chain
    # of BCu/In2Cu/BCu/In2Cu/BCu transitions can bridge separate islands.
    from analyze_ch022_multihop_graph import transition_graph
    component_graph = transition_graph(
        bcufree, in2free, viafree, source, target)
    report['multihop_component_graph'] = component_graph
    from analyze_ch022_in2_gap_blockers import inventory
    report['in2_gap_uuid_inventory'] = inventory(board, component_graph, power)
    if not component_graph['multihop_connected']:
        from analyze_ch022_in2_gap_virtual import evaluate as virtual_gap
        report['ch025_N_MUX_virtual'] = virtual_gap(
            board, source, target, code, power, region,
            report['in2_gap_uuid_inventory'])
    if not component_graph['multihop_connected']:
        report['status'] = 'no_BCu_In2_multihop_component_path'
        return None, report

    # Only run heavy KiCad-mesh routing after topology makes a route possible.
    # mesh_route's native obstacle model checks every new via against .505 mm
    # L3 exclusion and retains the exact existing CH022 source/target vias.
    raw = mesh_route(board, source, target, code,
                     (pcbnew.B_Cu, pcbnew.In2_Cu), power, local,
                     start_layer=0, goal_layer=0)
    if raw is None or len(raw) < 2:
        report['status'] = 'local_mesh_no_complete_bypass'
        return None, report
    path = [(1 if layer == 0 else 2, x, y) for layer, x, y in raw]
    if (path[0] != (1, *source) or path[-1] != (1, *target)
            or any(layer not in (1, 2) for layer, _, _ in path)
            or not any(layer == 2 for layer, _, _ in path)):
        report['status'] = 'route_not_a_BCu_In2_AGND_bypass'
        return None, report

    new_vias = []
    for a, b in zip(path, path[1:]):
        if a[0] == b[0]:
            check = bcufree if a[0] == 1 else in2free
            if not check.buffer(.000005).covers(LineString([a[1:], b[1:]])):
                raise RuntimeError('Route copper leaves legal layer corridor')
        else:
            if a[1:] != b[1:]:
                raise RuntimeError('Layer transition has unmatched coordinates')
            if a[1:] not in existing:
                pos = Point(a[1:])
                if not viafree.covers(pos):
                    raise RuntimeError('In2 via violates power outline keepout')
                new_vias.append(a[1:])
    report['new_via_centres_mm'] = [list(p) for p in sorted(set(new_vias))]
    report['path_vertices'] = len(path)
    report['In2_segment_count'] = sum(
        a[0] == b[0] == 2 for a, b in zip(path, path[1:]))
    report['status'] = 'BCu_In2_geometry_proposed_unqualified'
    return path, report

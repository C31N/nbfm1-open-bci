#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed AGND crossing proposal for CH022_N on an ephemeral native board.

Only propose a B.Cu -> F.Cu -> B.Cu two-via detour. Optional In2.Cu
routing is left to the existing 3-layer router, whose .505 mm power
exclusion stays mandatory. Never remove or modify foreign copper.
This is NOT a native DRC qualification, replay, or accepted checkpoint.
"""
from __future__ import annotations

from typing import Any

FLAGS = {
    'model_only': True, 'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'native_qualification': False,
    'independent_replay_verified': False, 'manufacturing_files': False,
}
AGND_Y = 11.0
UPSTREAM = (33.0, 11.6, 50.0, 21.0)
DOWNSTREAM = (33.0, 6.0, 50.0, 10.4)


def _samples(area: Any, direct: Any, anchor: tuple[float, float],
             limit: int) -> list[tuple[float, float]]:
    """Deterministic sites strictly inside every via-centre keepout."""
    from shapely.geometry import Point
    from escape_mesh_505 import polygons

    ranked: list[tuple[float, tuple[float, float]]] = []
    for patch in polygons(area):
        if patch.area < 0.00001:
            continue
        x0, y0, x1, y1 = patch.bounds
        candidates = [patch.representative_point(), patch.centroid]
        for fx in (.25, .5, .75):
            for fy in (.25, .5, .75):
                candidates.append(Point(x0 + (x1-x0)*fx, y0 + (y1-y0)*fy))
        for item in candidates:
            xy = (round(item.x, 6), round(item.y, 6))
            point = Point(xy)
            if not patch.contains(point) or not area.contains(point):
                continue
            score = point.distance(direct) + .30*point.distance(Point(anchor))
            ranked.append((score, xy))
    ranked.sort(key=lambda row: (row[0], row[1]))
    sites: list[tuple[float, float]] = []
    for _, xy in ranked:
        if all(Point(xy).distance(Point(other)) >= .35 for other in sites):
            sites.append(xy)
            if len(sites) >= limit:
                break
    return sites


def propose(board: Any, start: tuple[float, float],
            end: tuple[float, float], net: int,
            layers: tuple[int, ...], power: Any, region: Any,
            max_sites: int = 4) -> tuple[list[tuple[int, float, float]] | None,
                                          dict[str, Any]]:
    """Find a staged AGND bridge; return a proposal, never mutate the board.

    Both new vias require simultaneous F.Cu/B.Cu trace clearance, native
    board-edge radius and complete L3 power-outline + .505 mm exclusion.
    Only KiCad DRC/zone-fill/parity/replay can qualify a resulting PCB.
    """
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles
    from escape_mesh_505 import mesh_route

    if (layers != (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
            or not 1 <= max_sites <= 8):
        raise ValueError('Pinned F/B/In2 layer order and bounded search required')
    if not (start[1] > AGND_Y and end[1] < AGND_Y):
        raise ValueError('CH022 via anchors no longer straddle AGND y=11')
    direct = LineString([start, end])
    shapes, via_obstacle = obstacles(
        board, net, .15, .15, region, .60,
        (pcbnew.F_Cu, pcbnew.B_Cu))
    # 0.505 mm is measured from the full L3 power-zone OUTLINE,
    # including existing fill holes, not from the current filled copper.
    keepout = unary_union([
        via_obstacle, power.buffer(.505), shapes[0], shapes[1]])
    legal = region.difference(keepout).buffer(-.002)
    bands = {
        'before_AGND': legal.intersection(box(*UPSTREAM))
            .intersection(direct.buffer(6.0)),
        'after_AGND': legal.intersection(box(*DOWNSTREAM))
            .intersection(direct.buffer(6.0)),
    }
    report: dict[str, Any] = {
        **FLAGS,
        'algorithm': 'staged_BCu_FCu_BCu_two_via_crossing',
        'power_outline_keepout_mm': .505,
        'edge_clearance_mm': .25,
        'via_diameter_mm': .60,
        'AGND_y_mm': AGND_Y,
        'via_centres_before': [],
        'via_centres_after': [],
        'bands_legal_area_mm2': {
            name: round(g.area, 7) for name, g in bands.items()},
        'attempted_pairs': 0,
        'first_leg_usable': 0,
        'last_leg_usable': 0,
        'front_crossings_usable': 0,
        'proposal_only': True,
    }
    before = _samples(bands['before_AGND'], direct, start, max_sites)
    after = _samples(bands['after_AGND'], direct, end, max_sites)
    report['via_centres_before'] = [list(pt) for pt in before]
    report['via_centres_after'] = [list(pt) for pt in after]

    if not before or not after:
        report['status'] = 'no_paired_legal_via_centres'
        return None, report

    # Stage the three legs without any additional vias. This forces the
    # AGND crossing to F.Cu, not the board-spanning AGND B.Cu line.
    def leg(a: tuple[float, float], b: tuple[float, float],
            layer: int) -> list[tuple[int, float, float]] | None:
        result = mesh_route(
            board, a, b, net, layers, power, region,
            start_layer=layer, goal_layer=layer, allow_vias=False)
        return result if result and len(result) >= 2 else None

    initial = {pt: leg(start, pt, 1) for pt in before}
    final = {pt: leg(pt, end, 1) for pt in after}
    report['first_leg_usable'] = sum(path is not None for path in initial.values())
    report['last_leg_usable'] = sum(path is not None for path in final.values())
    report['status'] = 'staged_front_crossing_blocked'
    for a in before:
        if initial[a] is None:
            continue
        for b in after:
            if final[b] is None:
                continue
            report['attempted_pairs'] += 1
            crossing = leg(a, b, 0)
            if crossing is None:
                continue
            report['front_crossings_usable'] += 1
            combined = [
                *initial[a], (0, *a), *crossing[1:],
                (1, *b), *final[b][1:]]
            if (combined[0] != (1, *start)
                    or combined[-1] != (1, *end)):
                raise RuntimeError('Invalid B.Cu bridge endpoints')
            # A proposal must never enter In2.Cu or silently cross layers.
            if any(layer not in (0, 1) for layer, _, _ in combined):
                raise RuntimeError('Unexpected In2.Cu use in F.Cu AGND hop')
            if any(p[1:] != q[1:] for p, q in zip(combined, combined[1:])
                   if p[0] != q[0]):
                raise RuntimeError('Layer transition without coincident via')
            report['status'] = 'staged_bridge_geometry_proposed_unqualified'
            report['chosen_centres'] = [list(a), list(b)]
            report['route_vertices'] = len(combined)
            return combined, report
    return None, report

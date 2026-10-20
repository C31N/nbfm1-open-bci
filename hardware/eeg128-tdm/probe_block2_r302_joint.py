#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Cross-layer CH019-P/CH024-P experiments, preserving VCM and CH018-N copper.

All modifications are in a SHA-pinned ephemeral KiCad board. Native DRC on
fully proposed candidates is informational and never constitutes acceptance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive, digest, ZIP_SHA
from probe_ch019_trunk_return import (FLAGS, PCB, protected_selection)
from probe_ch019_existing_via_bridge import VIA_ENDS
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA

ROOT = Path(__file__).resolve().parent
UUID_GROUPS = {
    'CH026_P_MUX': (
        '82a1c65b-3d26-4d1f-be55-3962e9e1f1db',
        '33bd3c0c-2cec-4190-a52a-baa0606f516c',
        '8becd9ff-318f-4161-8602-37776971617d',
        '6549b817-a68e-45d5-96b9-7cbabd2eacf3',
    ),
    'CH027_P_MUX': (
        'bba58354-dd4e-400c-9bc1-df854fac72d8',
        '9683e15c-6b52-4b45-8e42-11290ee1d99b',
    ),
    'MUX_EN': ('8b6baf5a-aa8f-4eea-9681-7cdc57183397',),
}
CASES = {
    '026-single': {'CH026_P_MUX': (UUID_GROUPS['CH026_P_MUX'][0],)},
    '026-trunk': {'CH026_P_MUX': UUID_GROUPS['CH026_P_MUX']},
    '027-pair': {'CH027_P_MUX': UUID_GROUPS['CH027_P_MUX']},
    '026-and-027': {'CH026_P_MUX': UUID_GROUPS['CH026_P_MUX'],
                    'CH027_P_MUX': UUID_GROUPS['CH027_P_MUX']},
    '026-027-en': {**UUID_GROUPS},
    'exact-eight-conflicts': {
        'CH019_N_MUX': (
            'cbef8349-505c-5ce2-812b-299cf1e09ca5',
            '0832ca70-347c-5b2d-b8d9-c8fff7096f8a',
        ),
        'BANK1_P_MUX_OUT': (
            '7d5653c6-8ba9-40b9-afd5-266ed0ef4353',
        ),
        'CH026_P_MUX': UUID_GROUPS['CH026_P_MUX'] + (
            'd3abb5e2-a155-421a-8a73-4d1ef441d576',
        ),
    },
    'exact-eleven-conflicts': {
        'CH019_N_MUX': (
            'cbef8349-505c-5ce2-812b-299cf1e09ca5',
            '0832ca70-347c-5b2d-b8d9-c8fff7096f8a',
        ),
        'BANK1_P_MUX_OUT': (
            '7d5653c6-8ba9-40b9-afd5-266ed0ef4353',
        ),
        'CH026_P_MUX': UUID_GROUPS['CH026_P_MUX'] + (
            'd3abb5e2-a155-421a-8a73-4d1ef441d576',
        ),
        'MUX_EN': UUID_GROUPS['MUX_EN'],
    },
}


def model(board_path: Path, output: Path, case: str,
          joint_order: str = 'ch024-first', reserve_radius: float = .65,
          ch022_root: str = 'J2.23',
          via_plan: bool = False,
          ch026_escape_cut: bool = False,
          ch026_restore_early: bool = False,
          ch022_bcu_inventory: bool = False,
          ch017_local_restore: bool = False) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box, Point, LineString
    from analyze_139_escape_blockers import protected_power, windows
    from route_targeted_closure import xy, routing_domain, native_fresh
    from escape_mesh_505 import mesh_route, add_mesh_path
    from probe_ch019_trunk_return import pads
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import outlines, power_copper

    board = pcbnew.LoadBoard(str(board_path))
    base = pcbnew.LoadBoard(str(board_path))
    reserve = protected_power(board)
    region = routing_domain(board, .30, .25).intersection(box(12, .5, 59, 69))
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    result = {**FLAGS, 'case': case, 'status': 'not_started',
              'selected_segment_uuid': [], 'joint_order': joint_order,
              'radius_mm': reserve_radius, 'ch022_root': ch022_root,
              'forced_existing_pad_via_plan': via_plan,
              'ch026_escape_cut': ch026_escape_cut,
              'ch026_restore_early': ch026_restore_early,
              'ch017_local_restore': ch017_local_restore,
              'ch017_segment_uuids': [], 'ch017_native_continuity_ok': False}
    chosen = protected_selection(board, 'entire_trunk')
    lookup = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    extra = CASES[case]
    for net, uuids in extra.items():
        for uid in uuids:
            t = lookup.get(uid)
            expected_layer = (pcbnew.B_Cu if net in ('CH019_N_MUX', 'BANK1_P_MUX_OUT')
                              else pcbnew.F_Cu)
            if t is None or t.GetNetname() != net or t.GetLayer() != expected_layer:
                raise ValueError('Exact protected F.Cu candidate mismatch: ' + uid)
            if isinstance(t, (pcbnew.PCB_ARC, pcbnew.PCB_VIA)):
                raise ValueError('No via/arc can be relocated')
            chosen.append(t)
    if ch026_escape_cut:
        from shapely.geometry import Point as SafePoint, LineString as SafeLine
        from route_targeted_closure import xy as location
        cut_uuid = 'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa'
        track = lookup.get(cut_uuid)
        if (track is None or track.GetNetname() != 'CH026_P_ELECTRODE'
                or track.GetLayer() != pcbnew.F_Cu
                or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise ValueError('Pinned CH026-P F.Cu escape identity changed')
        line = SafeLine([location(track.GetStart()), location(track.GetEnd())])
        protect_pads = [SafePoint(pt) for _, pt, _ in pads(board, 'CH026_P_ELECTRODE')]
        protect_vias = [SafePoint(location(t.GetPosition()))
                        for t in board.GetTracks()
                        if isinstance(t, pcbnew.PCB_VIA)
                        and t.GetNetname() == 'CH026_P_ELECTRODE']
        if (any(line.distance(p) < 1.0 for p in protect_pads)
                or any(line.distance(v) < .65 for v in protect_vias)):
            raise RuntimeError('CH026 pad/via escape guard violated')
        chosen.append(track)
        result['CH026_escape_cut_uuid'] = cut_uuid
    # Only these two SHA-pinned CH017_N B.Cu interior links may be moved.
    # All adjoining copper, AGND, VCM, protected electrode nets and via
    # terminals are immutable; the route must be fully restituted *before*
    # any attempted CH022 B.Cu bridge.
    ch017_segments = []
    if ch017_local_restore:
        from shapely.geometry import LineString as CH017Line, Point as CH017Point
        from collections import Counter
        expected = (
            'd04ea811-0e34-5d4f-8320-88b489821ec6',
            '4aa24dbb-0a8d-5bc6-afe9-6f73d285e716',
        )
        for uid in expected:
            t = lookup.get(uid)
            if (t is None or t.GetNetname() != 'CH017_N_ELECTRODE'
                    or t.GetLayer() != pcbnew.B_Cu
                    or isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                raise ValueError('Pinned CH017_N segment identity changed: ' + uid)
            line = CH017Line([xy(t.GetStart()), xy(t.GetEnd())])
            pad_centers = [CH017Point(xy(p.GetPosition()))
                           for fp in board.GetFootprints() for p in fp.Pads()
                           if p.GetNetname() == 'CH017_N_ELECTRODE']
            via_centers = [CH017Point(xy(v.GetPosition()))
                           for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)
                           and v.GetNetname() == 'CH017_N_ELECTRODE']
            if (any(line.distance(p) < 1.0 for p in pad_centers)
                    or any(line.distance(v) < .65 for v in via_centers)):
                raise ValueError('CH017_N pad/via escape cannot be displaced: ' + uid)
            ch017_segments.append(t)
        counts = Counter(xy(t.GetStart()) for t in ch017_segments)
        counts.update(xy(t.GetEnd()) for t in ch017_segments)
        ch017_pivots = [pt for pt, count in counts.items() if count == 2]
        ch017_ends = sorted([pt for pt, count in counts.items() if count == 1])
        if len(ch017_pivots) != 1 or len(ch017_ends) != 2:
            raise ValueError('CH017_N candidate is no longer an exact two-link chain')
        chosen.extend(ch017_segments)
        result['ch017_segment_uuids'] = list(expected)
    # Strict scope and unique object identity before any mutation.
    if len({t.m_Uuid.AsString() for t in chosen}) != len(chosen):
        raise ValueError('Duplicate selected SWIG track')
    result['selected_segment_uuid'] = [t.m_Uuid.AsString() for t in chosen]
    original_ch018 = [(t.m_Uuid.AsString(), xy(t.GetStart()),
                       xy(t.GetEnd()), t.GetLayer())
                      for t in board.GetTracks() if t.GetNetname() == 'CH018_N_MUX']
    original_vcm = [(t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()),
                     t.GetLayer())
                    for t in board.GetTracks() if t.GetNetname() == 'VCM']
    # Fail closed if an existing CH022 F.Cu pad escape at J2.23 would
    # be cut; keep all J2-adjacent copper byte-identical.
    joint_pads = {name: pt for net in ('CH022_N_ELECTRODE', 'CH024_P_MUX')
                  for name, pt, _ in pads(board, net)}
    if set(('J2.23','R302.1','U3.23','R49.1','R305.2')) - set(joint_pads):
        raise ValueError('Critical pad identities have changed')
    j2_point = Point(joint_pads['J2.23'])
    untouched_j2 = {
        t.m_Uuid.AsString(): (xy(t.GetStart()), xy(t.GetEnd()), t.GetLayer())
        for t in board.GetTracks()
        if t.GetNetname() == 'CH022_N_ELECTRODE'
        and (Point(xy(t.GetPosition())).distance(j2_point) < .75
             if isinstance(t, pcbnew.PCB_VIA)
             else LineString([xy(t.GetStart()), xy(t.GetEnd())]).distance(j2_point) < .75)
    }
    if any(t.m_Uuid.AsString() in untouched_j2 for t in chosen):
        raise RuntimeError('Selection would disturb J2.23 escape')
    result['preserved_J2_23_copper_objects'] = len(untouched_j2)
    for t in chosen:
        board.Remove(t)
    try:
        seeded_ch022: dict[str, Any] = {}

        def connect_ch022_via_bridge(stage: str = 'all') -> bool:
            if stage == 'finish':
                if set(seeded_ch022) != {'rvia', 'jvia', 'code'}:
                    raise RuntimeError('Incomplete CH022 preseed state')
                rvia = seeded_ch022['rvia']
                jvia = seeded_ch022['jvia']
                code = seeded_ch022['code']
                bridge = mesh_route(board, rvia, jvia, code, layers,
                                    reserve, region, start_layer=1, goal_layer=1)
                if bridge is None or len(bridge) < 2:
                    if ch022_bcu_inventory:
                        from analyze_ch022_bcu_blockers import survey
                        result['bcu_obstacle_inventory'] = survey(board, rvia, jvia)
                    result['status'] = 'ch022_seeded_BCu_bridge_blocked'
                    return False
                add_mesh_path(board, bridge, code, layers)
                result['CH022_N_ELECTRODE_geometry_proposed'] = True
                result['CH022_via_points'] = {'R302.1': rvia, 'J2.23': jvia}
                result['ch022_interleaved_BCu_proposed'] = True
                return True

            # Require a real F.Cu-connected legal via window at BOTH
            # CH022 pads. Never via-in-pad or into the L3 plane outline.
            electrodes = pads(board, 'CH022_N_ELECTRODE')
            by_pad = {name: (pt, code) for name, pt, code in electrodes}
            if set(by_pad) != {'J2.23','R302.1'}:
                raise ValueError('Unexpected CH022 pad topology')
            from shapely.ops import unary_union
            from route_targeted_closure import obstacles
            from escape_mesh_505 import polygons
            candidates = {}
            for name in ('R302.1','J2.23'):
                pt, code = by_pad[name]
                component, _ = windows(board, code, pt, region, reserve)
                _, via_obstacle = obstacles(
                    board, code, .15, .15, region, .60, (pcbnew.F_Cu,pcbnew.B_Cu))
                # Restrict the copper-connected via centers to <=3.5 mm
                # from THEIR OWN pad; never reuse one global best patch.
                local = (component.difference(
                    unary_union([via_obstacle, reserve.buffer(.505)]))
                    .intersection(Point(pt).buffer(3.5)).buffer(-.000005))
                patches = [g for g in polygons(local) if g.area > 1e-8]
                result[name+'_legal_via_area_mm2'] = round(local.area,8)
                if not patches:
                    result['failed_net'] = 'CH022_N_ELECTRODE'
                    result['failed_pad'] = name
                    result['status'] = 'ch022_no_connected_local_via'
                    return False
                patch = min(patches, key=lambda q: (q.distance(Point(pt)),-q.area))
                candidates[name] = tuple(patch.representative_point().coords[0])
            if Point(candidates['R302.1']).distance(Point(candidates['J2.23'])) < 1.0:
                raise ValueError('Local CH022 via windows overlap unexpectedly')
            code = by_pad['R302.1'][1]
            # Escape R302 on F.Cu to first through-via, bridge on B.Cu
            # (optional legal additional transitions via mesh), and enter
            # J2 existing F.Cu island from the second legal through-via.
            rvia = candidates['R302.1']
            jvia = candidates['J2.23']
            def apply(start: tuple[float, float], goal: tuple[float, float],
                      start_layer: int, goal_layer: int,
                      allow_vias: bool = True) -> bool:
                result['forced_route_stage'] = (str(start_layer)+':'+str(start)
                                                 +' -> '+str(goal_layer)+':'+str(goal))
                path = mesh_route(board, start, goal, code, layers, reserve, region,
                                  start_layer=start_layer, goal_layer=goal_layer,
                                  allow_vias=allow_vias)
                if path is None:
                    result['failed_stage'] = 'missing_route'
                    result['failed_stage_endpoints'] = [start, goal]
                    return False
                if len(path) < 2:
                    result['failed_stage'] = 'degenerate_single_node_route'
                    result['failed_stage_endpoints'] = [start, goal]
                    return False
                add_mesh_path(board, path, code, layers)
                return True
            if not apply(by_pad['R302.1'][0], rvia, 0, 0, False):
                result['status'] = 'ch022_R302_FCu_via_escape_blocked'
                return False
            # Rounding and native obstacle checks remain authoritative:
            # the via centres originate from same-net connected windows.
            result['forced_route_stage'] = 'via_R302.1'
            add_mesh_path(board, [(0,*rvia),(1,*rvia)], code, layers)
            if stage == 'seed':
                # Fix both endpoint vias and their F.Cu escapes *before*
                # CH024-P is added, but delay only the intervening B.Cu
                # trunk until CH024-P and CH019-P have been routed.
                add_mesh_path(board, [(1,*jvia),(0,*jvia)], code, layers)
                if not apply(jvia, by_pad['J2.23'][0], 0, 0, False):
                    result['status'] = 'ch022_seeded_J2_escape_blocked'
                    return False
                seeded_ch022.update({'rvia': rvia, 'jvia': jvia, 'code': code})
                result['ch022_FCu_escapes_and_vias_seeded'] = True
                result['CH022_via_points'] = {'R302.1': rvia, 'J2.23': jvia}
                return True
            if not apply(rvia, jvia, 1, 1):
                result['status'] = 'ch022_BCu_return_blocked'
                return False
            result['forced_route_stage'] = 'via_J2.23'
            add_mesh_path(board, [(1,*jvia),(0,*jvia)], code, layers)
            if not apply(jvia, by_pad['J2.23'][0], 0, 0, False):
                result['status'] = 'ch022_J2_FCu_reentry_blocked'
                return False
            result['CH022_N_ELECTRODE_geometry_proposed'] = True
            result['CH022_via_points'] = {'R302.1': rvia, 'J2.23': jvia}
            return True

        def connect(net: str, required: set[str] | None = None) -> bool:
            terminals = pads(board, net)
            if required is not None and {n for n, _, _ in terminals} != required:
                raise ValueError('Unexpected ' + net + ' terminals')
            root = ch022_root if net == 'CH022_N_ELECTRODE' else 'R49.1'
            source = next((t for t in terminals if t[0] == root), None)
            if source is None:
                raise ValueError('Missing route root ' + root)
            targets = [source] + [t for t in terminals if t != source]
            competing = 'U3.23' if net == 'CH022_N_ELECTRODE' else 'R302.1'
            empty = Point(0, 0).buffer(0)
            extra = [Point(joint_pads[competing]).buffer(reserve_radius),
                     empty, empty]
            for padname, coord, _ in targets[1:]:
                path = mesh_route(board, source[1], coord, source[2],
                                  layers, reserve, region, extra_obstacles=extra)
                if path is None:
                    result['failed_net'] = net
                    result['failed_pad'] = padname
                    return False
                add_mesh_path(board, path, source[2], layers)
            result[net+'_geometry_proposed'] = True
            return True

        if joint_order.startswith('interleave'):
            if not via_plan or not ch026_escape_cut:
                raise ValueError('Interleaving requires CH026 removal and legal via plan')
            if not connect_ch022_via_bridge('seed'):
                result['status'] = 'ch022_escape_preseed_failed'
                return result
        if ch026_restore_early:
            if not joint_order.startswith('interleave') or not ch026_escape_cut:
                raise ValueError('Early CH026 restitution requires preseed and pinned cut')
            blocker = next((t for t in chosen if
                            t.m_Uuid.AsString() ==
                            'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa'), None)
            if blocker is None or blocker.GetNetname() != 'CH026_P_ELECTRODE':
                raise ValueError('Missing original CH026-P blocker reference')
            alternative = mesh_route(board, xy(blocker.GetStart()),
                                     xy(blocker.GetEnd()), blocker.GetNetCode(),
                                     layers, reserve, region,
                                     start_layer=0, goal_layer=0)
            if alternative is None or len(alternative) < 2:
                result['status'] = 'ch026_early_segment_restitution_blocked'
                result['failed_neighbor'] = blocker.GetNetname()
                result['failed_uuid'] = blocker.m_Uuid.AsString()
                return result
            add_mesh_path(board, alternative, blocker.GetNetCode(), layers)
            result['ch026_early_segment_restored_geometrically'] = True
        if ch017_local_restore:
            # Restore CH017 immediately: leaving it disconnected while CH022
            # crosses its old copper would be a false-positive closure.
            from shapely.geometry import Point as CH017Point, LineString as CH017Line
            pivot = ch017_pivots[0]
            touched = any(
                (CH017Point(xy(t.GetPosition())).distance(CH017Point(pivot)) < 0.000001
                 if isinstance(t, pcbnew.PCB_VIA)
                 else CH017Line([xy(t.GetStart()), xy(t.GetEnd())]).distance(
                     CH017Point(pivot)) < 0.000001)
                for t in board.GetTracks()
                if t.GetNetname() == 'CH017_N_ELECTRODE'
            )
            # Preserve the center node if it is a real third-branch junction.
            waypoints = [ch017_ends[0], pivot, ch017_ends[1]] if touched else ch017_ends
            result['ch017_pivot_preserved'] = touched
            result['ch017_original_endpoints_mm'] = [list(p) for p in ch017_ends]
            result['ch017_new_routes'] = []
            for p0, p1 in zip(waypoints, waypoints[1:]):
                local = region.intersection(box(31, 11.5, 49, 27))
                candidate = mesh_route(
                    board, p0, p1, ch017_segments[0].GetNetCode(),
                    layers, reserve, local, start_layer=1, goal_layer=1)
                if candidate is None or len(candidate) < 2:
                    result['status'] = 'ch017_local_restitution_blocked'
                    return result
                add_mesh_path(board, candidate, ch017_segments[0].GetNetCode(), layers)
                result['ch017_new_routes'].append([list(p) for p in candidate])
            # Native KiCad check of CH017 alone, even if a later CH022
            # proposal fails. Other deliberately removed test-net copper
            # must NOT be mistaken for an accepted full-board result.
            pcbnew.SaveBoard(str(board_path), board)
            original_report = native_fresh(
                output.parent / 'baseline' / PCB,
                output.with_suffix('.ch017-baseline-drc.json'))
            ch017_report = native_fresh(
                board_path, output.with_suffix('.ch017-probe-drc.json'))
            from native_connectivity import airwire_counts
            previous = airwire_counts(original_report)['CH017_N_ELECTRODE']
            current = airwire_counts(ch017_report)['CH017_N_ELECTRODE']
            errors = [v for v in ch017_report.get('violations', [])
                      if 'CH017_N_ELECTRODE' in json.dumps(v)]
            result['ch017_airwires_before'] = previous
            result['ch017_airwires_after'] = current
            result['ch017_native_violations'] = len(errors)
            result['ch017_native_continuity_ok'] = (
                previous == 0 and current == 0 and not errors)
            if not result['ch017_native_continuity_ok']:
                result['status'] = 'ch017_native_restitution_failed'
                return result
        if joint_order == 'ch022-first':
            if not (connect_ch022_via_bridge() if via_plan else
                    connect('CH022_N_ELECTRODE', {'J2.23','R302.1'})):
                result['status'] = 'ch022_route_blocked'
                return result
            result['ch022_pad_reconnection_proposed'] = True
        if not connect('CH024_P_MUX', {'R49.1','U3.23','R305.2'}):
            result['status'] = 'ch024_geometry_blocked'
            return result
        result['ch024_three_pads_proposed'] = True

        if joint_order == 'interleave-before-ch019':
            if not connect_ch022_via_bridge('finish'):
                result['status'] = 'ch022_interleaved_BCu_blocked'
                return result
            result['ch022_pad_reconnection_proposed'] = True

        # Existing through-vias only at the endpoints, no new via at U3.6.
        va, vb = VIA_ENDS['direct']
        via_set = {xy(t.GetPosition()) for t in board.GetTracks()
                   if isinstance(t, pcbnew.PCB_VIA)
                   and t.GetNetname() == 'CH019_P_MUX'}
        if va not in via_set or vb not in via_set:
            raise ValueError('CH019 return vias not retained')
        net = next(p.GetNetCode() for f in board.GetFootprints()
                   for p in f.Pads() if p.GetNetname() == 'CH019_P_MUX')
        path = mesh_route(board, va, vb, net, layers, reserve, region,
                          start_layer=1, goal_layer=1)
        if path is None:
            result['status'] = 'CH019_existing_vias_not_connected'
            return result
        add_mesh_path(board, path, net, layers)
        result['ch019_via_bridge_proposed'] = True

        if joint_order == 'interleave':
            if not connect_ch022_via_bridge('finish'):
                result['status'] = 'ch022_interleaved_BCu_blocked'
                return result
            result['ch022_pad_reconnection_proposed'] = True

        if joint_order == 'ch024-first':
            if not (connect_ch022_via_bridge() if via_plan else
                    connect('CH022_N_ELECTRODE', {'J2.23','R302.1'})):
                result['status'] = 'ch022_route_blocked'
                return result
            result['ch022_pad_reconnection_proposed'] = True

        skipped_segments = []
        for segment in chosen:
            if (ch026_restore_early and segment.m_Uuid.AsString() ==
                    'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa'):
                continue  # This component was already restored before CH024.
            # Pad-connected CH022 and existing-via CH019 replace old
            # piece-by-piece copper; native connectivity is mandatory.
            if segment.GetNetname() in ('CH022_N_ELECTRODE','CH019_P_MUX'):
                skipped_segments.append(segment.m_Uuid.AsString())
                continue
            layer = layers.index(segment.GetLayer())
            route = mesh_route(board, xy(segment.GetStart()),
                               xy(segment.GetEnd()), segment.GetNetCode(),
                               layers, reserve, region,
                               start_layer=layer, goal_layer=layer)
            if route is None:
                result['failed_neighbor'] = segment.GetNetname()
                result['failed_uuid'] = segment.m_Uuid.AsString()
                result['status'] = 'neighbor_unrestored'
                return result
            add_mesh_path(board, route, segment.GetNetCode(), layers)
        result['superseded_old_segment_uuids'] = skipped_segments
        current_j2 = {t.m_Uuid.AsString(): (xy(t.GetStart()), xy(t.GetEnd()), t.GetLayer())
                      for t in board.GetTracks() if t.m_Uuid.AsString() in untouched_j2}
        if current_j2 != untouched_j2:
            raise RuntimeError('J2.23 original copper was modified')
        current_ch018 = [(t.m_Uuid.AsString(), xy(t.GetStart()),
                         xy(t.GetEnd()), t.GetLayer()) for t in board.GetTracks()
                         if t.GetNetname() == 'CH018_N_MUX']
        current_vcm = [(t.m_Uuid.AsString(), xy(t.GetStart()),
                        xy(t.GetEnd()), t.GetLayer()) for t in board.GetTracks()
                       if t.GetNetname() == 'VCM']
        if current_ch018 != original_ch018 or current_vcm != original_vcm:
            raise RuntimeError('Protected CH018-N/VCM copper mutated')
        pcbnew.SaveBoard(str(board_path), board)
        before = native_fresh(output.parent / 'baseline' / PCB,
                              output.with_suffix('.before.json'))
        after = native_fresh(board_path, output.with_suffix('.after.json'))
        observed = pcbnew.LoadBoard(str(board_path))
        p0, p1 = power_copper(base), power_copper(observed)
        result.update({
            'drc_violations': len(after.get('violations', [])),
            'drc_unconnected': len(after.get('unconnected_items', [])),
            'drc_warnings': sum(t.get('severity') == 'warning'
                                for t in after.get('violations', [])
                                + after.get('unconnected_items', [])),
            'regressed_nets': regressed_nets(before, after),
            'L3_loss_mm2': p0.difference(p1).area,
            'L3_gain_mm2': p1.difference(p0).area,
            'zone_outlines_unchanged': outlines(base) == outlines(observed),
        })
        result['status'] = 'native_audit_only_unaccepted'
        return result
    finally:
        for t in chosen:
            board.Add(t)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--joint-order', choices=('ch022-first','ch024-first','interleave','interleave-before-ch019'),
                        required=True)
    parser.add_argument('--reserve-radius', type=float, choices=(.35,.65,.95),
                        required=True)
    parser.add_argument('--ch022-root', choices=('J2.23','R302.1'), required=True)
    parser.add_argument('--ch017-local-restore', action='store_true',
                        help='Route both pinned CH017_N BCu segments before CH022; reject native regressions')
    parser.add_argument('--ch022-bcu-inventory', action='store_true',
                        help='Capture protected B.Cu blockers if seeded via bridge is blocked')
    parser.add_argument('--ch026-restore-early', action='store_true',
                        help='Test CH026 segment restitution directly after CH022 via-seed')
    parser.add_argument('--ch026-escape-cut', action='store_true',
                        help='Selectively reroute pinned CH026-P FCu blocker')
    parser.add_argument('--ch022-via-plan', action='store_true',
                        help='Require F.Cu pad island vias and B.Cu return')
    args = parser.parse_args()
    if args.output.exists() or args.output.suffix != '.json':
        raise ValueError('Only new JSON reports')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Refuse repository output')
    fixture = frozen_archive(args.archive)
    if digest(fixture[PCB]) != FROZEN_INPUT_SHA:
        raise ValueError('Wrong diagnostic native PCB')
    with tempfile.TemporaryDirectory(prefix='ch019-crosslayer-') as temp:
        work = Path(temp)
        for name, raw in fixture.items():
            (work / name).write_bytes(raw)
        baseline = work / 'baseline'
        baseline.mkdir()
        for name, raw in fixture.items():
            (baseline / name).write_bytes(raw)
        try:
            output = model(work / PCB, work / 'crosslayer.json', 'exact-eleven-conflicts',
                           args.joint_order, args.reserve_radius, args.ch022_root,
                           args.ch022_via_plan, args.ch026_escape_cut,
                           args.ch026_restore_early, args.ch022_bcu_inventory,
                           args.ch017_local_restore)
        except Exception as exc:
            output = {**FLAGS, 'status': 'diagnostic_exception',
                      'error_type': type(exc).__name__, 'detail': str(exc),
                      'joint_order': args.joint_order,
                      'radius_mm': args.reserve_radius,
                      'ch022_root': args.ch022_root,
                      'forced_existing_pad_via_plan': args.ch022_via_plan,
                      'ch026_escape_cut': args.ch026_escape_cut,
                      'ch026_restore_early': args.ch026_restore_early,
                      'ch022_bcu_inventory': args.ch022_bcu_inventory,
                      'ch017_local_restore': args.ch017_local_restore}
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Source archive changed')
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(args.joint_order, args.reserve_radius, args.ch022_root,
          output['status'], output.get('failed_net'), output.get('failed_pad'), flush=True)


if __name__ == '__main__':
    main()

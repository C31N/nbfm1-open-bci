#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Test via-safe CH025_N interior opening against real KiCad F.Cu topology.

Read-only publication: temporarily remove only pinned CH024_N tracks and the
middle of pinned CH025_N, retaining original pad/via copper via exact F.Cu
stubs. Roll back all mutations. No manufacturing or checkpoint outputs.
"""
from __future__ import annotations

from typing import Any

FLAGS = dict(model_only=True, accepted=False, routing_completed=False,
             fabrication_release=False, native_qualification=False,
             independent_replay_verified=False, manufacturing_files=False)


def inner_endpoints(window: dict[str, Any], shrink_mm: float = .012
                    ) -> tuple[tuple[float, float], tuple[float, float]]:
    """Snap a horizontal protected interior window to a conservative cut."""
    a, b = window['start_mm'], window['end_mm']
    if abs(a[1] - b[1]) > .000001:
        raise ValueError('CH025 pinned F.Cu segment direction changed')
    if b[0] - a[0] < .05 + 2 * shrink_mm:
        raise ValueError('CH025 interior window too short')
    if shrink_mm < .01:
        raise ValueError('No shrink below .01 mm allowed')
    return ((round(a[0] + shrink_mm, 6), round(a[1], 6)),
            (round(b[0] - shrink_mm, 6), round(b[1], 6)))


def same_net_cut_contacts(
        cut_start: tuple[float, float], cut_end: tuple[float, float],
        segments: list[tuple[str, tuple[float, float], tuple[float, float]]]
        ) -> list[dict[str, Any]]:
    """Read-only inventory of same-net joins or overlaps at a proposed cut.

    ANY touching foreign segment is a blocking condition. A collinear trace
    is not silently treated as redundant: native connectivity and full DRC
    would be required before changing such topology.
    """
    from shapely.geometry import LineString
    from shapely.ops import nearest_points

    cut = LineString([cut_start, cut_end])
    if cut.length < .000001:
        raise ValueError('Degenerate CH025_N cut')
    conflicts = []
    for uid, start, end in sorted(segments, key=lambda x: x[0]):
        segment = LineString([start, end])
        dist = cut.distance(segment)
        if dist >= .000005:
            continue
        a, b = nearest_points(cut, segment)
        overlap = cut.intersection(segment)
        conflicts.append({
            'uuid': uid, 'track_start_mm': list(start),
            'track_end_mm': list(end),
            'closest_cut_point_mm': [round(a.x, 6), round(a.y, 6)],
            'closest_other_point_mm': [round(b.x, 6), round(b.y, 6)],
            'distance_mm': round(dist, 7),
            'overlap_mm': round(overlap.length, 7),
            'junction_type': ('collinear_overlap' if overlap.length > .000005
                              else 'same_net_point_contact'),
            'safety_decision': 'BLOCK_INTERIOR_MUTATION',
        })
    return conflicts


def evaluate(board: Any, start: tuple[float, float],
             end: tuple[float, float], code: int, region: Any,
             reserve: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union, nearest_points
    from analyze_ch025_via_guard import survey
    from probe_ch022_fcu_micro import (
        PINNED_CH024N, PINNED_CH025N, GUARDED_NETS, _copper_signature,
        _safe_candidates,
    )
    from probe_ch022_agnd_hop import DOWNSTREAM, _samples
    from route_targeted_closure import obstacles, xy, make_track
    from escape_mesh_505 import polygons

    lookup = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    target = lookup.get(PINNED_CH025N)
    if target is None or target.GetNetname() != 'CH025_N_ELECTRODE':
        raise ValueError('CH025 pinned target missing')
    if abs(pcbnew.ToMM(target.GetWidth()) - .15) > .000001:
        raise ValueError('CH025 pinned F.Cu width changed')
    cut_report = survey(board)
    movable, _ = _safe_candidates(board)
    ch024 = [t for t in movable if t.m_Uuid.AsString() in PINNED_CH024N]
    report = {
        **FLAGS, 'status': 'no_safe_joint_interior_trial',
        'ch025_contact_survey': cut_report, 'trials': [],
        'protected_nets': sorted(GUARDED_NETS),
        'power_keepout_mm': .505, 'edge_clearance_mm': .25,
    }
    if len(ch024) != 2 or not cut_report['interior_cut_windows']:
        report['status'] = ('CH024_N_pinned_pair_not_movable' if len(ch024) != 2
                            else 'CH025_N_no_via_safe_interior_window')
        report['all_trials_rolled_back'] = True
        return report
    before_protected = _copper_signature(board, GUARDED_NETS)
    old = [*ch024, target]
    original_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
    a, b = xy(target.GetStart()), xy(target.GetEnd())
    direct = LineString([start, end])
    for window in cut_report['interior_cut_windows']:
        left, right = inner_endpoints(window)
        record = {'interior_cut_start_mm': list(left),
                  'interior_cut_end_mm': list(right),
                  'CH025_contact_stubs_preserved': False,
                  'CH022_FCu_connected': False}
        record['mutation_attempted'] = False
        report['trials'].append(record)
        cut = LineString([left, right])
        vias = [xy(t.GetPosition()) for t in board.GetTracks()
                if isinstance(t, pcbnew.PCB_VIA)
                and t.GetNetname() == target.GetNetname()]
        pads = [xy(p.GetPosition()) for fp in board.GetFootprints()
                for p in fp.Pads() if p.GetNetname() == target.GetNetname()]
        if any(cut.distance(Point(p)) < .65 for p in vias):
            raise RuntimeError('CH025 via contact would be cut')
        if any(cut.distance(Point(p)) < 1.0 for p in pads):
            raise RuntimeError('CH025 pad contact would be cut')
        neighbours = [
            (t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()))
            for t in board.GetTracks()
            if (t is not target and t.GetNetname() == target.GetNetname()
                and not isinstance(t, pcbnew.PCB_VIA)
                and t.GetLayer() == pcbnew.F_Cu)
        ]
        contacts = same_net_cut_contacts(left, right, neighbours)
        record['same_net_contact_blockers'] = contacts
        if contacts:
            record['status'] = 'CH025_interior_branch_or_overlap_protected'
            record['original_copper_untouched'] = True
            # This isn't a routing crash: the pinned topological guard works.
            # No segment, pad, via, VCM or L3 plane has been altered.
            continue
        record['mutation_attempted'] = True
        for t in old:
            board.Remove(t)
        try:
            make_track(board, a, left, target.GetNetCode(), .15, pcbnew.F_Cu)
            make_track(board, right, b, target.GetNetCode(), .15, pcbnew.F_Cu)
            # Retained stubs must cover original F.Cu centreline within
            # every protected contact circle, independent of cut position.
            survivor = unary_union((LineString([a, left]),
                                    LineString([right, b])))
            original = LineString([a, b])
            for centre, radius in [*((p, .65) for p in vias),
                                   *((p, 1.) for p in pads)]:
                exposed = original.intersection(Point(centre).buffer(radius - .00001))
                if exposed.difference(survivor.buffer(.000003)).length > .000005:
                    raise RuntimeError('CH025 via/pad original copper not retained')
            record['CH025_contact_stubs_preserved'] = True
            if _copper_signature(board, GUARDED_NETS) != before_protected:
                raise RuntimeError('Protected VCM or neighbour copper mutated')
            blocked, viaobs = obstacles(
                board, code, .15, .15, region, .60,
                (pcbnew.F_Cu, pcbnew.B_Cu))
            front = region.difference(blocked[0]).buffer(-.000005)
            source = next((p for p in polygons(front)
                           if p.covers(Point(start))), None)
            legal = region.difference(unary_union(
                (viaobs, reserve.buffer(.505), blocked[0], blocked[1]))).buffer(-.002)
            area = legal.intersection(box(*DOWNSTREAM)).intersection(direct.buffer(6.0))
            sites = _samples(area, direct, end, 4)
            viable = [p for p in sites if source is not None
                      and source.covers(Point(p))]
            record['lower_via_candidates_mm'] = [list(p) for p in sites]
            record['source_connected_lower_vias_mm'] = [list(p) for p in viable]
            record['CH022_FCu_connected'] = bool(viable)
            if source is not None and not viable:
                parts = polygons(front)
                gaps = []
                for p in sites:
                    target_part = next((c for c in parts
                                        if c.covers(Point(p))), None)
                    if target_part is None or target_part == source:
                        continue
                    pt1, pt2 = nearest_points(source, target_part)
                    gaps.append((pt1.distance(pt2), p, pt1, pt2))
                if gaps:
                    dist, pos, one, two = min(gaps, key=lambda z: (z[0], z[1]))
                    record['residual_FCu_gap_mm'] = round(dist, 7)
                    record['gap_edges_mm'] = [[one.x, one.y], [two.x, two.y]]
                    record['distance_from_cut_to_gap_mm'] = round(
                        cut.distance(LineString([one, two])), 7)
            record['status'] = ('FCu_geometrically_connected_but_unqualified'
                                if viable else 'FCu_still_separated')
            report['status'] = record['status']
        finally:
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in original_ids:
                    board.Remove(item)
            for item in old:
                board.Add(item)
            if _copper_signature(board, GUARDED_NETS) != before_protected:
                raise RuntimeError('Protected geometry rollback failed')
            if {t.m_Uuid.AsString() for t in board.GetTracks()} != original_ids:
                raise RuntimeError('Rollback changed board track UUID inventory')
    report['all_trials_rolled_back'] = True
    if report['trials'] and all(
            x.get('status') == 'CH025_interior_branch_or_overlap_protected'
            for x in report['trials']):
        report['status'] = 'CH025_interior_same_net_contact_guard'
        report['unique_blocker_uuids'] = sorted({
            x['uuid'] for trial in report['trials']
            for x in trial['same_net_contact_blockers']
        })
    return report

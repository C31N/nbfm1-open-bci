#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed, UUID-pinned CH024_N F.Cu micro-displacement for CH022 AGND hop.

Runs solely on an ephemeral KiCad trial board. Every rejected trial rolls back
all temporary changes. A geometry result is NOT a native DRC or 136 acceptance.
No source PCB, released checkpoint or manufacturing exports are written.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

PINNED_CH024N = (
    '7c87269e-9bef-4b54-82fa-41d657775aac',
    'f489590a-6746-48d2-bd2f-091103b220a3',
)
GUARDED_NETS = frozenset({
    'CH017_N_ELECTRODE', 'CH026_P_ELECTRODE',
    'CH024_P_MUX', 'CH019_P_MUX', 'VCM', 'AGND',
    'CH028_N_ELECTRODE', 'CH028_P_ELECTRODE',
    'CH030_N_ELECTRODE', 'CH030_P_ELECTRODE',
    'CH031_N_ELECTRODE', 'CH031_P_ELECTRODE',
})
FLAGS = {
    'model_only': True, 'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'native_qualification': False,
    'independent_replay_verified': False, 'manufacturing_files': False,
}


def _copper_signature(board: Any, names: frozenset[str]) -> dict[str, tuple[Any, ...]]:
    from route_targeted_closure import xy

    return {
        t.m_Uuid.AsString(): (
            t.GetNetname(), int(t.GetLayer()), xy(t.GetStart()), xy(t.GetEnd()))
        for t in board.GetTracks() if t.GetNetname() in names
    }


def _safe_candidates(board: Any) -> tuple[list[Any], list[dict[str, Any]]]:
    """Reject pad/via escapes and identity changes before touching copper."""
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import xy

    lookup = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    pads = [Point(xy(p.GetPosition()))
            for f in board.GetFootprints() for p in f.Pads()
            if p.GetNetname() == 'CH024_N_ELECTRODE']
    vias = [Point(xy(v.GetPosition())) for v in board.GetTracks()
            if isinstance(v, pcbnew.PCB_VIA)
            and v.GetNetname() == 'CH024_N_ELECTRODE']
    selected, inventory = [], []
    for uid in PINNED_CH024N:
        t = lookup.get(uid)
        if (t is None or t.GetNetname() != 'CH024_N_ELECTRODE'
                or t.GetLayer() != pcbnew.F_Cu
                or isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            raise ValueError('CH024_N pinned segment identity/layer mismatch: ' + uid)
        line = LineString([xy(t.GetStart()), xy(t.GetEnd())])
        pad_distance = min((line.distance(p) for p in pads), default=1e6)
        via_distance = min((line.distance(v) for v in vias), default=1e6)
        permitted = pad_distance >= 1.0 and via_distance >= .65
        inventory.append({
            'uuid': uid, 'net': t.GetNetname(), 'layer': 'F.Cu',
            'start_mm': list(xy(t.GetStart())), 'end_mm': list(xy(t.GetEnd())),
            'pad_distance_mm': round(pad_distance, 6),
            'via_distance_mm': round(via_distance, 6),
            'eligible': permitted,
        })
        if permitted:
            selected.append(t)
    return selected, inventory


def try_micro(board: Any, start: tuple[float, float],
              end: tuple[float, float], code: int,
              layers: tuple[int, ...], power: Any, region: Any
              ) -> tuple[bool, dict[str, Any]]:
    """Temporarily free only legal CH024_N interior copper; restore if possible.

    Exact pinned routing trial order: first UUID, second UUID, both. The
    preserved nets are compared by UUID and geometry before successful return.
    Full native zone fill/DRC/parity/power/replay remain separate hard gates.
    """
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles, xy
    from escape_mesh_505 import add_mesh_path, mesh_route, polygons
    from probe_ch022_agnd_hop import propose, DOWNSTREAM, _samples

    if layers != (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu):
        raise ValueError('Pinned CH022 layer order changed')
    if board.GetNetsByName().get('CH022_N_ELECTRODE').GetNetCode() != code:
        raise ValueError('CH022 identity changed')
    protected_before = _copper_signature(board, GUARDED_NETS)
    eligible, inventory = _safe_candidates(board)
    report: dict[str, Any] = {
        **FLAGS, 'status': 'no_eligible_CH024N_micro_displacement',
        'pinned_segment_inventory': inventory, 'trials': [],
        'protected_nets': sorted(GUARDED_NETS),
        'power_keepout_mm': .505, 'edge_clearance_mm': .25,
    }
    if not eligible:
        return False, report

    for count in (1, 2):
        for subset in combinations(eligible, count):
            ids = [t.m_Uuid.AsString() for t in subset]
            record: dict[str, Any] = {
                'candidate_uuids': ids, 'geometric_front_connected': False,
                'route_proposed': False, 'CH024N_restituted': False,
            }
            report['trials'].append(record)
            before_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            accepted_geometry = False
            for t in subset:
                board.Remove(t)
            try:
                # Fast component connectivity test BEFORE any costly routing.
                blocked, via_obstacle = obstacles(
                    board, code, .15, .15, region, .60,
                    (pcbnew.F_Cu, pcbnew.B_Cu))
                front = region.difference(blocked[0]).buffer(-.000005)
                source = next((p for p in polygons(front)
                               if p.covers(Point(start))), None)
                legal = region.difference(unary_union([
                    via_obstacle, power.buffer(.505),
                    blocked[0], blocked[1]])).buffer(-.002)
                band = legal.intersection(box(*DOWNSTREAM)).intersection(
                    LineString([start, end]).buffer(6.0))
                sites = _samples(band, LineString([start, end]), end, 4)
                viable = [pt for pt in sites if source is not None
                          and source.covers(Point(pt))]
                record['downstream_via_sites'] = [list(v) for v in sites]
                record['reachable_via_sites'] = [list(v) for v in viable]
                record['geometric_front_connected'] = bool(viable)
                if not viable:
                    record['status'] = 'FCu_still_separated'
                    continue
                route, hop_report = propose(
                    board, start, end, code, layers, power, region)
                record['hop_status'] = hop_report.get('status')
                if route is None:
                    record['status'] = 'no_complete_AGND_hop'
                    continue
                add_mesh_path(board, route, code, layers)
                record['route_proposed'] = True
                # Restore each displaced CH024_N two-ended interior link.
                restored = []
                for item in subset:
                    a, b = xy(item.GetStart()), xy(item.GetEnd())
                    # Keep restitution close to the original corridor.
                    local = region.intersection(
                        LineString([a, b]).buffer(5.0))
                    alt = mesh_route(
                        board, a, b, item.GetNetCode(), layers, power, local,
                        start_layer=0, goal_layer=0)
                    if alt is None or len(alt) < 2:
                        record['failed_restitution_uuid'] = item.m_Uuid.AsString()
                        break
                    add_mesh_path(board, alt, item.GetNetCode(), layers)
                    restored.append(item.m_Uuid.AsString())
                if len(restored) != len(subset):
                    record['status'] = 'CH024N_restitution_blocked'
                    continue
                record['CH024N_restituted'] = True
                if _copper_signature(board, GUARDED_NETS) != protected_before:
                    record['status'] = 'protected_geometry_changed'
                    continue
                record['status'] = 'full_geometry_proposal_needs_native_qualification'
                report['status'] = record['status']
                report['chosen_micro_uuids'] = ids
                accepted_geometry = True
                return True, report
            except (RuntimeError, ValueError, KeyError) as exc:
                record['status'] = 'diagnostic_exception'
                record['error'] = type(exc).__name__ + ': ' + str(exc)
            finally:
                if not accepted_geometry:
                    # Restore ALL newly added trial tracks and original items.
                    for item in list(board.GetTracks()):
                        if item.m_Uuid.AsString() not in before_ids:
                            board.Remove(item)
                    for item in subset:
                        board.Add(item)
                    if _copper_signature(board, GUARDED_NETS) != protected_before:
                        raise RuntimeError('Micro trial rollback changed protected copper')
    report['status'] = 'micro_variants_exhausted_without_restitution'
    return False, report

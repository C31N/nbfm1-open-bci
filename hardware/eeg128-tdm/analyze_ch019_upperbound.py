#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Upper-bound local CH019-P multilayer corridor study, never a PCB candidate.

Remove ONLY in-memory eligible F.Cu/B.Cu signal segments to determine if
a geometrical link exists even before rebuilding every displaced net.
VCM, CH018-N, pads, vias, power zones and original PCB bytes are immutable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive, digest, ZIP_SHA
from probe_ch019_trunk_return import protected_selection, pads, PCB, FLAGS
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA, A, B

ROOT = Path(__file__).resolve().parent


def evaluate(board: Any, ordering: str) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from analyze_139_escape_blockers import protected_power
    from route_targeted_closure import xy, routing_domain
    from escape_mesh_505 import mesh_route, add_mesh_path

    result: dict[str, Any] = {**FLAGS, 'ordering': ordering,
                              'status': 'not_started',
                              'upper_bound_only': True,
                              'full_neighbor_restitution': False}
    reserved = {'VCM', 'CH018_N_MUX'}
    pads_by_net: dict[str, list[Any]] = defaultdict(list)
    vias_by_net: dict[str, list[Any]] = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pads_by_net[pad.GetNetname()].append(Point(xy(pad.GetPosition())))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            vias_by_net[t.GetNetname()].append(Point(xy(t.GetPosition())))

    direct = LineString([A, B])
    corridor = direct.buffer(2., cap_style=2).union(
        Point(A).buffer(3.)).union(Point(B).buffer(3.))
    chosen = protected_selection(board, 'entire_trunk')
    seen = {t.m_Uuid.AsString() for t in chosen}
    for track in board.GetTracks():
        if isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
            continue
        if track.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        if track.GetNetname() in reserved | {'CH019_P_MUX', 'CH022_N_ELECTRODE'}:
            continue
        line = LineString([xy(track.GetStart()), xy(track.GetEnd())])
        if not line.intersects(corridor):
            continue
        if min((line.distance(p) for p in pads_by_net[track.GetNetname()]),
               default=1000.) < 1.0:
            continue
        if min((line.distance(v) for v in vias_by_net[track.GetNetname()]),
               default=1000.) < .65:
            continue
        if track.m_Uuid.AsString() not in seen:
            chosen.append(track)
            seen.add(track.m_Uuid.AsString())

    result['removed_signal_segments'] = len(chosen)
    result['relaxed_nets'] = dict(sorted(Counter(t.GetNetname() for t in chosen).items()))
    original_vcm = [(t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()))
                    for t in board.GetTracks() if t.GetNetname() == 'VCM']
    original_ch018 = [(t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()))
                      for t in board.GetTracks() if t.GetNetname() == 'CH018_N_MUX']
    power = protected_power(board)
    region = routing_domain(board, .30, .25).intersection(box(12, .5, 59, 69))
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    for t in chosen:
        board.Remove(t)
    try:
        def connect_ch024() -> bool:
            terminals = pads(board, 'CH024_P_MUX')
            if {n for n, _, _ in terminals} != {'R49.1', 'U3.23', 'R305.2'}:
                raise ValueError('CH024 pad identity altered')
            src = next(x for x in terminals if x[0] == 'R49.1')
            for name, dst, _ in terminals:
                if name == 'R49.1':
                    continue
                route = mesh_route(board, src[1], dst, src[2],
                                   layers, power, region)
                if route is None:
                    result['failed_pad'] = name
                    return False
                add_mesh_path(board, route, src[2], layers)
            result['CH024_three_pads_geometrically_proposed'] = True
            return True

        def bridge_ch019() -> bool:
            net = next(p.GetNetCode() for fp in board.GetFootprints()
                       for p in fp.Pads() if p.GetNetname() == 'CH019_P_MUX')
            path = mesh_route(board, A, B, net, layers, power, region,
                              start_layer=1, goal_layer=1)
            result['CH019_via_bridge_geometrically_proposed'] = path is not None
            if path is not None:
                result['bridge_waypoints'] = path
                add_mesh_path(board, path, net, layers)
                return True
            return False

        operations = ((bridge_ch019, connect_ch024) if ordering == 'bridge-first'
                      else (connect_ch024, bridge_ch019))
        for fn in operations:
            if not fn():
                result['status'] = 'upper_bound_geometry_blocked'
                return result
        result['status'] = 'upper_bound_geometrically_proposed_but_unrestored'
        return result
    finally:
        current_vcm = [(t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()))
                       for t in board.GetTracks() if t.GetNetname() == 'VCM']
        current_ch018 = [(t.m_Uuid.AsString(), xy(t.GetStart()), xy(t.GetEnd()))
                         for t in board.GetTracks() if t.GetNetname() == 'CH018_N_MUX']
        if current_vcm != original_vcm or current_ch018 != original_ch018:
            raise RuntimeError('Immutable analog net geometry was altered')
        for t in chosen:
            board.Add(t)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ordering', choices=('bridge-first', 'ch024-first'), required=True)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Use a new JSON report')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Output within repo forbidden')
    parts = frozen_archive(args.archive)
    if digest(parts[PCB]) != FROZEN_INPUT_SHA:
        raise ValueError('Unexpected board hash')
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='ch019-local-upperbound-') as td:
        f = Path(td) / PCB
        f.write_bytes(parts[PCB])
        board = pcbnew.LoadBoard(str(f))
        try:
            obj = evaluate(board, args.ordering)
        except Exception as exc:
            obj = {**FLAGS, 'ordering': args.ordering, 'status': 'model_exception',
                   'type': type(exc).__name__, 'reason': str(exc),
                   'upper_bound_only': True, 'full_neighbor_restitution': False}
        if digest(f.read_bytes()) != FROZEN_INPUT_SHA:
            raise RuntimeError('Reference PCB bytes modified')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Frozen diagnostic ZIP changed')
    args.output.write_text(json.dumps(obj, indent=2) + '\n')
    print(obj['status'], flush=True)


if __name__ == '__main__':
    main()

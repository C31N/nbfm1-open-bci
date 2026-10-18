#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""SHA-pinned, read-only CH026_P_ELECTRODE influence on R302.1 via escape.

The mesh/DRC/neighbor-restitution gates are intentionally NOT bypassed.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import ZIP_SHA, digest, frozen_archive
from probe_ch019_trunk_return import PCB, pads
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA

SOURCE = Path(__file__).resolve().parent
R302 = (36.15, 15.6)
J223 = (43.75, 7.6)
TARGET_NET = 'CH026_P_ELECTRODE'
FLAGS: dict[str, bool] = {
    'model_only': True, 'accepted': False, 'routing_completed': False,
    'fabrication_release': False, 'independent_replay_verified': False,
    'native_qualification': False, 'manufacturing_files': False,
}


def study(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from shapely.ops import unary_union
    from route_targeted_closure import xy, routing_domain, obstacles
    from analyze_139_escape_blockers import component, protected_power

    p = {name: (pt, nc) for name, pt, nc in pads(board, 'CH022_N_ELECTRODE')}
    if set(p) != {'J2.23', 'R302.1'} or tuple(p['R302.1'][0]) != R302:
        raise ValueError('CH022_N pad identity/position differs from pinned baseline')
    if tuple(p['J2.23'][0]) != J223:
        raise ValueError('J2.23 reference pad not in expected location')
    region = routing_domain(board, .30, .25).intersection(box(12, .5, 59, 69))
    power = protected_power(board)
    net_code = p['R302.1'][1]
    local = Point(R302).buffer(3.5)
    frozen = {
        t.m_Uuid.AsString(): (t.GetNetname(), t.GetLayer(),
                             xy(t.GetStart()), xy(t.GetEnd()))
        for t in board.GetTracks()
        if t.GetNetname() in ('CH018_N_MUX','VCM')
        or (t.GetNetname() == 'CH022_N_ELECTRODE'
            and LineString([xy(t.GetStart()), xy(t.GetEnd())]).distance(Point(J223)) < .75)
    }
    other_vias = [Point(xy(t.GetPosition())) for t in board.GetTracks()
                  if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == TARGET_NET]
    other_pads = [Point(xy(pad.GetPosition())) for fp in board.GetFootprints()
                  for pad in fp.Pads() if pad.GetNetname() == TARGET_NET]
    def free() -> dict[str, Any]:
        blocked, via_blocked = obstacles(board, net_code, .15, .15, region,
                                         .60, (pcbnew.F_Cu, pcbnew.B_Cu))
        whole = region.difference(blocked[0]).buffer(-.000005)
        fcu = component(whole, R302)
        legal = (fcu.difference(unary_union([via_blocked, power.buffer(.505)]))
                 .intersection(local).buffer(-.000005))
        return {
            'R302_connected_fcu_mm2': round(fcu.area, 8),
            'local_legal_via_mm2': round(legal.area, 8),
            'nearest_legal_via_mm': (round(Point(R302).distance(legal), 8)
                                     if not legal.is_empty else None),
            'window_center_mm': list(legal.representative_point().coords[0])
                                if not legal.is_empty else None,
            'legal_window_components': len(getattr(legal,'geoms',[legal])),
        }

    source = []
    excluded = []
    for t in board.GetTracks():
        if t.GetNetname() != TARGET_NET or t.GetLayer() != pcbnew.F_Cu:
            continue
        if isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
            continue
        line = LineString([xy(t.GetStart()), xy(t.GetEnd())])
        if line.distance(Point(R302)) > 4.0:
            continue
        dpad = min((line.distance(q) for q in other_pads), default=1000.)
        dvia = min((line.distance(q) for q in other_vias), default=1000.)
        dj = line.distance(Point(J223))
        obj = {
            'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname(),
            'layer': 'F.Cu', 'from': list(xy(t.GetStart())),
            'to': list(xy(t.GetEnd())),
            'distance_R302_mm': round(line.distance(Point(R302)), 8),
            'distance_J2_23_mm': round(dj, 8),
            'distance_own_pad_mm': round(dpad, 8),
            'distance_own_via_mm': round(dvia, 8),
        }
        if dj < 6.1 or dpad < .50 or dvia < .50:
            obj['reason'] = 'protected_escape_or_neighbor_terminus'
            excluded.append(obj)
        else:
            source.append((t, obj))
    source.sort(key=lambda x: (x[1]['distance_R302_mm'], x[1]['uuid']))
    baseline = free()
    trials = []
    selected = source[:8]
    group_indices: list[tuple[int, ...]] = (
        [(i,) for i in range(len(selected))] +
        list(itertools.combinations(range(min(len(selected), 6)), 2)) +
        ([tuple(range(len(selected)))] if len(selected) > 1 else [])
    )
    for indices in group_indices:
        original = [selected[i][0] for i in indices]
        for t in original:
            board.Remove(t)
        try:
            after = free()
            trials.append({
                'removed_UUIDs': [t.m_Uuid.AsString() for t in original],
                'removed_segments': len(original), **after,
                'delta_legal_via_mm2': round(
                    after['local_legal_via_mm2'] - baseline['local_legal_via_mm2'], 8),
                'electrode_net_restituted': False, 'accepted': False,
            })
        finally:
            for t in original:
                board.Add(t)

    after_frozen = {
        t.m_Uuid.AsString(): (t.GetNetname(), t.GetLayer(),
                             xy(t.GetStart()), xy(t.GetEnd()))
        for t in board.GetTracks() if t.m_Uuid.AsString() in frozen
    }
    if after_frozen != frozen:
        raise RuntimeError('J2.23/CH018-N/VCM protected geometry changed')
    return {**FLAGS, 'baseline_sha256': FROZEN_INPUT_SHA,
            'target_net': TARGET_NET, 'protected_J2_23_copper': len(
                [x for x in frozen.values() if x[0]=='CH022_N_ELECTRODE']),
            'existing_CH026_electrode_vias': len(other_vias),
            'R302_xy': list(R302), 'J2_23_xy': list(J223),
            'baseline': baseline, 'selectable_segments': [x[1] for x in source],
            'excluded_segments': excluded, 'results': trials,
            'positive_candidates': [
                t for t in trials if t['local_legal_via_mm2'] > baseline['local_legal_via_mm2']],
            'full_neighbor_restitution': False,
            'L3_power_unchanged_by_models': True}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Unique diagnostic JSON only')
    if args.output.resolve().is_relative_to(SOURCE):
        raise ValueError('Never write inside PCB project')
    parts = frozen_archive(args.archive)
    if digest(parts[PCB]) != FROZEN_INPUT_SHA:
        raise ValueError('Pinned PCB mismatch')
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='ch026-electrode-escape-') as td:
        board_file = Path(td) / PCB
        board_file.write_bytes(parts[PCB])
        report = study(pcbnew.LoadBoard(str(board_file)))
        if digest(board_file.read_bytes()) != FROZEN_INPUT_SHA:
            raise ValueError('PCB source bytes changed during read-only study')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Pinned ZIP changed')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('CH026 electrode proximity', len(report['selectable_segments']),
          'positive', len(report['positive_candidates']), flush=True)


if __name__ == '__main__':
    main()

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
}


def model(board_path: Path, output: Path, case: str) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box
    from analyze_139_escape_blockers import protected_power
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
              'selected_segment_uuid': []}
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
    for t in chosen:
        board.Remove(t)
    try:
        def connect(net: str, required: set[str] | None = None) -> bool:
            terminals = pads(board, net)
            if required is not None and {n for n, _, _ in terminals} != required:
                raise ValueError('Unexpected ' + net + ' terminals')
            source = next((t for t in terminals if t[0] == 'R49.1'), terminals[0])
            targets = [source] + [t for t in terminals if t != source]
            for padname, coord, _ in targets[1:]:
                path = mesh_route(board, source[1], coord, source[2],
                                  layers, reserve, region)
                if path is None:
                    result['failed_net'] = net
                    result['failed_pad'] = padname
                    return False
                add_mesh_path(board, path, source[2], layers)
            return True

        if not connect('CH024_P_MUX', {'R49.1', 'U3.23', 'R305.2'}):
            result['status'] = 'ch024_geometry_blocked'
            return result
        result['ch024_three_pads_proposed'] = True

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

        # Restore all selectively removed copper objects via their original
        # individual endpoints, including CH022-N. No permanent neighbor cuts.
        for segment in chosen:
            layer = 0 if segment.GetLayer() == pcbnew.F_Cu else 2
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
        result['all_selected_segments_proposed'] = True
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
    parser.add_argument('--case', choices=tuple(CASES), required=True)
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
            output = model(work / PCB, work / 'crosslayer.json', args.case)
        except Exception as exc:
            output = {**FLAGS, 'case': args.case, 'status': 'diagnostic_exception',
                      'error_type': type(exc).__name__, 'detail': str(exc)}
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Source archive changed')
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(args.case, output['status'], flush=True)


if __name__ == '__main__':
    main()

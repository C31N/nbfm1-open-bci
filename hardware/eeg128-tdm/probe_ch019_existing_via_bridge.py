#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Guarded CH019-P return using only existing net vias as layer transitions.

Models B.Cu/F.Cu trunk links between pinned CH019 same-net vias on a
temporary SHA-pinned joint-137 board. No manufacturing outputs, never accept.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive, digest, ZIP_SHA
from probe_ch019_trunk_return import (FLAGS, PCB, pads, protected_selection)
ROOT = Path(__file__).resolve().parent
VIA_ENDS = {
    'direct': ((39.915, 45.15), (32.7, 23.4)),
    'alternate': ((43.5, 43.279999), (33.5, 24.229999)),
    'hybrid': ((39.915, 45.15), (33.5, 24.229999)),
}


def model(board_file: Path, report_file: Path, pair_name: str,
          ordering: str, layer_name: str) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box
    from analyze_139_escape_blockers import protected_power
    from audit_block1_corridor_geometry import outlines, power_copper
    from escape_mesh_505 import add_mesh_path, mesh_route
    from route_targeted_closure import routing_domain, native_fresh, xy
    from native_connectivity import regressed_nets

    result: dict[str, Any] = {**FLAGS, 'pair': pair_name, 'ordering': ordering,
                              'layer': layer_name, 'status': 'not_started'}
    board = pcbnew.LoadBoard(str(board_file))
    reference_board = pcbnew.LoadBoard(str(board_file))
    selected = protected_selection(board, 'entire_trunk')
    power = protected_power(board)
    region = routing_domain(board, .30, .25).intersection(box(12, .5, 59, 69))
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    via_coords = VIA_ENDS[pair_name]
    via_items = [t for t in board.GetTracks()
                 if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == 'CH019_P_MUX']
    if len(via_items) != 4:
        raise ValueError('Unexpected count of retained CH019-P vias')
    code = via_items[0].GetNetCode()
    for pt in via_coords:
        if not any(abs(xy(v.GetPosition())[0] - pt[0]) < .000002
                   and abs(xy(v.GetPosition())[1] - pt[1]) < .000002
                   for v in via_items):
            raise ValueError('Requested pinned CH019-P via is missing')
    result['existing_vias'] = [list(xy(v.GetPosition())) for v in via_items]
    for t in selected:
        board.Remove(t)
    try:
        def bridge() -> bool:
            layer_index = 1 if layer_name == 'B.Cu' else 0
            path = mesh_route(board, *via_coords, code, layers, power, region,
                              start_layer=layer_index, goal_layer=layer_index)
            if path is None:
                result['status'] = 'existing_via_bridge_blocked'
                return False
            add_mesh_path(board, path, code, layers)
            result['existing_via_bridge_geometrically_proposed'] = True
            result['via_bridge_waypoints'] = path
            return True

        def route_pads(net_name: str) -> bool:
            terminals = pads(board, net_name)
            if net_name == 'CH024_P_MUX':
                if {name for name, _, _ in terminals} != {'R49.1', 'U3.23', 'R305.2'}:
                    raise ValueError('Wrong CH024-P terminal identity')
                head = next(p for p in terminals if p[0] == 'R49.1')
                terminals = [head] + [p for p in terminals if p != head]
            for label, point, _ in terminals[1:]:
                path = mesh_route(board, terminals[0][1], point, terminals[0][2],
                                  layers, power, region)
                if path is None:
                    result['status'] = 'terminal_unreachable'
                    result['blocked_net'] = net_name
                    result['blocked_pad'] = label
                    return False
                add_mesh_path(board, path, terminals[0][2], layers)
            result[net_name + '_three_or_more_terminals_proposed'] = True
            return True

        operations = ([bridge, lambda: route_pads('CH024_P_MUX')]
                      if ordering == 'bridge-first' else
                      [lambda: route_pads('CH024_P_MUX'), bridge])
        for op in operations:
            if not op():
                return result
        if not route_pads('CH022_N_ELECTRODE'):
            return result

        # A geometrical bridge is not a connectivity/replay qualification.
        pcbnew.SaveBoard(str(board_file), board)
        after = native_fresh(board_file, report_file.with_suffix('.after.json'))
        before = native_fresh(report_file.parent / 'baseline' / PCB,
                              report_file.with_suffix('.before.json'))
        result['violations'] = len(after.get('violations', []))
        result['warnings'] = sum(x.get('severity') == 'warning'
                                 for x in after.get('violations', [])
                                 + after.get('unconnected_items', []))
        result['unconnected'] = len(after.get('unconnected_items', []))
        result['regressed_nets'] = regressed_nets(before, after)
        result['all_required_nets_closed_natively'] = all(
            n not in json.dumps(after.get('unconnected_items', []))
            for n in ('CH024_P_MUX', 'CH019_P_MUX', 'CH022_N_ELECTRODE'))
        observed = pcbnew.LoadBoard(str(board_file))
        p0, p1 = power_copper(reference_board), power_copper(observed)
        result['L3_power_loss_mm2'] = p0.difference(p1).area
        result['L3_power_gain_mm2'] = p1.difference(p0).area
        result['zone_outlines_unchanged'] = outlines(reference_board) == outlines(observed)
        result['status'] = 'native_audit_unaccepted'
        return result
    finally:
        for track in selected:
            board.Add(track)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pair', choices=tuple(VIA_ENDS), required=True)
    p.add_argument('--ordering', choices=('bridge-first', 'ch024-first'), required=True)
    p.add_argument('--layer', choices=('B.Cu', 'F.Cu'), default='B.Cu')
    args = p.parse_args()
    if args.output.exists() or args.output.suffix != '.json':
        raise ValueError('Only a fresh JSON output is permitted')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('No repository output allowed')
    fixture = frozen_archive(args.archive)
    with tempfile.TemporaryDirectory(prefix='ch019-existing-via-') as temp:
        work = Path(temp)
        for name, content in fixture.items():
            (work / name).write_bytes(content)
        reference = work / 'baseline'
        reference.mkdir()
        for name, content in fixture.items():
            (reference / name).write_bytes(content)
        try:
            result = model(work / PCB, work / 'model-result.json', args.pair,
                           args.ordering, args.layer)
        except (ValueError, RuntimeError) as error:
            result = {**FLAGS, 'status': 'model_exception',
                      'pair': args.pair, 'ordering': args.ordering,
                      'layer': args.layer, 'reason': str(error)}
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Source fixture changed during modeling')
    print(result['status'], flush=True)


if __name__ == '__main__':
    main()

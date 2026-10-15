#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Diagnose a complete CH018_N path; never promote the unpaired candidate."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pcbnew
from audit_block1_corridor_geometry import power_copper
from native_connectivity import regressed_nets
from route_targeted_closure import add_path, make_track, make_via, metrics, native_fresh, net_of


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('board', 'head', 'trunk', 'output-dir'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(args.board.read_bytes()).hexdigest() == 'feb5eeedd8458e05fc9a7e3756b28b63555f81da3fd8720d63857706b2a798b7'
    args.output_dir.mkdir(parents=True, exist_ok=False)
    target = args.output_dir / 'eeg128-tdm.kicad_pcb'
    for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.kicad_sch'):
        shutil.copy2(args.board.with_suffix(ext), target.with_suffix(ext))
    before = native_fresh(target, args.output_dir/'before.json')
    board = pcbnew.LoadBoard(str(target))
    original_power = power_copper(board)
    net = next(p.GetNetCode() for f in board.GetFootprints() for p in f.Pads()
               if p.GetNetname() == 'CH018_N_MUX')
    head = json.loads(args.head.read_text())['path']
    trunk = json.loads(args.trunk.read_text())['path']
    assert head[0] == [1, 38.75, 26] and head[-1] == [1, 43.6, 25.0]
    assert trunk[0] == [0, 43.6, 25] and trunk[-1] == [0, 41.135, 59.65]
    assert trunk[1][1:] == trunk[2][1:] and trunk[2][0] == 1
    make_track(board, (38.25, 26), (38.75, 26), net, .15, pcbnew.F_Cu)
    make_via(board, (38.75, 26), net, .60)
    add_path(board, head, net, .15, .60, layers=(pcbnew.F_Cu, pcbnew.In2_Cu))
    # Continue the head on L3, removing a redundant initial B.Cu-to-L3
    # transition only 0.06 mm from the original proposed escape via.
    make_track(board, (43.6, 25), tuple(trunk[2][1:]), net, .15, pcbnew.In2_Cu)
    add_path(board, trunk[2:], net, .15, .60, layers=(pcbnew.B_Cu, pcbnew.In2_Cu))
    make_via(board, (41.135, 59.65), net, .60)
    make_track(board, (41.135, 59.65), (41.135, 58.15), net, .15, pcbnew.F_Cu)
    pcbnew.SaveBoard(str(target), board)
    for ext in ('.kicad_pro', '.kicad_dru'):
        shutil.copy2(args.board.with_suffix(ext), target.with_suffix(ext))
    after = native_fresh(target, args.output_dir/'drc.json')
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir/'parity.json'), str(target)], check=True)
    parity = json.loads((args.output_dir/'parity.json').read_text())
    loss = original_power.difference(power_copper(pcbnew.LoadBoard(str(target)))).area
    result = {**metrics(after), 'net': 'CH018_N_MUX',
              'net_still_open': 'CH018_N_MUX' in {net_of(i) for i in after['unconnected_items']},
              'power_loss_mm2': loss, 'regressed_nets': regressed_nets(before, after),
              'parity_findings': len(parity.get('schematic_parity', [])),
              'pair_closed': False, 'accepted': False,
              'reason': 'Diagnostic unpaired N route; zero-power-loss gate is mandatory',
              'rejected_pcb_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'rejected_copper_retained': False}
    (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    target.unlink()
    print(json.dumps(result))


if __name__ == '__main__':
    main()

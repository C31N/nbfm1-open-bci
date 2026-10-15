#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded atomic MUX pair probes preserving filled L3 power copper.

Incomplete paths remain in memory only. Every complete pair is independently
refilled, DRC/parity checked and compared with the input L3 power polygons.
This is an engineering experiment; no manufacturing checkpoint is promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

import pcbnew
from audit_block1_corridor_geometry import power_copper
from native_connectivity import regressed_nets
from route_targeted_closure import add_path, metrics, native_fresh, net_of, search, xy


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--path-seconds', type=float, default=4)
    p.add_argument('--max-pairs', type=int, default=16)
    p.add_argument('--expected-open', type=int, default=149,
                   help='Required native airwire count of the approved input checkpoint')
    p.add_argument('--channel', type=int, action='append', default=[])
    p.add_argument('--power-margin', type=float, default=.05,
                   help='Extra reserved-plane buffer: .05 enforces .20-mm power clearance')
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    board = a.output_dir / 'eeg128-tdm.kicad_pcb'
    for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
        shutil.copy2(a.board.with_suffix(ext), board.with_suffix(ext))
    # The diagnosis schematic belongs to these unchanged footprints/net names.
    schematic = Path(__file__).parent / 'engineering/eeg128-tdm.kicad_sch'
    shutil.copy2(schematic, board.with_suffix('.kicad_sch'))
    original = board.read_bytes()
    before = native_fresh(board, a.output_dir / 'drc-initial.json')
    assert metrics(before) == {'violations': 0, 'warnings': 0, 'unconnected': a.expected_open}
    filled = board.read_bytes()
    baseline = pcbnew.LoadBoard(str(board))
    old_power = power_copper(baseline)
    pending = {net_of(item) for item in before['unconnected_items']}
    channels = sorted({int(m[1]) for n in pending
                       if (m := re.fullmatch(r'CH(\d+)_P_MUX', n))
                       and f'CH{int(m[1]):03d}_N_MUX' in pending},
                      key=lambda n: (not 17 <= n <= 32, n != 18, n))
    channels = [n for n in channels if not a.channel or n in a.channel][:a.max_pairs]
    trials = []
    accepted = None
    # Exact parameters are recorded. No repeats of the prior eight/four
    # unconstrained CH018 probes: L3 now has a hard filled-power exclusion.
    for ch in channels:
        for layer in (pcbnew.In2_Cu, pcbnew.B_Cu):
            for order in ('NP', 'PN'):
                b = pcbnew.LoadBoard(str(board))
                event = {'channel': ch, 'layers': ['F.Cu', 'In2.Cu' if layer == pcbnew.In2_Cu else 'B.Cu'],
                         'order': order, 'step_mm': .05, 'margin_mm': 12,
                         'path_seconds': a.path_seconds, 'paths': [], 'accepted': False}
                event['extra_power_margin_mm'] = a.power_margin
                routes = []
                for polarity in order:
                    name = f'CH{ch:03d}_{polarity}_MUX'
                    pads = [(f.GetReference(), pad) for f in b.GetFootprints()
                            for pad in f.Pads() if pad.GetNetname() == name]
                    sources = [pad for ref, pad in pads if ref.startswith('R')]
                    goals = [pad for ref, pad in pads if ref.startswith('U')]
                    if not sources or len(goals) != 1:
                        event['paths'].append({'net': name, 'found': False, 'reason': 'ambiguous pad anchors'})
                        break
                    goal = xy(goals[0].GetPosition())
                    # Each RC source contains two already connected resistor
                    # pads; choose its terminal closest to the MUX destination.
                    source = min(sources, key=lambda pad: math.dist(xy(pad.GetPosition()), goal))
                    start = xy(source.GetPosition())
                    path = search(b, start, goal, source.GetNetCode(), .15, .15,
                                  True, 12, step=.05, max_nodes=250000,
                                  deadline=time.monotonic()+a.path_seconds,
                                  layers=(pcbnew.F_Cu, layer), via_diameter=.60,
                                  reserved_bottom=old_power.buffer(a.power_margin)
                                  if layer == pcbnew.In2_Cu else None)
                    event['paths'].append({'net': name, 'start_mm': start, 'goal_mm': goal,
                                           'found': path is not None})
                    if path is None:
                        break
                    # A complete source-to-destination path only, never an
                    # isolated via. The second polarity sees the first copper.
                    add_path(b, path, source.GetNetCode(), .15, .60,
                             layers=(pcbnew.F_Cu, layer))
                    routes.append({'net': name, 'path': path})
                if len(routes) == 2:
                    trial = a.output_dir / f'trial-{len(trials):03d}'
                    trial.mkdir()
                    target = trial / board.name
                    for ext in ('.kicad_pro', '.kicad_dru', '.kicad_sch'):
                        shutil.copy2(board.with_suffix(ext), target.with_suffix(ext))
                    pcbnew.SaveBoard(str(target), b)
                    # SaveBoard may create a default project for a new basename.
                    # Restore the approved netclasses before native verification.
                    for ext in ('.kicad_pro', '.kicad_dru'):
                        shutil.copy2(a.board.with_suffix(ext), target.with_suffix(ext))
                    after = native_fresh(target, trial/'drc.json')
                    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity',
                                    '--severity-all', '--all-track-errors', '--format', 'json',
                                    '--output', str(trial/'parity.json'), str(target)], check=True)
                    parity = json.loads((trial/'parity.json').read_text())
                    new_power = power_copper(pcbnew.LoadBoard(str(target)))
                    loss = old_power.difference(new_power).area
                    remaining = {net_of(item) for item in after['unconnected_items']}
                    event.update(metrics(after), power_loss_mm2=loss,
                                 parity_findings=len(parity.get('schematic_parity', [])),
                                 regressed_nets=sorted(regressed_nets(before, after)))
                    event['accepted'] = (metrics(after)['violations'] == 0
                                         and metrics(after)['warnings'] == 0 and loss == 0
                                         and not parity.get('schematic_parity')
                                         and not parity['violations']
                                         and not regressed_nets(before, after)
                                         and all(r['net'] not in remaining for r in routes))
                    if event['accepted']:
                        accepted = str(target)
                        (trial/'paths.json').write_text(json.dumps(routes, indent=2)+'\n')
                    else:
                        # Retain diagnostics only; rejected PCB copper is deleted.
                        target.unlink()
                trials.append(event)
                print(json.dumps(event), flush=True)
                result = {'baseline_sha256': hashlib.sha256(original).hexdigest(),
                          'baseline_refilled_sha256': hashlib.sha256(filled).hexdigest(),
                          'channels': channels, 'trials': trials, 'accepted_board': accepted,
                          'routing_completed': False, 'fabrication_release': False}
                (a.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
                if accepted:
                    return
    assert board.read_bytes() == filled


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay two unadopted preparatory reroutes; never publish a routing checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from merge_native_closure import copper
from native_connectivity import regressed_nets
from replay_block2_source_window import MEMBERS
from replay_ch019_electrode import clean, digest, geometry
from route_targeted_closure import metrics, native_fresh

ROOT = Path(__file__).resolve().parent
RECIPE = ROOT / 'engineering/followup-2026-10-15-escapes139/preparatory-recipes.json'
RECIPE_SHA256 = 'f306fba56f4ac4f279d060aee098aa2571182e13ff5ea951701ff4a4e1811d80'
ALLOWED = {'c22': ('CH022_N_MUX', 'In2.Cu'), 'c26': ('CH026_P_ELECTRODE', 'F.Cu')}


def recipe() -> dict:
    if digest(RECIPE) != RECIPE_SHA256:
        raise ValueError('Preparatory recipe SHA-256 differs')
    data = json.loads(RECIPE.read_text())
    if (data['scope'] != 'BLOCK2_139_PREPARATORY_ESCAPES_ONLY'
            or any(data[key] is not False for key in
                   ('accepted', 'routing_completed', 'fabrication_release'))
            or set(data['cases']) != set(ALLOWED)):
        raise ValueError('Wrong preparatory scope or release flags')
    return data


def apply(board: Path, data: dict, case: str) -> None:
    """Validate the entire delta in memory before the only disk write."""
    if digest(board) != data['baseline_member_sha256'][board.name]:
        raise ValueError('Wrong baseline PCB SHA-256')
    trial = data['cases'][case]
    net, layer = ALLOWED[case]
    if trial['net'] != net or trial['accepted'] is not False or trial['unconnected'] != 139:
        raise ValueError('Wrong preparatory case')
    text = board.read_text()
    old = copper(text)
    codes = {int(c): n for c, n in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    if old.keys() & trial['additions'].keys():
        raise ValueError('Copper UUID overlaps baseline')
    for uid, change in trial['changes'].items():
        if old.get(uid) != change['before'] or text.count(change['before']) != 1:
            raise ValueError('Reviewed copper differs')
        text = text.replace(change['before'], change['after'], 1)
    text = text[:text.rfind(')')] + '\n' + '\n'.join(trial['additions'].values()) + '\n)\n'
    new = copper(text)
    for uid in set(trial['changes']) | set(trial['additions']):
        for block in (old.get(uid, ''), new.get(uid, '')):
            if block and (not block.startswith('(segment')
                          or f'(layer "{layer}")' not in block
                          or codes[int(re.search(r'\(net\s+(\d+)\)', block)[1])] != net):
                raise ValueError('Mutation outside single-net, single-layer segment scope')
    if hashlib.sha256(text.encode()).hexdigest() != trial['expected_applied_sha256']:
        raise ValueError('Applied PCB SHA-256 differs')
    board.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=sorted(ALLOWED), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--apply-only', action='store_true')
    args = parser.parse_args()
    data = recipe()
    board = args.output_dir / 'eeg128-tdm.kicad_pcb'
    if args.apply_only:
        apply(board, data, args.case)
        return
    archive = ROOT / 'engineering/block2-ch019-electrode-closed139.zip'
    if digest(archive) != data['baseline_archive_sha256']:
        raise ValueError('Wrong baseline archive SHA-256')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(MEMBERS):
            raise ValueError('Unexpected baseline archive members')
        for name in MEMBERS:
            content = bundle.read(name)
            if hashlib.sha256(content).hexdigest() != data['baseline_member_sha256'][name]:
                raise ValueError('Baseline member SHA-256 differs')
            (args.output_dir / name).write_bytes(content)
    reference = args.output_dir / 'reference'
    reference.mkdir()
    for name in MEMBERS:
        shutil.copy2(args.output_dir / name, reference / name)
    before = native_fresh(reference / board.name, args.output_dir / 'drc-before.json')
    clean(before, 139)
    # Apply exits before the zone filler/DRC starts in another process.
    subprocess.run([sys.executable, __file__, '--case', args.case,
                    '--output-dir', str(args.output_dir), '--apply-only'], check=True)
    after = native_fresh(board, args.output_dir / 'drc-after.json')
    clean(after, 139)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir / 'parity.json'), str(board)], check=True)
    clean(json.loads((args.output_dir / 'parity.json').read_text()), 139)
    if regressed_nets(before, after):
        raise ValueError('Connectivity regression')
    trial = data['cases'][args.case]
    geo = geometry(reference / board.name, board, trial)
    if digest(board) != trial['expected_pcb_sha256']:
        raise ValueError('Native PCB replay SHA-256 differs')
    result = {**metrics(after), **geo, 'case': args.case, 'kicad_version': '8.0.9',
              'diagnostic_parity_findings': 0, 'regressed_nets': [],
              'pcb_sha256': digest(board), 'preparatory_reroute_verified': True,
              'accepted': False, 'routing_progress': False,
              'routing_completed': False, 'fabrication_release': False,
              'reason': 'No airwire reduction; CH018_P_MUX and CH021_N_ELECTRODE remain open'}
    (args.output_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

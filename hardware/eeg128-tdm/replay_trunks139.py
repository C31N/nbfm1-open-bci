#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay complete, unadopted CH018-P and CH021-N trunk diagnostics from 139."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from replay_ch018_neighbors import validate_vias
from merge_native_closure import copper
from native_connectivity import regressed_nets
from replay_block2_source_window import MEMBERS, reproducible_zip
from route_targeted_closure import metrics, native_fresh, net_of
from replay_ch019_electrode import clean, geometry

ROOT = Path(__file__).resolve().parent
DIRECTORY = ROOT / 'engineering/followup-2026-10-16-trunks139'
CONFIG = {
    'p': {'recipe': 'ch018-pair-recipe.json',
          'sha256': '23f8302f7c2c87f07f511c1d4b4f4356f66874a6c2f70089332e539182fa895b',
          'scope': 'BLOCK2_CH018_PAIR_CLOSURE_138', 'count': 138,
          'closed': ['CH018_P_MUX'], 'required': {'CH018_P_MUX', 'CH018_N_MUX', 'CH017_N_MUX'},
          'vias': {'CH018_P_MUX'},
          'allowed': {'CH018_P_MUX': {'F.Cu', 'B.Cu', 'In2.Cu'}, 'CH017_N_MUX': {'In2.Cu'},
                      'MUX_S1': {'F.Cu', 'B.Cu'}, 'MUX_S2': {'F.Cu'},
                      'MUX_S3': {'F.Cu'}, 'MUX_EN': {'F.Cu'}}},
    'n': {'recipe': 'ch021-electrode-recipe.json',
          'sha256': 'ca2d944ec29a13d32a5ee84d189e6433eb898332ed7683b15276164f231764d7',
          'scope': 'BLOCK2_CH021_ELECTRODE_CLOSURE_138', 'count': 138,
          'closed': ['CH021_N_ELECTRODE'],
          'required': {'CH021_N_ELECTRODE', 'CH017_N_MUX', 'CH023_N_ELECTRODE', 'CH027_P_ELECTRODE'},
          'vias': {'CH021_N_ELECTRODE', 'CH023_N_ELECTRODE'},
          'allowed': {'CH021_N_ELECTRODE': {'F.Cu', 'B.Cu', 'In2.Cu'},
                      'CH023_N_ELECTRODE': {'F.Cu', 'B.Cu', 'In2.Cu'},
                      'CH027_P_ELECTRODE': {'F.Cu'}, 'CH017_N_MUX': {'In2.Cu'}}},
}
CONFIG['joint'] = {
    'recipe': 'joint-trunks-recipe.json',
    'sha256': '9dc9d6f7227767c0f502a3edcf594531c0e96062987a684a9520a74e5aa1be5a',
    'scope': 'BLOCK2_JOINT_TRUNKS_CLOSURE_137', 'count': 137,
    'closed': CONFIG['p']['closed'] + CONFIG['n']['closed'],
    'required': CONFIG['p']['required'] | CONFIG['n']['required'],
    'vias': CONFIG['p']['vias'] | CONFIG['n']['vias'],
    'allowed': CONFIG['p']['allowed'] | CONFIG['n']['allowed'] | {'CH017_N_MUX': {'B.Cu', 'In2.Cu'}},
    'removed_vias': {'21548a14-551d-4062-8b9f-c24eb62ac5f8'},
}
Report = dict[str, Any]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(case: str = 'p') -> Report:
    config = CONFIG[case]
    source = DIRECTORY / config['recipe']
    if digest(source) != config['sha256']:
        raise ValueError('Reviewed recipe SHA-256 differs')
    data = json.loads(source.read_text())
    if (data['scope'] != CONFIG[case]['scope']
            or data['accepted'] is not False
            or data['routing_completed'] is not False
            or data['fabrication_release'] is not False):
        raise ValueError('Wrong scope or release flags')
    return data


def apply(board: Path, data: Report, case: str = 'p') -> None:
    config = CONFIG[case]
    allowed = config['allowed']
    if (data['scope'] != CONFIG[case]['scope']
            or any(data[k] is not False for k in ('accepted', 'routing_completed', 'fabrication_release'))):
        raise ValueError('Diagnostic scope or release flags changed')
    if digest(board) != data['baseline_member_sha256'][board.name]:
        raise ValueError('Wrong baseline PCB SHA-256')
    text = board.read_text()
    old = copper(text)
    codes = {int(code): name for code, name in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    for uid, change in data['changes'].items():
        if old.get(uid) != change['before'] or text.count(change['before']) != 1:
            raise ValueError('Exact reviewed baseline copper differs')
        text = text.replace(change['before'], change['after'], 1)
    if old.keys() & data['additions'].keys():
        raise ValueError('New copper UUID overlaps baseline')
    text = text[:text.rfind(')')] + '\n' + '\n'.join(data['additions'].values()) + '\n)\n'
    new = copper(text)
    reviewed = set(data['changes']) | set(data['additions'])
    for uid in reviewed:
        for block in (old.get(uid, ''), new.get(uid, '')):
            if block:
                net = int(re.search(r'\(net\s+(\d+)\)', block)[1])
                if codes[net] not in allowed:
                    raise ValueError('Mutation outside the reviewed neighbor scope')
                if block.startswith('(segment'):
                    if re.search(r'\(layer\s+"([^"]+)"\)', block)[1] not in allowed[codes[net]]:
                        raise ValueError('Mutation outside the reviewed layers')
                elif not block.startswith('(via') or (codes[net] not in config['vias']
                        and not (uid in config.get('removed_vias', set()) and uid not in new)):
                    raise ValueError('Unreviewed via or copper mutation')
    validate_vias(new, reviewed)
    if hashlib.sha256(text.encode()).hexdigest() != data['expected_applied_sha256']:
        raise ValueError('Applied PCB SHA-256 differs')
    board.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=sorted(CONFIG), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--apply-only', action='store_true')
    args = parser.parse_args()
    data = recipe(args.case)
    config = CONFIG[args.case]
    board = args.output_dir / 'eeg128-tdm.kicad_pcb'
    if args.apply_only:
        apply(board, data, args.case)
        return
    archive = ROOT / 'engineering/block2-ch019-electrode-closed139.zip'
    if digest(archive) != data['baseline_archive_sha256']:
        raise ValueError('Wrong baseline archive SHA-256')
    # Same lock as the additions-only replay chain; the mutation child skips it.
    replay_lock = (Path(tempfile.gettempdir()) / 'eeg128-native-replay.lock').open('a+b')
    if sys.platform == 'win32':
        import msvcrt
        if replay_lock.tell() == 0:
            replay_lock.write(b'0')
            replay_lock.flush()
        replay_lock.seek(0)
        msvcrt.locking(replay_lock.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(replay_lock, fcntl.LOCK_EX)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(MEMBERS):
            raise ValueError('Unexpected archive members')
        for name in MEMBERS:
            content = bundle.read(name)
            if hashlib.sha256(content).hexdigest() != data['baseline_member_sha256'][name]:
                raise ValueError('Baseline project member SHA-256 differs')
            (args.output_dir / name).write_bytes(content)
    reference = args.output_dir / 'reference'
    reference.mkdir()
    for name in MEMBERS:
        shutil.copy2(args.output_dir / name, reference / name)
    before = native_fresh(reference / board.name, args.output_dir / 'drc-before.json')
    clean(before, 139)
    shutil.copy2(ROOT / 'engineering/eeg128-tdm.kicad_sch', board.with_suffix('.kicad_sch'))
    subprocess.run([sys.executable, __file__, '--case', args.case, '--output-dir', str(args.output_dir),
                    '--apply-only'], check=True)
    after = native_fresh(board, args.output_dir / 'drc-after.json')
    clean(after, config['count'])
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir / 'parity.json'), str(board)], check=True)
    parity = json.loads((args.output_dir / 'parity.json').read_text())
    clean(parity, config['count'])
    if regressed_nets(before, after) or config['required'] & {net_of(item) for item in after['unconnected_items']}:
        raise ValueError('Connectivity regression or required closed net remains open')
    geo = geometry(reference / board.name, board, data)
    if digest(board) != data['expected_pcb_sha256']:
        raise ValueError('Native PCB replay differs from reviewed SHA-256')
    staging = args.output_dir / 'candidate.staging.zip'
    reproducible_zip(args.output_dir, staging)
    if digest(staging) != data['expected_archive_sha256']:
        staging.unlink()
        raise ValueError('Archive replay SHA-256 differs')
    staging.replace(args.output_dir / 'candidate.zip')
    result = {**metrics(after), **geo, 'diagnostic_parity_findings': 0,
              'case': args.case, 'closed_nets': config['closed'], 'regressed_nets': [],
              'kicad_version': '8.0.9', 'pcb_sha256': digest(board),
              'archive_sha256': data['expected_archive_sha256'],
              'routing_completed': False, 'fabrication_release': False, 'accepted': False}
    (args.output_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

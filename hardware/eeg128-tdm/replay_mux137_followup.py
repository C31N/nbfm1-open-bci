#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay complete F.Cu-only S0/CH025 preparatory reroutes on diagnostic 137."""
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
DIRECTORY = ROOT / 'engineering/followup-2026-10-16-mux137'
CONFIG = {
    's0': {'recipe': 's0-recipe.json',
           'sha256': '2f7026c0a1ce6df0054cbcb4551442abea52f52b8f4e2b9e70d92d25d675cae3',
           'scope': 'BLOCK2_MUX137_PREPARATION_S0', 'count': 137, 'closed': [],
           'required': {'MUX_S0', 'CH018_P_MUX', 'CH021_N_ELECTRODE'}, 'vias': set(),
           'allowed': {'MUX_S0': {'F.Cu'}}},
    'p25': {'recipe': 'p25-recipe.json',
            'sha256': '3a019822edfd42c0714414865277df25df02c83fa937a7544460e2b10fa06624',
            'scope': 'BLOCK2_MUX137_PREPARATION_P25', 'count': 137, 'closed': [],
            'required': {'CH025_P_MUX', 'CH018_P_MUX', 'CH021_N_ELECTRODE'}, 'vias': set(),
            'allowed': {'CH025_P_MUX': {'F.Cu'}}},
}
CONFIG['joint'] = {
    'recipe': 'joint-recipe.json', 'sha256': 'a6c5e5c9d42e397391a8bb6059023dac856089eb4738d62eb8d51a13f2ec4c8c',
    'scope': 'BLOCK2_MUX137_PREPARATION_JOINT', 'count': 137, 'closed': [],
    'required': CONFIG['s0']['required'] | CONFIG['p25']['required'], 'vias': set(),
    'allowed': CONFIG['s0']['allowed'] | CONFIG['p25']['allowed'],
}
Report = dict[str, Any]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(case: str = 's0') -> Report:
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


def apply(board: Path, data: Report, case: str = 's0') -> None:
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
    archive = ROOT / 'engineering/followup-2026-10-16-trunks139/joint-trunks-closed137.zip'
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
    clean(before, 137)
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

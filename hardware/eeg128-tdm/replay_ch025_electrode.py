#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay the immutable 141→140 CH025 electrode closure and CH026-P neck replacement; never export fabrication data."""
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

ROOT = Path(__file__).resolve().parent
RECIPE = ROOT / 'engineering/followup-2026-10-15-power-safe140/ch025e140-recipe.json'
RECIPE_SHA256 = '3664442c29de2df49d1f1e69b371aa519a6ddbb557eef1b5096df89a41722af1'
ALLOWED = {'CH025_P_ELECTRODE', 'CH026_P_ELECTRODE'}
Report = dict[str, Any]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe() -> Report:
    if digest(RECIPE) != RECIPE_SHA256:
        raise ValueError('Reviewed recipe SHA-256 differs')
    data = json.loads(RECIPE.read_text())
    if (data['scope'] != 'BLOCK2_CH025_ELECTRODE_C26_REPLACEMENT_140'
            or data['routing_completed'] is not False
            or data['fabrication_release'] is not False):
        raise ValueError('Wrong scope or release flags')
    return data


def apply(board: Path, data: Report) -> None:
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
                if codes[net] not in ALLOWED or (block.startswith('(segment') and not re.search(
                        r'\(layer\s+"(?:F|B|In2)\.Cu"\)', block)):
                    raise ValueError('Mutation outside the reviewed neighbor scope')
    validate_vias(new, reviewed)
    if hashlib.sha256(text.encode()).hexdigest() != data['expected_applied_sha256']:
        raise ValueError('Applied PCB SHA-256 differs')
    board.write_text(text)


def geometry(baseline: Path, candidate: Path, data: Report) -> Report:
    import pcbnew
    from audit_block1_corridor_geometry import outlines, power_copper
    from verify_hardware_identity import balanced_blocks

    old_text, new_text = baseline.read_text(), candidate.read_text()
    old, new = copper(old_text), copper(new_text)
    expected = dict(old)
    for uid, change in data['changes'].items():
        expected.pop(uid)
        if change['after']:
            expected[uid] = change['after']
    expected.update(data['additions'])
    norm = lambda value: re.sub(r'\s+', '', value)
    exact = {uid: norm(value) for uid, value in expected.items()} == {
        uid: norm(value) for uid, value in new.items()}
    footprints = sorted(map(norm, balanced_blocks(old_text, 'footprint'))) == sorted(
        map(norm, balanced_blocks(new_text, 'footprint')))
    before, after = pcbnew.LoadBoard(str(baseline)), pcbnew.LoadBoard(str(candidate))
    p0, p1 = power_copper(before), power_copper(after)
    result = {'exact_reviewed_copper': exact, 'footprints_unchanged': footprints,
              'zone_outlines_unchanged': outlines(before) == outlines(after),
              'project_rules_unchanged': all(baseline.with_suffix(ext).read_bytes()
                                           == candidate.with_suffix(ext).read_bytes()
                                           for ext in ('.kicad_pro', '.kicad_dru')),
              'L3_power_loss_mm2': p0.difference(p1).area,
              'L3_power_gain_mm2': p1.difference(p0).area}
    if not all(result[key] for key in ('exact_reviewed_copper', 'footprints_unchanged',
                                      'zone_outlines_unchanged', 'project_rules_unchanged')):
        raise ValueError('Protected geometry changed')
    if result['L3_power_loss_mm2'] != 0.0 or result['L3_power_gain_mm2'] != 0.0:
        raise ValueError('Filled L3 power changed; no numerical tolerance is permitted')
    return result


def clean(report: Report, count: int) -> None:
    if (report.get('kicad_version') != '8.0.9' or report.get('schematic_parity')
            or metrics(report) != {'violations': 0, 'warnings': 0, 'unconnected': count}):
        raise ValueError('Native KiCad 8.0.9 gate failed')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--apply-only', action='store_true')
    args = parser.parse_args()
    data = recipe()
    board = args.output_dir / 'eeg128-tdm.kicad_pcb'
    if args.apply_only:
        apply(board, data)
        return
    archive = ROOT / 'engineering/block2-ch029-electrode-closed141.zip'
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
    clean(before, 141)
    shutil.copy2(ROOT / 'engineering/eeg128-tdm.kicad_sch', board.with_suffix('.kicad_sch'))
    subprocess.run([sys.executable, __file__, '--output-dir', str(args.output_dir),
                    '--apply-only'], check=True)
    after = native_fresh(board, args.output_dir / 'drc-after.json')
    clean(after, 140)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir / 'parity.json'), str(board)], check=True)
    parity = json.loads((args.output_dir / 'parity.json').read_text())
    clean(parity, 140)
    if regressed_nets(before, after) or 'CH025_P_ELECTRODE' in {net_of(item) for item in after['unconnected_items']}:
        raise ValueError('Connectivity regression or CH025 electrode remains open')
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
              'closed_nets': ['CH025_P_ELECTRODE'], 'regressed_nets': [],
              'kicad_version': '8.0.9', 'pcb_sha256': digest(board),
              'archive_sha256': data['expected_archive_sha256'],
              'routing_completed': False, 'fabrication_release': False, 'accepted': True}
    (args.output_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

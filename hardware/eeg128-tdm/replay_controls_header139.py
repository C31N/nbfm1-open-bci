#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay two unadopted, complete neighbor restorations on the fixed 139 baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from shapely.geometry import box
from merge_native_closure import copper
from native_connectivity import regressed_nets
from replay_block2_source_window import MEMBERS, reproducible_zip
from replay_ch018_neighbors import validate_vias
from replay_ch019_electrode import clean, geometry
from route_targeted_closure import native_fresh

ROOT = Path(__file__).resolve().parent
RECIPE = ROOT / 'engineering/followup-2026-10-16-controls-header139/recipes.json'
RECIPE_SHA256 = '69aab409827453c17b0b20cdd3b904338bb269d75c73e91c256b194d32469503'
ALLOWED = {
    'controls': {'MUX_S1': {'F.Cu', 'B.Cu'}, 'MUX_S2': {'F.Cu'},
                 'MUX_S3': {'F.Cu'}, 'MUX_EN': {'F.Cu'}},
    'header': {'CH027_P_ELECTRODE': {'F.Cu'},
               'CH023_N_ELECTRODE': {'F.Cu', 'B.Cu', 'In2.Cu'}},
}
Report = dict[str, Any]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe() -> Report:
    if digest(RECIPE) != RECIPE_SHA256:
        raise ValueError('Reviewed round-2 recipe differs')
    data = json.loads(RECIPE.read_text())
    if (data['scope'] != 'BLOCK2_CONTROLS_HEADER_DIAGNOSTICS_139'
            or set(data['cases']) != set(ALLOWED)
            or any(data[k] is not False for k in ('accepted', 'routing_completed', 'fabrication_release'))):
        raise ValueError('Wrong diagnostic scope or release flags')
    return data


def apply(board: Path, data: Report, case: str) -> None:
    if digest(board) != data['baseline_member_sha256'][board.name]:
        raise ValueError('Wrong immutable 139 PCB')
    trial = data['cases'][case]
    if trial['accepted'] is not False:
        raise ValueError('Diagnostic cannot become an accepted checkpoint')
    text = board.read_text()
    old = copper(text)
    names = {int(n): value for n, value in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    if old.keys() & trial['additions'].keys():
        raise ValueError('Copper UUID collision')
    for uid, change in trial['changes'].items():
        if old.get(uid) != change['before'] or text.count(change['before']) != 1:
            raise ValueError('Exact reviewed copper differs')
        text = text.replace(change['before'], change['after'], 1)
    text = text[:text.rfind(')')] + '\n' + '\n'.join(trial['additions'].values()) + '\n)\n'
    new = copper(text)
    reviewed = set(trial['changes']) | set(trial['additions'])
    for uid in reviewed:
        for block in (old.get(uid, ''), new.get(uid, '')):
            if not block:
                continue
            name = names[int(re.search(r'\(net\s+(\d+)\)', block)[1])]
            if name not in ALLOWED[case]:
                raise ValueError('Mutation outside reviewed neighbor nets')
            if block.startswith('(segment'):
                if re.search(r'\(layer\s+"([^"]+)"\)', block)[1] not in ALLOWED[case][name]:
                    raise ValueError('Mutation outside reviewed layers')
            elif block.startswith('(via'):
                if case != 'header' or name != 'CH023_N_ELECTRODE':
                    raise ValueError('Unreviewed via mutation')
            else:
                raise ValueError('Unsupported copper mutation')
    validate_vias(new, reviewed)
    if hashlib.sha256(text.encode()).hexdigest() != trial['expected_applied_sha256']:
        raise ValueError('Applied round-2 PCB differs')
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
        raise ValueError('Wrong baseline ZIP')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(MEMBERS):
            raise ValueError('Wrong archive members')
        for name in MEMBERS:
            content = bundle.read(name)
            if hashlib.sha256(content).hexdigest() != data['baseline_member_sha256'][name]:
                raise ValueError('Wrong baseline member')
            (args.output_dir / name).write_bytes(content)
    reference = args.output_dir / 'reference'
    reference.mkdir()
    for name in MEMBERS:
        shutil.copy2(args.output_dir / name, reference / name)
    before = native_fresh(reference / board.name, args.output_dir / 'drc-before.json')
    clean(before, 139)
    subprocess.run([sys.executable, __file__, '--case', args.case, '--output-dir',
                    str(args.output_dir), '--apply-only'], check=True)
    after = native_fresh(board, args.output_dir / 'drc-after.json')
    clean(after, 139)
    shutil.copy2(ROOT / 'engineering/eeg128-tdm.kicad_sch', board.with_suffix('.kicad_sch'))
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir / 'parity.json'), str(board)], check=True)
    clean(json.loads((args.output_dir / 'parity.json').read_text()), 139)
    if regressed_nets(before, after):
        raise ValueError('Neighbor net regressed')
    trial = data['cases'][args.case]
    geo = geometry(reference / board.name, board, trial)
    if digest(board) != trial['expected_pcb_sha256']:
        raise ValueError('Native PCB hash differs')
    reproducible_zip(args.output_dir, args.output_dir / 'diagnostic.zip')
    if digest(args.output_dir / 'diagnostic.zip') != trial['expected_archive_sha256']:
        raise ValueError('Native ZIP hash differs')
    import pcbnew
    from analyze_139_escape_blockers import windows, protected_power
    b = pcbnew.LoadBoard(str(board))
    netname, point, region = ('CH018_P_MUX', (41.135, 45.15), box(12, 20, 59, 69)) if args.case == 'controls' else (
        'CH021_N_ELECTRODE', (43.25, 7.6), box(25, .5, 57, 35.9))
    net = next(p.GetNetCode() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == netname)
    _, window = windows(b, net, point, region, protected_power(b))
    if window['legal_via_area_mm2'] <= 0:
        raise ValueError('No modeled target via window after full restitution')
    result = {**geo, 'case': args.case, 'violations': 0, 'warnings': 0, 'unconnected': 139,
              'diagnostic_parity_findings': 0, 'regressed_nets': [], 'diagnostic_verified': True,
              'accepted': False, 'routing_completed': False, 'fabrication_release': False,
              'target_window_model': window, 'pcb_sha256': digest(board),
              'archive_sha256': trial['expected_archive_sha256']}
    (args.output_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

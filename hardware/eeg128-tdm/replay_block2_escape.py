#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay the guarded Block-2 BANK escape without promoting the PCB."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from merge_native_closure import copper
from native_connectivity import regressed_nets
from run_native_closure import verify

MEMBERS = tuple('eeg128-tdm' + ext for ext in
                ('.kicad_pcb', '.kicad_pro', '.kicad_dru'))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(report: dict, expected_open: int) -> None:
    if (report['kicad_version'] != '8.0.9' or report['violations']
            or report.get('schematic_parity')
            or len(report['unconnected_items']) != expected_open
            or any(item['severity'] == 'warning' for item in
                   report['unconnected_items'])):
        raise ValueError('Native DRC or open-connection count differs')


def apply_recipe(board: Path, recipe: dict) -> None:
    text = board.read_text()
    if recipe['scope'] != 'BLOCK2_BANK_ESCAPE':
        raise ValueError('Unexpected copper recipe scope')
    codes = {name: int(code) for code, name in
             re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    bank = codes['BANK1_P_MUX_OUT']
    items = copper(text)
    changes = recipe['changes']
    if (len(changes) != 12 or sum(c['before'] is not None for c in changes) != 3
            or sum(c['after'] is not None for c in changes) != 9):
        raise ValueError('Expected exactly three removals and nine additions')
    if len({c['uuid'] for c in changes}) != len(changes):
        raise ValueError('Duplicate copper UUID')
    for change in changes:
        uuid, old, new = change['uuid'], change['before'], change['after']
        if change['net'] != 'BANK1_P_MUX_OUT':
            raise ValueError('Copper change reaches outside the BANK net')
        for block in (old, new):
            if block is not None and not re.search(r'\(net\s+' + str(bank) + r'\)', block):
                raise ValueError('Copper net code differs from BANK net')
        if old is not None:
            if new is not None or items.get(uuid) != old or text.count(old) != 1:
                raise ValueError('Removed copper differs from the exact baseline')
            text = text.replace(old, '', 1)
        else:
            if new is None or uuid in items or list(copper('(kicad_pcb\n' + new + '\n)')) != [uuid]:
                raise ValueError('Invalid added copper')
            end = text.rfind(')')
            text = text[:end] + '\n' + new + '\n' + text[end:]
    copper(text)
    board.write_text(text)


def reproducible_zip(folder: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as bundle:
        for name in MEMBERS:
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, (folder / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-zip', required=True, type=Path)
    parser.add_argument('--recipe', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.baseline_zip) as bundle:
        if sorted(bundle.namelist()) != sorted(MEMBERS):
            raise ValueError('Archive members differ from the three project files')
        for name in MEMBERS:
            target = output / name
            target.write_bytes(bundle.read(name))
            expected = recipe['baseline_sha256'][target.suffix]
            if digest(target) != expected:
                raise ValueError(f'Archive member hash differs: {name}')
    board = output / MEMBERS[0]
    before = verify(board, output / 'drc-before.json')
    clean(before, recipe['before_unconnected'])
    apply_recipe(board, recipe)
    after = verify(board, output / 'drc-after.json')
    clean(after, recipe['after_unconnected'])
    if regressed_nets(before, after):
        raise ValueError('Previously closed net reopened, including power')
    if digest(board) != recipe['expected_pcb_sha256']:
        raise ValueError('Replay PCB is not byte-identical')
    for name in MEMBERS[1:]:
        if digest(output / name) != recipe['baseline_sha256'][(output / name).suffix]:
            raise ValueError('Project rules changed')
    archive = output / 'block2-bank-escape-candidate.zip'
    reproducible_zip(output, archive)
    result = {'kicad_version': after['kicad_version'], 'violations': 0,
              'warnings': 0, 'unconnected': len(after['unconnected_items']),
              'power_regressions': [], 'pcb_sha256': digest(board),
              'archive_sha256': digest(archive), 'routing_completed': False,
              'fabrication_release': False, 'engineering_candidate_only': True}
    (output / 'block2-escape-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

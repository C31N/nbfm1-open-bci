#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay the exact Block-2 VCM source-window correction without PCB promotion."""
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
    """Permit only the two exact VCM replacements and the short B.Cu link."""
    text = board.read_text()
    if (recipe['scope'] != 'BLOCK2_VCM_SOURCE_WINDOW'
            or digest(board) != 'c8fefc8f70b4ae8adeb107a7389422b7f28737f20cbfa9aac6516a12d1446acb'):
        raise ValueError('Wrong scope or baseline PCB')
    codes = {name: int(code) for code, name in
             re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    net = codes['VCM']; items = copper(text); changes = recipe['changes']
    known = {'41740aec-2de4-45bb-a3ff-e00fa3601d22',
             '25bcfc5d-4e99-4b3e-b0be-65d0bd2559f8'}
    if (len(changes) != 3 or len({c['uuid'] for c in changes}) != 3
            or {c['uuid'] for c in changes if c['before'] is not None} != known):
        raise ValueError('Expected exactly the two VCM objects and one new link')
    for c in changes:
        uid, old, new = c['uuid'], c['before'], c['after']
        if c['net'] != 'VCM' or new is None or list(copper('(kicad_pcb\n'+new+'\n)')) != [uid]:
            raise ValueError('Only VCM copper is allowed')
        if not re.search(r'\(net\s+'+str(net)+r'\)',new):
            raise ValueError('VCM net code differs')
        if old is not None:
            if items.get(uid) != old or text.count(old) != 1:
                raise ValueError('Exact original VCM copper differs')
            token = '(at 39.45 26)' if old.startswith('(via') else '(end 39.45 26)'
            updated = '(at 39.65 26)' if old.startswith('(via') else '(end 39.65 26)'
            if old.count(token) != 1 or new != old.replace(token,updated):
                raise ValueError('Only the 0.20-mm VCM endpoint shift is allowed')
            text = text.replace(old,new,1)
        else:
            if uid in items or not new.startswith('(segment'):
                raise ValueError('Invalid new VCM link')
            for token in ('(start 39.65 26)','(end 39.45 26)',
                          '(width 0.25)','(layer "B.Cu")'):
                if token not in new: raise ValueError('VCM link geometry differs')
            end = text.rfind(')'); text = text[:end]+'\n'+new+'\n'+text[end:]
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
    if digest(args.baseline_zip) != recipe['baseline_archive_sha256']:
        raise ValueError('Wrong BANK-escape baseline archive')
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
    archive = output / 'block2-vcm-source-candidate.zip'
    reproducible_zip(output, archive)
    result = {'kicad_version': after['kicad_version'], 'violations': 0,
              'warnings': 0, 'unconnected': len(after['unconnected_items']),
              'power_regressions': [], 'pcb_sha256': digest(board),
              'archive_sha256': digest(archive), 'routing_completed': False,
              'fabrication_release': False, 'engineering_candidate_only': True}
    (output / 'block2-vcm-source-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Replay a hash-bound engineering copper recipe with separate native checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from merge_native_closure import copper
from run_native_closure import verify


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def airwires(report: dict[str, Any]) -> Counter[str]:
    result: Counter[str] = Counter()
    for item in report['unconnected_items']:
        names = {match[1] for end in item['items']
                 if (match := re.search(r'\[([^]]+)\]', end['description']))}
        if len(names) != 1:
            raise ValueError('Ambiguous native airwire net')
        result.update(names)
    return result


def validate_vcm_corridor(recipe: dict[str, Any], text: str) -> bool:
    """Permit only the two identified Block-1 reference-trunk replacements."""
    if recipe.get('scope') != 'MUX_BLOCK1_VCM_CORRIDOR':
        return False
    expected = {
        'a8dda715-232a-456c-b468-7e3e59eebf03': (11.75, 36.4, 188.75, 36.4),
        '6424b39b-49e9-4ee8-b7e5-8ee59047cfc2': (11.75, 36.4, 27.75, 36.4),
    }
    codes = {name: int(code) for code, name in
             re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    removed = set()
    seen = set()
    added_reference = 0
    for item in recipe['changes']:
        if item['uuid'] in seen:
            raise ValueError('VCM corridor recipe contains a duplicate UUID')
        seen.add(item['uuid'])
        name, old, new = item['net'], item['before'], item['after']
        if name != 'VCM' and not re.fullmatch(r'CH(?:00\d|01[0-5])_[PN]_MUX', name):
            raise ValueError('VCM corridor recipe contains an out-of-block net')
        for block in (old, new):
            if block is not None and not re.search(r'\(net\s+' + str(codes[name]) + r'\)', block):
                raise ValueError('VCM corridor copper net differs from its declared net')
        if old is not None:
            if name != 'VCM' or new is not None or item['uuid'] not in expected:
                raise ValueError('VCM corridor may remove only its two original trunks')
            points = tuple(float(v) for pair in re.findall(
                r'\((?:start|end)\s+([-\d.]+)\s+([-\d.]+)\)', old) for v in pair)
            if points != expected[item['uuid']]:
                raise ValueError('VCM corridor baseline trunk geometry differs')
            removed.add(item['uuid'])
        if name == 'VCM':
            if any(block is not None and (not block.lstrip().startswith('(segment')
                    or '(layer "B.Cu")' not in block or '(width 0.25)' not in block)
                   for block in (old, new)):
                raise ValueError('VCM replacement must preserve B.Cu and 0.25 mm width')
            added_reference += new is not None
        elif old is not None or new is None:
            raise ValueError('Block-1 signal changes must be additive')
    if removed != set(expected) or not added_reference:
        raise ValueError('VCM corridor requires both trunks and a replacement path')
    return True


def validate_left_vcm_escape(recipe: dict[str, Any], text: str) -> bool:
    """Allow the exact 174-checkpoint reference replacement and local escapes."""
    if recipe.get('scope') != 'MUX_BLOCK1_LEFT_VCM_ESCAPE':
        return False
    baseline = '69927dc28b099641f3ae1a92c37bb91e247ca80d0ff595bb78ea5f3df7ce1124'
    if (hashlib.sha256(text.encode()).hexdigest() != baseline
            or recipe['baseline_sha256']['.kicad_pcb'] != baseline):
        raise ValueError('Left VCM escape requires the exact verified 174 PCB')
    codes = {name: int(code) for code, name in
             re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', text)}
    expected = set()
    for uuid, block in copper(text).items():
        if not (block.startswith('(segment') and '(layer "B.Cu")' in block
                and re.search(r'\(net\s+' + str(codes['VCM']) + r'\)', block)):
            continue
        points = [tuple(map(float, pair)) for pair in re.findall(
            r'\((?:start|end)\s+([-\d.]+)\s+([-\d.]+)\)', block)]
        column = (len(points) == 2 and points[0][0] == points[1][0]
                  and points[0][0] in (11.75, 16.45, 22.25)
                  and points[0][1] in (13, 15.6, 18.2, 20.8, 23.4, 26, 28.6, 31.2)
                  and points[1][1] == 36.4 and '(width 0.2)' in block)
        trunk = (set(points) in ({(11.75, 36.4), (24.8, 36.4)},
                                {(24.8, 36.4), (24.8, 33)})
                 and '(width 0.25)' in block)
        if column or trunk:
            expected.add(uuid)
    if len(expected) != 26:
        raise ValueError('Left VCM baseline must contain its 26 identified segments')
    seen, removed = set(), set()
    added_reference = 0
    for item in recipe['changes']:
        uuid, name, old, new = (item[key] for key in ('uuid', 'net', 'before', 'after'))
        if uuid in seen:
            raise ValueError('Left VCM recipe contains a duplicate UUID')
        seen.add(uuid)
        if name != 'VCM' and not re.fullmatch(r'CH(?:00\d|01[0-5])_[PN]_(?:MUX|ELECTRODE)', name):
            raise ValueError('Left VCM escape contains an out-of-block net')
        for block in (old, new):
            if block is not None and not re.search(r'\(net\s+' + str(codes[name]) + r'\)', block):
                raise ValueError('Left VCM copper net differs from its declared net')
        if old is not None:
            if name != 'VCM' or new is not None or uuid not in expected:
                raise ValueError('Left VCM may remove only its 26 original segments')
            removed.add(uuid)
        if new is None:
            continue
        if list(copper('(kicad_pcb\n' + new + '\n)')) != [uuid]:
            raise ValueError('Invalid left VCM copper block')
        points = [tuple(map(float, pair)) for pair in re.findall(
            r'\((?:start|end|at)\s+([-\d.]+)\s+([-\d.]+)\)', new)]
        if not points or any(not (5.0 <= x <= 40.0 and 5.0 <= y <= 65.0) for x, y in points):
            raise ValueError('Left VCM escape copper leaves Block 1')
        if name == 'VCM':
            if not (new.startswith('(segment') and '(layer "B.Cu")' in new
                    and re.search(r'\(width 0\.(?:2|25)\)', new)):
                raise ValueError('VCM replacement requires 0.20/0.25 mm B.Cu segments')
            added_reference += 1
        elif new.startswith('(via'):
            if not all(token in new for token in ('(size 0.6)', '(drill 0.3)', '(layers "F.Cu" "B.Cu")')):
                raise ValueError('Block-1 signal vias require 0.60/0.30 mm F.Cu/B.Cu geometry')
        elif new.startswith('(segment'):
            if ('(width 0.15)' not in new
                    or not re.search(r'\(layer "(?:F|B|In2)\.Cu"\)', new)):
                raise ValueError('Block-1 signal traces require 0.15 mm L1/L3/L4 geometry')
            if '(layer "In2.Cu")' in new and any(y > 36.5 for x, y in points):
                raise ValueError('L3 signal routing must remain in the upper free corridor')
        else:
            raise ValueError('Only local signal segments and through vias are allowed')
    if removed != expected or not added_reference:
        raise ValueError('Left VCM escape requires all 26 removals and a replacement')
    return True


def validate_recovery167(recipe: dict[str, Any], text: str) -> bool:
    """Rebuild only reviewed Block-1 escapes and open Block-2/3 MUX channels."""
    if recipe.get('scope') != 'RECOVERY_167_ANALOG':
        return False
    baseline = '79b30a218cf4913f67c5515e707e362799c5ef3cef080a310c24c15f8f357f68'
    if (hashlib.sha256(text.encode()).hexdigest() != baseline
            or recipe['baseline_sha256']['.kicad_pcb'] != baseline):
        raise ValueError('Recovery requires the exact verified 167 PCB')
    codes = {name:int(code) for code,name in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)',text)}
    original = copper(text)
    required = {'CH002_N_MUX','CH004_N_ELECTRODE','CH004_N_MUX','CH005_N_MUX','CH011_P_ELECTRODE'}
    allowed = set(required)
    allowed.update({'CH000_N_ELECTRODE','CH014_P_ELECTRODE','CH004_P_ELECTRODE',
                    'CH005_N_ELECTRODE','CH010_P_ELECTRODE','CH012_P_ELECTRODE',
                    'CH015_P_ELECTRODE','CH015_N_ELECTRODE'})
    allowed.update(f'CH{ch:03d}_{side}_MUX' for ch in range(16,25) for side in ('P','N'))
    allowed.update(f'CH{ch:03d}_N_MUX' for ch in (25,26,28,29,30,37,43,44))
    allowed.update(f'CH{ch:03d}_P_MUX' for ch in (36,40,41))
    allowed.update(f'CH{ch:03d}_{side}_MUX' for ch in (33,42) for side in ('P','N'))
    normalize = lambda block:re.sub(r'\s+','',block)
    seen,removed,added = set(),[],set()
    for item in recipe['changes']:
        uid,name,old,new = (item[k] for k in ('uuid','net','before','after'))
        if uid in seen or name not in allowed:
            raise ValueError('Unreviewed recovery net or duplicate UUID')
        seen.add(uid)
        if old is not None:
            if (name not in {'CH002_N_MUX','CH004_N_ELECTRODE'} or new is not None
                    or uid not in original or normalize(old) != normalize(original[uid])):
                raise ValueError('Recovery may remove only its reviewed two-net corridor')
            removed.append(uid)
        elif new is None or uid in original:
            raise ValueError('Invalid recovery addition')
        for block in (old,new):
            if block is not None and (list(copper('(kicad_pcb\n'+block+'\n)')) != [uid]
                    or not re.search(r'\(net\s+'+str(codes[name])+r'\)',block)):
                raise ValueError('Recovery copper UUID or declared net differs')
        if new is None:
            continue
        points = [tuple(map(float,q)) for q in re.findall(r'\((?:start|end|at)\s+([-\d.]+)\s+([-\d.]+)\)',new)]
        if len(points) != (1 if new.startswith('(via') else 2) or any(
                not (5<=x<=86 and 5<=y<=65) for x,y in points):
            raise ValueError('Recovery copper leaves the reviewed three-block corridor')
        if new.startswith('(via'):
            if not all(token in new for token in ('(size 0.6)','(drill 0.3)','(layers "F.Cu" "B.Cu")')):
                raise ValueError('Recovery vias require 0.60/0.30-mm through geometry')
        elif new.startswith('(segment'):
            if '(width 0.15)' not in new or not re.search(r'\(layer "(?:F|B|In2)\.Cu"\)',new):
                raise ValueError('Recovery signals require 0.15-mm L1/L3/L4 geometry')
        else:
            raise ValueError('Only tracks and through vias are permitted')
        added.add(name)
    signature = hashlib.sha256(json.dumps(sorted(removed),separators=(',',':')).encode()).hexdigest()
    if len(removed)!=283 or signature!='1aa3ddd243ba0921c2e11347eca66240c7a446c544af2caedb29b3018c513f0d':
        raise ValueError('Recovery removal set differs from its 283 reviewed items')
    if not required<=added:
        raise ValueError('Recovery requires both restored corridors and all three Block-1 closures')
    for ch in (*range(16,25),33,42):
        pair = {f'CH{ch:03d}_{s}_MUX' for s in ('P','N')}
        if added&pair and not pair<=added:
            raise ValueError('Open P/N MUX counterparts must be routed together')
    electrode_pair = {'CH015_P_ELECTRODE','CH015_N_ELECTRODE'}
    if added&electrode_pair and not electrode_pair<=added:
        raise ValueError('CH015 electrode P/N closures must be routed together')
    return True


def mutate(board: Path, recipe_path: Path) -> None:
    """Change only explicit top-level copper; leave rules and pads untouched."""
    recipe = json.loads(recipe_path.read_text())
    text = board.read_text()
    items = copper(text)
    vcm_corridor = (validate_vcm_corridor(recipe, text)
                    or validate_left_vcm_escape(recipe, text)
                    or validate_recovery167(recipe, text))
    for change in recipe['changes']:
        uuid = change['uuid']
        old, new = change['before'], change['after']
        if old is None:
            if uuid in items:
                raise ValueError(f'Added UUID already exists: {uuid}')
        elif uuid not in items or re.sub(r'\s+', '', items[uuid]) != re.sub(r'\s+', '', old):
            raise ValueError(f'Baseline copper mismatch: {uuid}')
        adc_replacement = (
            recipe.get('scope') == 'ADC6_ADC7_GEOMETRY'
            and change['net'] == 'ADC7_P'
            and all(item['net'] in {'ADC6_N', 'ADC7_P', 'ADC7_N'}
                    for item in recipe['changes'])
            and any(item['net'] == 'ADC7_P' and item['before'] is None
                    and item['after'] is not None for item in recipe['changes'])
        )
        adc6_length_replacement = (
            recipe.get('scope') == 'ADC6_LENGTH_GEOMETRY'
            and change['net'] == 'ADC6_N'
            and all(item['net'] == 'ADC6_N'
                    and all(block is None or (block.lstrip().startswith('(segment')
                            and '(layer "B.Cu")' in block)
                            for block in (item['before'], item['after']))
                    for item in recipe['changes'])
            and any(item['before'] is None and item['after'] is not None
                    for item in recipe['changes'])
        )
        adc6_via_replacement = (
            recipe.get('scope') == 'ADC6_VIA_GEOMETRY'
            and change['net'] in {'ADC6_P', 'ADC6_N'}
            and {item['net'] for item in recipe['changes']} == {'ADC6_P', 'ADC6_N'}
            and all(block is None or block.lstrip().startswith(('(segment', '(via'))
                    for item in recipe['changes'] for block in (item['before'], item['after']))
            and all(sum(item['net'] == net and item[key] is not None
                        and item[key].lstrip().startswith('(via')
                        for item in recipe['changes']) == 2
                    for net in ('ADC6_P', 'ADC6_N') for key in ('before', 'after'))
            and all('(size 0.6)' in block and '(drill 0.3)' in block
                    for item in recipe['changes'] for block in (item['before'], item['after'])
                    if block is not None and block.lstrip().startswith('(via'))
        )
        if (new is None and change['net'] != 'VREG_1V1'
                and not adc_replacement and not adc6_length_replacement
                and not adc6_via_replacement and not vcm_corridor):
            raise ValueError('Removal requires a scoped core/ADC/VCM copper replacement')
        if new is not None and list(copper('(kicad_pcb\n' + new + '\n)')) != [uuid]:
            raise ValueError(f'Invalid replacement copper block: {uuid}')
        if old is not None:
            text = text.replace(items[uuid], new or '', 1)
        else:
            end = text.rfind(')')
            text = text[:end] + '\n' + new + '\n' + text[end:]
    copper(text)  # Reject malformed or duplicate final copper.
    board.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', required=True, type=Path)
    parser.add_argument('--recipe', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    for suffix, expected in recipe['baseline_sha256'].items():
        if digest(args.board.with_suffix(suffix)) != expected:
            raise ValueError(f'Recipe requires its exact baseline {suffix}; do not apply twice')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    board = (args.output_dir / 'eeg128-tdm.kicad_pcb').resolve()
    if board.exists():
        raise ValueError('Use a new output directory; an existing checkpoint will not be overwritten')
    for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
        shutil.copy2(args.board.with_suffix(suffix), board.with_suffix(suffix))
    before = verify(board, args.output_dir / 'drc-before.json')
    if len(before['unconnected_items']) != recipe['before_unconnected']:
        raise ValueError('Baseline does not reproduce the claimed native airwire count')
    module_dir = str(Path(__file__).resolve().parent)
    child = (f'import sys;sys.path.insert(0,{module_dir!r});from pathlib import Path;'
             'from replay_copper_checkpoint import mutate;'
             f'mutate(Path({str(board)!r}),Path({str(args.recipe.resolve())!r}))')
    with (args.output_dir / 'mutation.log').open('w') as log:
        subprocess.run([sys.executable, '-c', child], check=True, stdout=log, stderr=subprocess.STDOUT)
    after = verify(board, args.output_dir / 'drc-final.json')
    if len(after['unconnected_items']) != recipe['after_unconnected']:
        raise ValueError('Replay does not reproduce the expected native checkpoint')
    old_counts, new_counts = airwires(before), airwires(after)
    if any(count > old_counts[net] for net, count in new_counts.items()):
        raise ValueError('Replay reopened or increased another net')
    if recipe.get('expected_pcb_sha256') and digest(board)!=recipe['expected_pcb_sha256']:
        raise ValueError('Replay is not byte-identical to its reviewed checkpoint')
    result = {'kicad_version': after['kicad_version'], 'violations': 0, 'warnings': 0,
              'before': len(before['unconnected_items']), 'unconnected': len(after['unconnected_items']),
              'net_airwires': dict(new_counts), 'pcb_sha256': digest(board),
              'engineering_only': True, 'routing_completed': False, 'fabrication_release': False}
    (args.output_dir / 'replay-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Verify an unadopted S1 relocation; never change the accepted checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from merge_native_closure import copper
from native_connectivity import regressed_nets
from replay_block2_source_window import MEMBERS, reproducible_zip
from replay_ch019_electrode import geometry, clean
from route_targeted_closure import native_fresh

ROOT=Path(__file__).resolve().parent
RECIPE=ROOT/'engineering/followup-2026-10-16-escape139/mux-s1-recipe.json'
RECIPE_SHA256='347a71e80f713325e93df653998ece69228ef86545ca70d79248d0faae126675'


def digest(path: Path) -> str:return hashlib.sha256(path.read_bytes()).hexdigest()


def reviewed_recipe() -> dict[str, Any]:
    if digest(RECIPE)!=RECIPE_SHA256:raise ValueError('Diagnostic recipe integrity failure')
    d=json.loads(RECIPE.read_text())
    if d['scope']!='BLOCK2_MUX_S1_UNADOPTED_DIAGNOSTIC_139' or any(
        d.get(k) is not False for k in ('accepted','routing_completed','fabrication_release')):
        raise ValueError('Diagnostic scope or release flags differ')
    return d


def apply(text: str, d: dict[str, Any]) -> str:
    if hashlib.sha256(text.encode()).hexdigest()!=d['baseline_sha256']:
        raise ValueError('Wrong 139 PCB')
    old=copper(text)
    names={int(n):v for n,v in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)',text)}
    for uid,c in d['changes'].items():
        if old.get(uid)!=c['before'] or text.count(c['before'])!=1 or c['after']:
            raise ValueError('Reviewed removal differs')
        text=text.replace(c['before'],'',1)
    if old.keys() & d['additions'].keys():raise ValueError('UUID collision')
    for block in [*(c['before'] for c in d['changes'].values()),*d['additions'].values()]:
        if (not block.startswith('(segment') or not re.search(r'\(layer\s+"F\.Cu"\)',block)
            or names[int(re.search(r'\(net\s+(\d+)\)',block)[1])]!='MUX_S1'):
            raise ValueError('Only reviewed F.Cu S1 tracks may change; no vias')
    text=text[:text.rfind(')')]+'\n'+'\n'.join(d['additions'].values())+'\n)\n'
    if hashlib.sha256(text.encode()).hexdigest()!=d['expected_applied_sha256']:
        raise ValueError('Applied diagnostic differs')
    return text


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();d=reviewed_recipe()
    archive=ROOT/'engineering/block2-ch019-electrode-closed139.zip'
    if digest(archive)!=d['baseline_archive_sha256']:raise ValueError('Wrong baseline archive')
    a.output_dir.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        if sorted(z.namelist())!=sorted(MEMBERS):raise ValueError('Unexpected project members')
        for name in MEMBERS:(a.output_dir/name).write_bytes(z.read(name))
    board=a.output_dir/'eeg128-tdm.kicad_pcb';ref=a.output_dir/'reference';ref.mkdir()
    for name in MEMBERS:shutil.copy2(a.output_dir/name,ref/name)
    before=native_fresh(ref/board.name,a.output_dir/'drc-before.json');clean(before,139)
    board.write_text(apply(board.read_text(),d))
    after=native_fresh(board,a.output_dir/'drc-after.json');clean(after,139)
    shutil.copy2(ROOT/'engineering/eeg128-tdm.kicad_sch',board.with_suffix('.kicad_sch'))
    subprocess.run(['kicad-cli','pcb','drc','--schematic-parity','--severity-all','--all-track-errors',
                    '--format','json','--output',str(a.output_dir/'parity.json'),str(board)],check=True)
    clean(json.loads((a.output_dir/'parity.json').read_text()),139)
    if regressed_nets(before,after):raise ValueError('Neighbor connectivity regressed')
    geo=geometry(ref/board.name,board,d)
    if digest(board)!=d['expected_pcb_sha256']:raise ValueError('PCB replay differs')
    reproducible_zip(a.output_dir,a.output_dir/'diagnostic.zip')
    if digest(a.output_dir/'diagnostic.zip')!=d['expected_archive_sha256']:raise ValueError('ZIP replay differs')
    result={**geo,'diagnostic_verified':True,'accepted':False,'violations':0,'warnings':0,
            'unconnected':139,'diagnostic_parity_findings':0,'regressed_nets':[],
            'new_vias':0,'removed_vias':0,'pcb_sha256':digest(board),
            'archive_sha256':d['expected_archive_sha256'], 'routing_completed':False,'fabrication_release':False}
    (a.output_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()

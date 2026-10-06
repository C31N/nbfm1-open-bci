#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Diagnose a pinned routing artifact offline with native KiCad; no promotion; includes native dangling vias."""
import json
from pathlib import Path
import shutil
import subprocess
from remove_drc_dangling import clean

root = Path('/tmp/a2-cleanup-diagnostic')
root.mkdir(parents=True, exist_ok=True)
source = Path('/tmp/a2-cleanup-source')
board = root / 'eeg128-tdm.kicad_pcb'
shutil.copy2(source / 'round1-before-cleanup.kicad_pcb', board)
for suffix in ('kicad_pro', 'kicad_dru'):
    shutil.copy2(Path('hardware/eeg128-tdm') / ('eeg128-tdm.'+suffix), root / ('eeg128-tdm.'+suffix))
progress = []
for index in range(9):
    subprocess.run(['/usr/bin/python3', 'hardware/eeg128-tdm/fill_zones.py', str(board)], check=True)
    report = root / f'drc-step{index}.json'
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all',
                    '--all-track-errors', '--output', str(report), str(board)], check=True)
    shutil.copy2(board, root / f'step{index}.kicad_pcb')
    data = json.loads(report.read_text())
    state = {'step': index, 'unconnected': len(data.get('unconnected_items', [])),
             'violations': data.get('violations', [])}
    progress.append(state)
    print(json.dumps(state), flush=True)
    (root / 'progress.json').write_text(json.dumps(progress, indent=2)+'\n')
    if index == 8:
        break
    text, removed = clean(board.read_text(), data)
    if not removed:
        break
    board.write_text(text)
    print(json.dumps({'removed': removed}), flush=True)
subprocess.run(['/usr/bin/python3', 'hardware/eeg128-tdm/check_analog_layer_policy.py',
                '--baseline', str(source / 'round0.kicad_pcb'), '--candidate', str(board)], check=True)

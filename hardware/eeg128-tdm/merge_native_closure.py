#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Merge nonconflicting copper changes, then require native improvement."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from run_native_closure import verify
from native_connectivity import regressed_nets


def copper(text: str) -> dict[str, str]:
    """Read balanced top-level copper blocks, respecting quoted strings."""
    result: dict[str, str] = {}
    depth = 0
    quoted = False
    escaped = False
    start = 0
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '(':
            if depth == 1:
                start = index
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 1:
                block = text[start:index + 1]
                if re.match(r'\((segment|via|arc)\s', block):
                    match = re.search(r'\(uuid\s+"?([0-9a-f-]+)"?\)', block)
                    if not match or match[1] in result:
                        raise ValueError('Missing or duplicated copper UUID')
                    result[match[1]] = block
    if depth or quoted:
        raise ValueError('Unbalanced board syntax')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'branch', 'target', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline = copper(args.base.read_text())
    branch = copper(args.branch.read_text())
    target_text = args.target.read_text()
    target = copper(target_text)
    replacements: dict[str, str] = {}
    for uuid, block in baseline.items():
        if uuid not in branch:
            raise ValueError(f'Routing branch removed baseline copper {uuid}')
        if re.sub(r'\s+', '', block) != re.sub(r'\s+', '', branch[uuid]):
            if uuid not in target or re.sub(r'\s+', '', target[uuid]) != re.sub(r'\s+', '', block):
                raise ValueError(f'Concurrent copper change conflicts at {uuid}')
            replacements[uuid] = branch[uuid]
    additions = {uuid: block for uuid, block in branch.items() if uuid not in baseline}
    if additions.keys() & target.keys():
        raise ValueError('Added copper UUID conflicts with target')
    board = args.output_dir / 'eeg128-tdm.kicad_pcb'
    for ext in ('.kicad_pro', '.kicad_dru'):
        shutil.copy2(args.target.with_suffix(ext), board.with_suffix(ext))
    shutil.copy2(args.target, board)
    before = verify(board, args.output_dir / 'drc-before.json')
    for uuid, block in replacements.items():
        target_text = target_text.replace(target[uuid], block, 1)
    position = target_text.rfind(')')
    board.write_text(target_text[:position] + '\n' + '\n'.join(additions.values()) + '\n)\n')
    after = verify(board, args.output_dir / 'drc-final.json')
    if regressed_nets(before, after):
        raise RuntimeError('Merged board reopened or increased another net')
    if len(after['unconnected_items']) >= len(before['unconnected_items']):
        raise RuntimeError('Merged board did not improve connectivity')
    result = {'added_copper_items': len(additions), 'changed_copper_items': len(replacements),
              'violations': 0, 'warnings': 0,
              'before': len(before['unconnected_items']), 'unconnected': len(after['unconnected_items'])}
    (args.output_dir / 'merge-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

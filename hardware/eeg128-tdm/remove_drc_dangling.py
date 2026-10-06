#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Remove only unlocked segment UUIDs identified as dangling by native DRC."""
import argparse
import json
from pathlib import Path
import re
from verify_hardware_identity import balanced_blocks


def clean(text: str, report: dict) -> tuple[str, list[str]]:
    ids = []
    for violation in report.get('violations', []):
        if violation.get('type') != 'track_dangling' or violation.get('severity') != 'warning':
            continue
        items = violation.get('items', [])
        if len(items) != 1 or not items[0].get('uuid'):
            raise ValueError('Ambiguous dangling-track DRC item')
        ids.append(items[0]['uuid'])
    for uuid in sorted(set(ids)):
        blocks = balanced_blocks(re.sub(r'\(segment(?=\s)', '(segment ', text), 'segment')
        matches = [b for b in blocks if re.search(r'\(uuid\s+"?'+re.escape(uuid)+r'"?\)', b)]
        if len(matches) != 1 or re.search(r'\(locked(?:\s|\))', matches[0]):
            raise ValueError('Dangling UUID must identify one unlocked segment')
        # Keep all other source bytes unchanged, including KiCad formatting.
        block = matches[0]
        original = block if block in text else block.replace('(segment ', '(segment', 1)
        if original not in text:
            raise ValueError('Cannot locate exact segment text')
        text = text.replace(original, '', 1)
    return text, sorted(set(ids))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    text, removed = clean(args.board.read_text(), json.loads(args.report.read_text()))
    if removed:
        args.board.write_text(text)
    print(json.dumps({'removed_dangling_segment_uuids': removed}))

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Restrict exported TDM_ANALOG traces to F.Cu before routing."""
import argparse
import json
from pathlib import Path
import re
from verify_hardware_identity import balanced_blocks


def constrain(text: str) -> str:
    classes = [b for b in balanced_blocks(text, 'class')
               if re.match(r'\(class\s+"?TDM_ANALOG"?\s', b)]
    if len(classes) != 1:
        raise ValueError('Expected exactly one TDM_ANALOG class')
    block = classes[0]
    if not re.search(r'\(layer\s+"?F\.Cu"?\s', text):
        raise ValueError('F.Cu layer missing from DSN')
    if len(re.findall(r'\(circuit\b', block)) != 1:
        raise ValueError('Expected exactly one analog circuit scope')
    if re.search(r'\(use_layer\b', block):
        raise ValueError('Unexpected existing analog layer restriction')
    updated = re.sub(r'\(circuit\b', '(circuit\n        (use_layer "F.Cu")', block, count=1)
    return text.replace(block, updated, 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dsn', type=Path)
    args = parser.parse_args()
    args.dsn.write_text(constrain(args.dsn.read_text()))
    print(json.dumps({'analog_class': 'TDM_ANALOG', 'trace_layers': ['F.Cu']}))

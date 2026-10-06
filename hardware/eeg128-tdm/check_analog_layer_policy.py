#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reject new long B.Cu routes on CH/BANK/ADC analog signals."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
from verify_hardware_identity import balanced_blocks


def bottom_lengths(path: Path) -> dict[str, float]:
    text = re.sub(r"\((segment|arc)(?=\s)", r"(\1 ", path.read_text())
    names = dict(re.findall(r'\(net\s+(\d+)\s+"([^"\n]+)"\)', text))
    lengths: dict[str, float] = defaultdict(float)
    for block in balanced_blocks(text, 'segment'):
        if not re.search(r'\(layer\s+"B\.Cu"\)', block):
            continue
        number = re.search(r'\(net\s+(\d+)\)', block)
        if number is None or number.group(1) not in names:
            raise RuntimeError('Unknown net on B.Cu segment')
        name = names[number.group(1)]
        if not(name.startswith(('CH', 'BANK')) or re.fullmatch(r'ADC\d+_[PN]', name)):
            continue
        def point(kind: str) -> tuple[float, float]:
            hit = re.search(r'\('+kind+r'\s+([-\d.]+)\s+([-\d.]+)\)', block)
            if hit is None:
                raise RuntimeError('Unparseable analog segment geometry')
            return float(hit.group(1)), float(hit.group(2))
        lengths[name] += math.dist(point('start'), point('end'))
    # Fail closed for unsupported copper-arc geometry rather than omit its length.
    for block in balanced_blocks(text, 'arc'):
        if re.search(r'\(layer\s+"B\.Cu"\)', block):
            raise RuntimeError('B.Cu arcs require explicit analog-layer review')
    return dict(lengths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    baseline = bottom_lengths(args.baseline)
    candidate = bottom_lengths(args.candidate)
    added = {net: length-baseline.get(net, 0.0) for net, length in candidate.items()
             if length-baseline.get(net, 0.0) > .01}
    rejected = {net: length for net, length in added.items() if length > 2.001}
    print(json.dumps({'analog_layer_pass': not rejected, 'added_bottom_mm': added,
                      'rejected_long_bottom_mm': rejected}, sort_keys=True))
    return 1 if rejected else 0


if __name__ == '__main__':
    raise SystemExit(main())

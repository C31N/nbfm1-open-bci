#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from pathlib import Path
import re


STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01)
				(material "JLC solder mask") (epsilon_r 3.8))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.0994)
				(material "JLC3313 FR-4") (epsilon_r 4.1))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (thickness 1.265)
				(material "FR-4 core") (epsilon_r 4.6))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (thickness 0.0994)
				(material "JLC3313 FR-4") (epsilon_r 4.1))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)
				(material "JLC solder mask") (epsilon_r 3.8))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(dielectric_constraints yes)
		)
"""


def balanced_end(text: str, start: int) -> int:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    raise RuntimeError("unbalanced KiCad S-expression")


def apply_stackup(text: str) -> str:
    text = re.sub(
        r'\(1 "In1\.Cu" (?:signal|power)\)',
        '(1 "In1.Cu" power)',
        text,
    )
    text = re.sub(
        r'\(2 "In2\.Cu" (?:signal|power)\)',
        '(2 "In2.Cu" power)',
        text,
    )

    marker = "\n\t\t(stackup"
    start = text.find(marker)
    if start >= 0:
        block_start = start + 1
        block_end = balanced_end(text, block_start)
        return text[:block_start] + STACKUP.strip("\n") + text[block_end:]

    setup = "\n\t(setup\n"
    if setup not in text:
        raise RuntimeError("KiCad board has no setup block")
    return text.replace(setup, setup + STACKUP, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    args = parser.parse_args()

    path = Path(args.board)
    original = path.read_text(encoding="utf-8")
    updated = apply_stackup(original)
    path.write_text(updated, encoding="utf-8")
    print(
        {
            "board": str(path),
            "stackup": "JLC04161H-3313",
            "layers": ["F.Cu", "In1.Cu:GND", "In2.Cu:PWR", "B.Cu"],
            "nominal_thickness_mm": 1.6,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

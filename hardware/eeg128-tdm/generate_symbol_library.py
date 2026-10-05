#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

from pathlib import Path

from generate_schematic import library_symbol, parse_components, signature


ROOT = Path(__file__).resolve().parent


def externalize(block: str) -> str:
    return block.replace('NBFM1_A0:', '', 1)


def main() -> int:
    components = parse_components()
    signatures = sorted({signature(component) for component in components})
    symbols = [externalize(library_symbol(numbers)) for numbers in signatures]

    text = "\n".join(
        [
            "(kicad_symbol_lib",
            "  (version 20231120)",
            '  (generator "nbfm1-open-bci-generate_symbol_library")',
            '  (generator_version "1.0")',
            *symbols,
            ")",
            "",
        ]
    )
    output = ROOT / "NBFM1_A0.kicad_sym"
    output.write_text(text, encoding="utf-8")
    print(
        {
            "output": str(output),
            "symbols": len(symbols),
            "components_covered": len(components),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

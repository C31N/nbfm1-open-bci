#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew

from prepare_autoroute import ensure_critical_manufacturer_footprints


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    board = pcbnew.LoadBoard(str(input_path))
    if board is None:
        raise RuntimeError(f"cannot load {input_path}")

    replaced = ensure_critical_manufacturer_footprints(board)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)
    print({"output": str(output_path), "critical_footprints_replaced": replaced})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

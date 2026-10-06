#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministically refill all KiCad copper zones."
    )
    parser.add_argument("board")
    args = parser.parse_args()

    path = Path(args.board)
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        raise RuntimeError(f"cannot load {path}")

    zone_count = board.GetAreaCount()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(path), board)
    print({"board": str(path), "zones_filled": zone_count})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

    path = Path(args.board).resolve()
    project = path.with_suffix('.kicad_pro')
    original_project = project.read_bytes() if project.exists() else None
    try:
        board = pcbnew.LoadBoard(str(path))
        if board is None:
            raise RuntimeError(f"cannot load {path}")
        zone_count = board.GetAreaCount()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        if not pcbnew.SaveBoard(str(path), board):
            raise RuntimeError(f"cannot save filled board {path}")
    finally:
        # Preserve the authoritative netclasses even if native SaveBoard writes
        # process-global default project settings next to this board basename.
        if original_project is not None:
            project.write_bytes(original_project)
    print({"board": str(path), "zones_filled": zone_count})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

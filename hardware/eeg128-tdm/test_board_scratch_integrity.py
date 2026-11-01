#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Isolated fail-closed footprint and pad inventory regression tests."""
from __future__ import annotations

import unittest

from board_scratch_integrity import component_inventory, require_unchanged_components


class _UUID:
    def __init__(self, value: str) -> None:
        self.value = value

    def AsString(self) -> str:
        return self.value


class _Point:
    def __init__(self, x: int, y: int) -> None:
        self.x, self.y = x, y


class _LayerSet:
    def FmtBin(self) -> str:
        return "000000000001"


class _Pad:
    def __init__(self, idx: int) -> None:
        self.m_Uuid = _UUID(f"pad-{idx}")
        self.idx = idx
        self.net = "AGND"

    def GetNumber(self) -> str:
        return "1"

    def GetNetname(self) -> str:
        return self.net

    def GetPosition(self) -> _Point:
        return _Point(self.idx, 5)

    def GetSize(self) -> _Point:
        return _Point(150, 150)

    def GetLayerSet(self) -> _LayerSet:
        return _LayerSet()

    def GetShape(self) -> int:
        return 0


class _Footprint:
    def __init__(self, idx: int) -> None:
        self.idx = idx
        self.m_Uuid = _UUID(f"footprint-{idx}")
        self.pad = _Pad(idx)

    def GetReference(self) -> str:
        return f"R{self.idx}"

    def GetPosition(self) -> _Point:
        return _Point(self.idx, 7)

    def GetLayer(self) -> int:
        return 0

    def GetValue(self) -> str:
        return "10k"

    def Pads(self) -> list[_Pad]:
        return [self.pad]


class _Board:
    def __init__(self) -> None:
        self.footprints = [_Footprint(i) for i in range(1, 643)]

    def GetFootprints(self) -> list[_Footprint]:
        return self.footprints

    def GetPads(self) -> list[_Pad]:
        return [f.pad for f in self.footprints]


class BoardScratchIntegrityTests(unittest.TestCase):
    def test_baseline_survives_unchanged_scratch(self) -> None:
        board = _Board()
        snapshot = component_inventory(board)
        self.assertEqual(len(snapshot), 642)
        require_unchanged_components(board, snapshot, "unchanged")

    def test_missing_footprint_is_rejected(self) -> None:
        board = _Board()
        snapshot = component_inventory(board)
        board.footprints.pop()
        with self.assertRaisesRegex(RuntimeError, "642 footprints"):
            require_unchanged_components(board, snapshot, "ripup")

    def test_pad_net_change_is_rejected(self) -> None:
        board = _Board()
        snapshot = component_inventory(board)
        board.footprints[2].pad.net = "3V3A"
        with self.assertRaisesRegex(RuntimeError, "changed=\\['R3'\\]"):
            require_unchanged_components(board, snapshot, "routing")

    def test_footprint_uuid_change_is_rejected(self) -> None:
        board = _Board()
        snapshot = component_inventory(board)
        board.footprints[0].m_Uuid = _UUID("replacement")
        with self.assertRaisesRegex(RuntimeError, "Footprint/pad mutation"):
            require_unchanged_components(board, snapshot, "save")

    def test_board_pads_and_footprint_pads_must_agree(self) -> None:
        board = _Board()
        board.GetPads = lambda: []
        with self.assertRaisesRegex(RuntimeError, "board.GetPads"):
            component_inventory(board)

    def test_duplicate_pad_uuid_is_rejected(self) -> None:
        board = _Board()
        board.footprints[1].pad.m_Uuid = _UUID("pad-1")
        with self.assertRaisesRegex(RuntimeError, "duplicate pad UUID"):
            component_inventory(board)


if __name__ == "__main__":
    unittest.main()

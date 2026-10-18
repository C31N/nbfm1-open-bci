# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure fail-closed CH031-N local reroute guard tests."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock

import probe_block2_ch031_selective as mod


class LocalCH031Guards(unittest.TestCase):
    def test_two_referenced_windows_are_distinct(self) -> None:
        self.assertEqual(len(mod.PATCHES), 2)
        self.assertNotEqual(mod.PATCHES[0], mod.PATCHES[1])
        self.assertEqual(mod.PATCHES[0], (48.1259, 33.8786))
        self.assertEqual(mod.PATCHES[1], (46.3236, 27.4653))

    def test_fail_closed_reporting(self) -> None:
        self.assertFalse(mod.OUTPUT_FLAGS['accepted'])
        self.assertFalse(mod.OUTPUT_FLAGS['routing_completed'])
        self.assertFalse(mod.OUTPUT_FLAGS['fabrication_release'])
        self.assertFalse(mod.OUTPUT_FLAGS['replay_qualified'])

    def test_only_unmodified_pcb_is_input(self) -> None:
        self.assertEqual(mod.PCB, 'eeg128-tdm.kicad_pcb')
        code = Path(mod.__file__).read_text()
        self.assertNotIn('pcbnew.SaveBoard(', code)
        self.assertNotIn("'accepted': True", code)
        self.assertNotIn("kicad-cli pcb export", code)

    def test_track_ref_owner_remains_until_finally(self) -> None:
        code = Path(mod.__file__).read_text()
        self.assertIn("for t in chosen:", code)
        self.assertIn("finally:", code)
        self.assertIn("board.Add(t)", code)


if __name__ == '__main__':
    unittest.main()

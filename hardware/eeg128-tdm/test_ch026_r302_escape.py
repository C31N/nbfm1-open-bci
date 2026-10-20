# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import analyze_ch026_r302_escape as module


class R302CH026Guards(unittest.TestCase):
    def test_hard_release_flags(self) -> None:
        for key in ('accepted','routing_completed','fabrication_release','manufacturing_exports'):
            self.assertIs(module.FLAGS[key],False)

    def test_copper_identity_and_original_file_preserved(self) -> None:
        src=Path(module.__file__).read_text()
        self.assertIn("'CH026_P_ELECTRODE'",src)
        self.assertIn("t.GetLayer()!=pcbnew.F_Cu",src)
        self.assertIn("finally: board.Add(t)",src)
        self.assertIn("digest(path.read_bytes())!=PCB_SHA",src)
        self.assertNotIn("pcbnew.SaveBoard(",src)
        self.assertNotIn("kicad-cli pcb export",src)

    def test_radius_and_power_guard(self) -> None:
        src=Path(module.__file__).read_text()
        self.assertIn("if d>4.0:continue",src)
        self.assertIn("Point(center).buffer(3.5)",src)
        self.assertIn("protected.buffer(.505)",src)
        self.assertIn("line.distance(p)<1.0",src)


if __name__=='__main__':
    unittest.main()

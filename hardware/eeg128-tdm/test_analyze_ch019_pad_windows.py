# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import analyze_ch019_pad_windows as m


class PadWindowGuards(unittest.TestCase):
    def test_no_manufacturing(self) -> None:
        s = Path(m.__file__).read_text()
        self.assertNotIn('pcbnew.SaveBoard(', s)
        self.assertNotIn("'accepted': True", s)
        self.assertIn("with tempfile.TemporaryDirectory", s)

    def test_expected_three_pad_scope(self) -> None:
        self.assertEqual(len(m.TRUNK), 3)
        self.assertEqual(len(m.ELECTRODE), 2)
        for flag in ('accepted','routing_completed','fabrication_release'):
            self.assertIs(m.FLAGS[flag], False)


if __name__ == '__main__':
    unittest.main()

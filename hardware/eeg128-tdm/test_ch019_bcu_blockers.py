# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import analyze_ch019_bcu_blockers as mod


class CH019BCuDiagnostic(unittest.TestCase):
    def test_endpoints_are_existing_vias(self):
        self.assertEqual(mod.A, (39.915, 45.15))
        self.assertEqual(mod.B, (32.7, 23.4))

    def test_hard_no_release(self):
        for k in ('accepted', 'routing_completed', 'fabrication_release',
                  'drc_qualified', 'replay_qualified', 'manufacturing_files'):
            self.assertIs(mod.FLAGS[k], False)

    def test_forbid_any_board_writes_or_exports(self):
        s = Path(mod.__file__).read_text()
        self.assertNotIn('pcbnew.SaveBoard(', s)
        self.assertNotIn('kicad-cli pcb export', s)
        self.assertIn("name not in {'CH018_N_MUX', 'CH022_N_ELECTRODE'}", s)
        self.assertIn("pad_dist >= 1.00 and via_dist >= .65", s)
        self.assertIn("routing_domain(board, .30, .25)", s)

    def test_sha_pinning(self):
        self.assertEqual(len(mod.FROZEN_INPUT_SHA), 64)


if __name__ == '__main__':
    unittest.main()

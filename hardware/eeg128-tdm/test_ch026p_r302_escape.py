# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_ch026p_r302_escape as m


class CH026EscapeGuards(unittest.TestCase):
    def test_source_identity(self) -> None:
        self.assertEqual(m.TARGET_NET, 'CH026_P_ELECTRODE')
        self.assertEqual(m.R302, (36.15,15.6))
        self.assertEqual(m.J223, (43.75,7.6))
    def test_no_release_or_production(self) -> None:
        for k in ('accepted','routing_completed','fabrication_release',
                  'independent_replay_verified','native_qualification','manufacturing_files'):
            self.assertFalse(m.FLAGS[k])
        code=Path(m.__file__).read_text()
        self.assertNotIn('pcbnew.SaveBoard(', code)
        self.assertNotIn('kicad-cli pcb export', code)
        self.assertIn("dj < 6.1 or dpad < .50 or dvia < .50", code)
        self.assertIn("power.buffer(.505)", code)
        self.assertIn("routing_domain(board, .30, .25)", code)


if __name__ == '__main__':
    unittest.main()

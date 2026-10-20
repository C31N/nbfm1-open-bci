# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import unittest
from pathlib import Path

import analyze_ch022_bcu_blockers as mod


class CH022BCuGuards(unittest.TestCase):
    def test_protected_nets(self) -> None:
        self.assertTrue({'CH026_P_ELECTRODE', 'CH024_P_MUX',
                         'CH019_P_MUX', 'CH018_N_MUX', 'VCM',
                         'CH022_N_ELECTRODE'}.issubset(mod.PROTECTED))

    def test_never_release(self) -> None:
        for k in ('accepted', 'routing_completed', 'fabrication_release',
                  'native_qualification', 'independent_replay_verified',
                  'manufacturing_exports'):
            self.assertFalse(mod.FLAGS[k])

    def test_readonly_and_guards(self) -> None:
        code = Path(mod.__file__).read_text()
        self.assertNotIn('board.Remove(', code)
        self.assertNotIn('pcbnew.SaveBoard(', code)
        self.assertIn("closest_pad < 1.0 or closest_via < 0.65", code)
        self.assertIn("corridor_width: float = 1.2", code)


if __name__ == '__main__':
    unittest.main()

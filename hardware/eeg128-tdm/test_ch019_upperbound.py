# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import analyze_ch019_upperbound as module


class UpperBoundModelGuard(unittest.TestCase):
    def test_immutable_scope(self) -> None:
        body=Path(module.__file__).read_text()
        self.assertIn("reserved = {'VCM', 'CH018_N_MUX'}",body)
        self.assertIn('via',body)
        self.assertIn("full_neighbor_restitution': False",body)
        self.assertNotIn("pcbnew.SaveBoard(",body)

    def test_fail_closed(self) -> None:
        self.assertEqual(module.A,(39.915,45.15))
        self.assertEqual(module.B,(32.7,23.4))
        for k in ('accepted','routing_completed','fabrication_release',
                  'independent_replay_verified','native_qualification','manufacturing_files'):
            self.assertFalse(module.FLAGS[k])


if __name__ == '__main__':
    unittest.main()

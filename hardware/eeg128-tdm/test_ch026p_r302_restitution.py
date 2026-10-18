# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_ch026p_r302_restitution as mod


class CH026RestitutionGuard(unittest.TestCase):
    def test_pinned_copper_and_power(self) -> None:
        self.assertEqual(mod.UUID,'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa')
        source=Path(mod.__file__).read_text()
        self.assertIn('power.buffer(.505)',source)
        self.assertIn('routing_domain(board,.30,.25)',source)
        self.assertIn("Point(target).buffer(clearance_radius)",source)
        self.assertIn('protected!=current',source)
        self.assertIn('net_regressions',source)

    def test_nothing_released_or_exported(self) -> None:
        for k in ('accepted','routing_completed','fabrication_release',
                  'independent_replay_verified','manufacturing_files','native_qualification'):
            self.assertIs(mod.FLAGS[k],False)
        src=Path(mod.__file__).read_text()
        self.assertIn('TemporaryDirectory',src)
        self.assertNotIn('kicad-cli pcb export',src)


if __name__=='__main__':
    unittest.main()

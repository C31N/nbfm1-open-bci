# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_ch026_ch022_joint as m
class CH026CH022Test(unittest.TestCase):
    def test_protected_selection(self) -> None:
        self.assertEqual(m.PINNED['long'],'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa')
        self.assertEqual(m.PINNED['diagonal'],'9dd73183-097f-4e10-a5b8-8875dab1c044')
        self.assertEqual(m.J223,(43.75,7.6))
        src=Path(m.__file__).read_text()
        self.assertIn('if now!=frozen',src)
        self.assertIn('power_copper',src)
        self.assertIn('local_via_window',src)
        self.assertIn('native_fresh',src)
        self.assertNotIn('kicad-cli pcb export',src)
    def test_fail_closed_flags(self) -> None:
        for k in ('accepted','routing_completed','fabrication_release',
                  'independent_replay_verified','native_qualification','manufacturing_files'):
            self.assertFalse(m.FLAGS[k])
if __name__=='__main__':
    unittest.main()

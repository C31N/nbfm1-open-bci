# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
import unittest
from pathlib import Path
import probe_block2_ch026_joint136 as m
class TripleNetsGuards(unittest.TestCase):
    def test_release_prohibited(self) -> None:
        for key in ('accepted','routing_completed','fabrication_release',
                    'native_qualification','independent_replay_verified',
                    'manufacturing_files'):
            self.assertFalse(m.FLAGS[key])
    def test_critical_copper_immutable(self) -> None:
        src=Path(m.__file__).read_text()
        self.assertIn("('CH018_N_MUX','VCM')",src)
        self.assertIn("if freeze!=present",src)
        self.assertIn("region=routing_domain(board,.30,.25)",src)
        self.assertIn("power.buffer(.505)",src)
        self.assertIn("R305.2",src)
        self.assertIn("CH026_neighbor_geometry_restored",src)
        self.assertNotIn("kicad-cli pcb export",src)
if __name__=='__main__':
    unittest.main()

# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import analyze_ch022_bcu_blockers as analysis
import probe_block2_r302_joint as probe


class NativeCH022BlockedCorridor(unittest.TestCase):
    def test_exact_layers_and_power_keepout(self) -> None:
        body=Path(analysis.__file__).read_text()
        self.assertIn("(pcbnew.B_Cu, pcbnew.In2_Cu)", body)
        self.assertIn("power.buffer(.505)", body)
        self.assertIn("separated_component_gap_mm", body)
        self.assertIn("new_via_bands", body)
        self.assertIn("front_blockers", body)

    def test_only_read_blockers_after_failed_route(self) -> None:
        body=Path(probe.__file__).read_text()
        self.assertIn("audit_bridge_blockers", body)
        self.assertIn("result['bridge_copper_blockers'] = inspect(", body)
        self.assertNotIn("pcbnew.SaveBoard(", Path(analysis.__file__).read_text())
        self.assertNotIn("'accepted': True", body)


if __name__ == '__main__':
    unittest.main()

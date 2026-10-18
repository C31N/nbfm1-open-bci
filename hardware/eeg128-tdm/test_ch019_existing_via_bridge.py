# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_ch019_existing_via_bridge as mod


class ExistingViaBridges(unittest.TestCase):
    def test_reviewed_via_anchors(self) -> None:
        self.assertEqual(mod.VIA_ENDS['direct'],
                         ((39.915, 45.15), (32.7, 23.4)))
        self.assertEqual(mod.VIA_ENDS['alternate'],
                         ((43.5, 43.279999), (33.5, 24.229999)))
        self.assertEqual(len(mod.VIA_ENDS), 3)

    def test_release_flags_are_never_enabled(self) -> None:
        self.assertFalse(mod.FLAGS['accepted'])
        self.assertFalse(mod.FLAGS['routing_completed'])
        self.assertFalse(mod.FLAGS['fabrication_release'])
        self.assertFalse(mod.FLAGS['native_qualification'])
        self.assertFalse(mod.FLAGS['independent_replay_verified'])

    def test_reuse_existing_vias_and_preserve_tracks(self) -> None:
        content = Path(mod.__file__).read_text()
        self.assertIn("if len(via_items) != 4:", content)
        self.assertIn("for track in selected:", content)
        self.assertIn("finally:", content)
        self.assertNotIn("kicad-cli pcb export", content)
        self.assertNotIn("'accepted': True", content)

    def test_geometric_power_gate_reported(self) -> None:
        content = Path(mod.__file__).read_text()
        self.assertIn("'L3_power_loss_mm2'", content)
        self.assertIn("'L3_power_gain_mm2'", content)
        self.assertIn("routing_domain(board, .30, .25)", content)


if __name__ == '__main__':
    unittest.main()

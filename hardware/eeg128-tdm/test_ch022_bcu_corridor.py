# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_block2_r302_joint as probe


class CH022BCuInteriorGate(unittest.TestCase):
    def test_never_cut_protected_signal_or_power(self) -> None:
        source = Path(probe.__file__).read_text()
        for name in ("'CH022_N_ELECTRODE'", "'CH026_P_ELECTRODE'",
                     "'CH024_P_MUX'", "'CH019_P_MUX'", "'CH018_N_MUX'",
                     "'VCM'", "'AGND'"):
            self.assertIn(name, source)
        self.assertIn("line.distance(p) < 1.0", source)
        self.assertIn("line.distance(v) < .65", source)
        self.assertIn("track.GetLayer() != pcbnew.B_Cu", source)
        self.assertIn("bcu_corridor_cut > 2.5", source)

    def test_restitution_and_j2_guard(self) -> None:
        source = Path(probe.__file__).read_text()
        self.assertIn("result['status'] = 'neighbor_unrestored'", source)
        self.assertIn("current_j2 != untouched_j2", source)
        self.assertIn("current_ch018 != original_ch018 or current_vcm != original_vcm", source)
        self.assertIn("power_copper(base)", source)
        self.assertIn("regressed_nets(before, after)", source)

    def test_release_is_fail_closed(self) -> None:
        for flag in ("accepted", "routing_completed", "fabrication_release",
                     "independent_replay_verified", "native_qualification",
                     "manufacturing_files"):
            self.assertIs(probe.FLAGS[flag], False)


if __name__ == '__main__':
    unittest.main()

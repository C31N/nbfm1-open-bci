#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Block2 FCu micro-ripup no-release static safety contract."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_real_mux_fcu_block2_ripup.py")

class TestBlock2FcuRipup(unittest.TestCase):
    def test_protected_cut_whitelist_and_restitution(self) -> None:
        s = SOURCE.read_text()
        for marker in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX",
            "IMMUTABLE_NETS", "movable(", "CH025_N_MUX",
            "CH027_N_MUX", "CH022_N_ELECTRODE", "MUX_EN",
            "100pct_restituted", "all_originals_restituted",
            "native_In1_exact", "native_L3_exact",
            "candidate_native_DRC_pass", "regressed_nets",
            "new_via_count", "no_new_vias",
            '"fabrication_release": False', '"accepted": False',
        ):
            self.assertIn(marker, s)
        for denied in ("make_via(", "ExportGerbers", "ExportDrill",
                       "GeneratePositionFiles"):
            self.assertNotIn(denied, s)

if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CH027-only wide FCu safe copper invariant."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch027_wide_fcu_untouched_s0.py")

class TestCH027WideFCu(unittest.TestCase):
    def test_no_other_copper_changes(self) -> None:
        source=SOURCE.read_text()
        for required in (
            "S0_UUIDS", "CH027_ALT_VIA", "CH027_VIA_LANDINGS_MM",
            "both_original_S0_tracks_untouched",
            "protected_originals_unchanged", "allow_vias=False",
            "native_L3_exact_zero", "exact_native_difference",
            "regressed_nets", "PINNED_CANDIDATE_SHA",
            '"fabrication_release": False', '"accepted": False',
            "25.0", "TemporaryDirectory",
            "FCu_topologically_connected",
            "mesh_skipped_complexity_budget",
            "source_component", "target_component",
            "connected and complexity <= 1900",
        ):
            self.assertIn(required, source)
        for banned in ("ExportGerbers", "ExportDrill",
                       "make_via(", "In1_Cu, pcbnew.In2_Cu"):
            self.assertNotIn(banned, source)

if __name__ == "__main__":
    unittest.main()

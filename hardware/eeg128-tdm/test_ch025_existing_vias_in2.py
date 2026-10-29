#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static no-release and no-new-via guard for native CH025 In2 probe."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch025_existing_vias_in2.py")

class TestCH025In2ExistingVias(unittest.TestCase):
    def test_protected_original_and_exact_zero(self) -> None:
        s = SOURCE.read_text()
        for x in (
            "PINNED_CANDIDATE_SHA", "SOURCES", "TARGETS",
            "pcbnew.In2_Cu", "pcbnew.In1_Cu",
            "power.buffer(.58)", "reserved_bottom=power.buffer(.505)",
            "SHAPE_POLY_SET", "exact_native_difference",
            "source_originals_unchanged", "new_vias_added",
            "all_existing_vias_unchanged",
            "bounded_In2_A_star_started",
            "L3_exact_zero", "In1_exact_zero",
            "regressed_nets", "native_DRC_qualified",
            '"fabrication_release": False', '"accepted": False',
        ):
            self.assertIn(x, s)
        for x in ("make_via(", "ExportGerbers", "ExportDrill",
                  "IsOnLayer(pcbnew.In1_Cu)"):
            self.assertNotIn(x, s)

if __name__ == "__main__":
    unittest.main()

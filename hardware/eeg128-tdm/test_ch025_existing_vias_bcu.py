#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static nonrelease contract for existing-only CH025 B.Cu route."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch025_existing_vias_bcu.py")

class TestExistingCH025Vias(unittest.TestCase):
    def test_locked_via_contract(self) -> None:
        text = SOURCE.read_text()
        for value in ("SRC_VIA", "DST_VIA", "SRC_ALT_VIA",
                      "DST_ALT_VIA", "VIATYPE_THROUGH", "BCu_annulus_components",
                      "no_new_vias", "allow_vias=False",
                      "native_DRC_qualified", "exact_native_difference",
                      "In1_exact_zero", "L3_exact_zero",
                      "unchanged_fingerprints(board)",
                      '"fabrication_release": False',
                      '"accepted": False', "TemporaryDirectory"):
            self.assertIn(value, text)
        for forbidden in ("make_via(", "ExportGerbers", "ExportDrill"):
            self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()

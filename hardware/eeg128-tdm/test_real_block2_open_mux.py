#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static guard of real open-MUX native FCu-only trial."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_real_block2_open_mux.py")

class TestNativeRealOpenMux(unittest.TestCase):
    def test_no_release_and_native_drc_gate(self) -> None:
        s = SOURCE.read_text()
        for text in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "airwire_counts", "native_net_before",
            "native_net_after", "native_DRC_qualified",
            "regressed_nets", "unchanged_fingerprints",
            "exact_native_difference", "native_3V3A_exact",
            "native_In1_exact", "no_regressed_nets",
            "unconnected", "138", "add_path",
            "original_copper_restituted",
            '"accepted": False', '"fabrication_release": False',
        ):
            self.assertIn(text, s)
        for forbidden in ("make_via(", "ExportGerbers", "ExportDrill"):
            self.assertNotIn(forbidden, s)

if __name__ == "__main__":
    unittest.main()

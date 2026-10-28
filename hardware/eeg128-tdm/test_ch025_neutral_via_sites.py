#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed static contract for CH025 exact-zero native via screens."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch025_neutral_via_sites.py")

class TestCH025NeutralViaSites(unittest.TestCase):
    def test_source_gate(self) -> None:
        text = SOURCE.read_text()
        for term in ("PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
                     "ZONE_FILLER", "exact_native_difference",
                     "polygon_snapshot(board, pcbnew.In1_Cu)",
                     "polygon_snapshot(board, pcbnew.In2_Cu)",
                     "track_inventory(board) != original",
                     "protected_originals_restituted",
                     "native_zone_neutral_pair_found",
                     "physical_route_qualified",
                     '"accepted": False',
                     '"fabrication_release": False',
                     "no_native_exact_zero_two_via_pair_in_sample"):
            self.assertIn(term, text)
        for blocked in ("SaveBoard(", "ExportGerbers",
                        "ExportDrill", "Gerber",
                        "In1_Cu, netcode"):
            self.assertNotIn(blocked, text)

if __name__ == "__main__":
    unittest.main()

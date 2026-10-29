#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""No-release contract for native MUX_S0 In1/L3 exact-zero via-hop screen."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_mux_s0_exact_via_hop.py")

class TestMUXS0NativeViaHop(unittest.TestCase):
    def test_fail_closed(self) -> None:
        text = SOURCE.read_text()
        for snippet in (
            "PINNED_CANDIDATE_SHA",
            "ARCHIVE_SHA256", "S0_UUIDS",
            "existing_S0_vias", "ZONE_FILLER",
            "polygon_snapshot(board, pcbnew.In1_Cu)",
            "polygon_snapshot(board, pcbnew.In2_Cu)",
            "native_both_layers_exact", "native_3V3A_loss_mm2",
            "native_3V3A_gain_mm2",
            "pair_both_layers_exact_count",
            "original_tracks_and_footprints_unchanged",
            "after_via_ids != original_via_ids",
            "physical_hop_qualified", "TemporaryDirectory",
            '"fabrication_release": False', '"accepted": False',
        ):
            self.assertIn(snippet, text)
        for banned in ("SaveBoard(", "ExportGerbers",
                       "ExportDrill", "Gerber"):
            self.assertNotIn(banned, text)

if __name__ == "__main__":
    unittest.main()

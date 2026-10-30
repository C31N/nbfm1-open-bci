#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static contract checks for the non-producing fixed-copper upper bound."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_fcu_fixed_cut_upperbound.py")


class FixedCutUpperboundTests(unittest.TestCase):
    def test_source_guards_and_protected_copper(self):
        source = SOURCE.read_text()
        for required in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "native_open_positions", "baseline_DRC",
            "CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX",
            "PRESERVE_CHANNELS", '"CH022_"', '"CH025_"', '"CH027_"',
            "upperbound_movable(net)", "pcbnew.F_Cu",
            "same_free_component", "original", "immutable_tracks_unchanged",
            "protected_footprints_unchanged", "via_UUID_set_unchanged",
            "source_unchanged", "fixed_only_partitioned_targets",
            '"accepted": False', '"fabrication_release": False',
        ):
            self.assertIn(required, source)
        for forbidden in (
            "pcbnew.SaveBoard(", "make_via(", "ExportGerbers",
            "ExportDrill", "ExportBOM", "ExportCPL",
            "SetLayer(pcbnew.In1_Cu)",
        ):
            self.assertNotIn(forbidden, source)

    def test_upperbound_source_never_publishes_candidate(self):
        source = SOURCE.read_text()
        self.assertIn('"saved_candidate_PCB": False', source)
        self.assertIn('"native_candidate_DRC_pass": False', source)
        self.assertIn("upperbound_only_not_routing_qualified", source)
        self.assertIn("TemporaryDirectory", source)


if __name__ == "__main__":
    unittest.main()

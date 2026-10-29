#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static guard for native micro-ripup, restoration and original copper."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_micro_ripup_fcu.py")

class TestMicroRipupFCu(unittest.TestCase):
    def test_virtual_original_restoration(self) -> None:
        code = SOURCE.read_text()
        for token in (
            "PINNED_CANDIDATE_SHA", "CASE_VICTIMS",
            "CH027_ALT_VIA", "CH027_VIA_LANDINGS_MM",
            "S0_UUIDS", "NEIGHBORS", "CUT",
            "geometric_contact_reachable",
            "same_free_FCu_component",
            "complete_restitution_geometry_found",
            "native_3V3A_exact_zero",
            "track_inventory(board) != initial",
            "unchanged_fingerprints(board) != protected",
            "max_nodes=40000", "regressed_nets",
            "CH027_Astar_proposal", "bounded_CH027_FCu_Astar_started",
            "S1_soft_reservation_applied",
            "victim_restitution_order", "cost_regions=cost_regions",
            "reinserted_original", "original_S0_copper_reinserted",
            "original_S0_segments_reinserted_for_native_DRC",
            "native_CH027_airwire_delta",
            "native_CH027_open_item_details_before",
            "native_CH027_open_item_details_after",
            "native_DRC_qualified",
            "protected_originals_restituted",
            '"fabrication_release": False', '"accepted": False',
        ):
            self.assertIn(token, code)
        for token in ("make_via(", "ExportDrill", "ExportGerbers"):
            self.assertNotIn(token, code)

if __name__ == "__main__":
    unittest.main()

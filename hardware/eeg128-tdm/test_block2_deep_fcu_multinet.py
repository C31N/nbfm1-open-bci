#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static fail-closed deep Block2 three-net cut and restitution checks."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_deep_fcu_multinet.py")

class DeepBlock2Test(unittest.TestCase):
    def test_three_net_native_release_gates(self) -> None:
        text = SOURCE.read_text()
        for x in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "CH025_N_MUX", "CH027_N_MUX", "CH022_N_ELECTRODE",
            "MUX_EN", "full_eight_net_bbox_mm",
            "all_bbox_FCu_inventory", "deep_cut_order_UUIDs",
            "after_cut_components", "victim_restitution",
            "same_free_component", "add_path",
            "native_target_open", "unconnected\": 136",
            "regressed_nets", "exact_native_difference",
            "native_In1_exact", "native_L3_exact",
            "new_vias_added", "all_originals_restituted",
            '"accepted": False', '"fabrication_release": False',
            "independent_replay_verified",
        ):
            self.assertIn(x, text)
        for forbidden in (
            "make_via(", "ExportGerbers", "ExportDrill",
            "ExportBOM", "ExportCPL", "SetLayer(pcbnew.In1_Cu)",
        ):
            self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()

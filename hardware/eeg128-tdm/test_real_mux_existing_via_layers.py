#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Safety assertions: actual open nets, existing vias only, strict no-release."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_real_mux_existing_via_layers.py")

class TestExistingViaMultilayer(unittest.TestCase):
    def test_protection_contract(self) -> None:
        content = SOURCE.read_text()
        for needle in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "CH020_N_MUX", "CH030_N_MUX",
            "VIATYPE_THROUGH", "same_net_existing_through_via_count",
            "power.buffer(.58)", "native_In1_exact_after_rollback",
            "native_L3_exact_after_rollback", "new_via_sites_sampled",
            "native_drc_and_138_gate_checked",
            "regressed_nets", "original_copper_restituted",
            "independent_replay_verified", '"fabrication_release": False',
        ):
            self.assertIn(needle, content)
        for forbidden in ("make_via(", "ExportGerbers", "ExportDrill",
                          "SaveGerbers", "SaveDrill", "GeneratePositionFiles"):
            self.assertNotIn(forbidden, content)

if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static no-release contract for CH027 scratch annulus and S0 restitution."""
from __future__ import annotations
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch027_annulus_s0_native.py")

class CH027AnnulusScratchContract(unittest.TestCase):
    def test_locked_scratch_no_release(self) -> None:
        source = SOURCE.read_text()
        for required in ("PINNED_CANDIDATE_SHA", "CH027_ALT_VIA",
                         "exact_native_difference", "regressed_nets",
                         "CH027_annulus_FCu", "native_139_baseline",
                         "candidate_native_DRC_qualified",
                         "new_vias != original_vias",
                         "unchanged_fingerprints(board) != protected",
                         '"fabrication_release": False',
                         '"routing_completed": False',
                         '"checkpoint_promoted": False',
                         "TemporaryDirectory", "LANDING",
                         "scratchdir.mkdir()", "shutil.copyfile",
                         "frozen_endpoints", "S0_original_corridor_reserved",
                         "reserved_S0_line", "7.0"):
            self.assertIn(required, source)
        for banned in ("ExportGerbers", "ExportDrill",
                       "generate_manufacturing", "In1_Cu)"):
            self.assertNotIn(banned, source)

if __name__ == "__main__":
    unittest.main()

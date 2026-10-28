#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static release-boundary tests of native scratch-only multihop routing."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).with_name("probe_mux_en_multihop_route.py")

class MultiHopScratchContract(unittest.TestCase):
    def test_syntax_gating_and_restitution(self) -> None:
        code=SOURCE.read_text()
        parsed=ast.parse(code)
        functions={item.name for item in parsed.body
                   if isinstance(item,ast.FunctionDef)}
        self.assertTrue({"run","find_leg"}<=functions)
        for marker in ("CH019_BCu_restituted_on_scratch",
                       "native_L3_both_difference_sets_empty",
                       "protected_original_tracks_unchanged",
                       "CH027_fixed_via_unchanged",
                       "schematic_parity_qualified",
                       "independent_replay_verified",
                       "canonicalize_new_copper_uuids",
                       "raw_PCB_geometry_unchanged_except_new_UUID_atoms",
                       "native(", "regressed_nets"):
            self.assertIn(marker,code)
    def test_no_release_or_manufacture(self) -> None:
        code=SOURCE.read_text()
        for phrase in ("ExportGerbers", "ExportDrill", "ExportBOM",
                       "fabrication_release\": True",
                       "accepted\": True"):
            self.assertNotIn(phrase,code)
        self.assertIn('"accepted": False',code)
        self.assertIn('"fabrication_release": False',code)
        self.assertIn("TemporaryDirectory(",code)

if __name__=="__main__":
    unittest.main()

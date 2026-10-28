#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static contract for strictly non-promoting MUX_EN multihop geometry."""
from __future__ import annotations
import ast
import unittest
from pathlib import Path

FILE=Path(__file__).with_name("probe_mux_en_multihop.py")


class MultihopFailClosed(unittest.TestCase):
    def test_syntax_and_completeness(self) -> None:
        src=FILE.read_text()
        module=ast.parse(src)
        names={n.name for n in module.body if isinstance(n,ast.FunctionDef)}
        self.assertTrue({"run","grid_candidates"} <= names)
        self.assertIn("exact_native_difference",src)
        self.assertIn("original_track_inventory_restored",src)
        self.assertIn("protected_original_fingerprint_unchanged",src)
        self.assertIn("In1_Cu_used",src)
        self.assertIn("MUX_S2",src)
        self.assertIn("MUX_S3",src)

    def test_no_manufacturing_or_promotion(self) -> None:
        src=FILE.read_text()
        for forbidden in ("ExportGerbers","ExportDrill","ExportBOM",
                          "fabrication_release\": True",
                          "accepted\": True"):
            self.assertNotIn(forbidden,src)
        self.assertIn('"accepted": False',src)
        self.assertIn('"fabrication_release": False',src)
        self.assertIn('TemporaryDirectory(',src)

if __name__=="__main__":
    unittest.main()

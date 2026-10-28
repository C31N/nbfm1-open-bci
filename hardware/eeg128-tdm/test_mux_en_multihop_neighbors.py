#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed static conditions for read-only MUX neighbor probe."""
from __future__ import annotations
import ast
import unittest
from pathlib import Path

PATH = Path(__file__).with_name("probe_mux_en_multihop_neighbors.py")

class FCuNeighborContract(unittest.TestCase):
    def test_readonly_and_restitution(self) -> None:
        source = PATH.read_text()
        functions = {x.name for x in ast.parse(source).body
                     if isinstance(x, ast.FunctionDef)}
        self.assertTrue({"probe", "main"} <= functions)
        for token in ("PINNED_CANDIDATE_SHA",
                      "original_copper_restored", "track_inventory",
                      "S2_S3_originals_preserved", "no_FCu_mesh_in_reviewed_margin",
                      "schematic_parity_qualified"):
            self.assertIn(token, source)
        self.assertNotIn("SaveBoard(", source)
        self.assertNotIn("ExportGerbers", source)

if __name__ == "__main__":
    unittest.main()

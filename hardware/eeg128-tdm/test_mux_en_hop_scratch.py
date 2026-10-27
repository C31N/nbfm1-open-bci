#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static fail-closed regression tests for scratch-only MUX_EN trial."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

TARGET = Path(__file__).with_name("probe_mux_en_hop_scratch.py")


class ScratchNativeContract(unittest.TestCase):
    def test_source_syntax_and_exact_protected_paths(self) -> None:
        source = TARGET.read_text()
        parsed = ast.parse(source)
        self.assertTrue(any(isinstance(n, ast.FunctionDef)
                            and n.name == "qualify" for n in parsed.body))
        self.assertIn("0832ca70-347c-5b2d-b8d9-c8fff7096f8a", source)
        self.assertIn("exact_native_difference", source)
        self.assertIn("regressed_nets", source)
        self.assertIn("CH019_original_track_restituted", source)

    def test_explicit_no_acceptance_or_manufacturing(self) -> None:
        source = TARGET.read_text()
        self.assertIn('"fabrication_release": False', source)
        self.assertIn('"routing_completed": False', source)
        self.assertIn('"accepted": False', source)
        self.assertIn('"manufacturing_export_invoked": False', source)
        self.assertIn("TemporaryDirectory(", source)
        self.assertNotIn("gerber", source.lower())
        self.assertNotIn("export gerber", source.lower())


if __name__ == "__main__":
    unittest.main()

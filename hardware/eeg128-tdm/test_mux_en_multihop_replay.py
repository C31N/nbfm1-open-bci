#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed static checks of two-pass MUX_EN route source replay."""
from __future__ import annotations
import ast
import unittest
from pathlib import Path

FILE=Path(__file__).with_name("probe_mux_en_multihop_replay.py")

class ReplayAuditContract(unittest.TestCase):
    def test_requires_two_independent_runs_and_original_sha(self):
        source=FILE.read_text()
        names={item.name for item in ast.parse(source).body
               if isinstance(item, ast.FunctionDef)}
        self.assertTrue({"replay","uuid_difference","main"}<=names)
        for token in ('for iteration in (1, 2)', 'ARCHIVE_SHA256',
                      'BOARD_SHA256', 'member_byte_identity',
                      'CH027_fixed_via_unchanged', 'candidate_native_DRC',
                      'native_L3_both_difference_sets_empty'):
            self.assertIn(token, source)

    def test_fail_closed_on_nonidentical_replay(self):
        source=FILE.read_text()
        self.assertIn('"independent_replay_bytes_differ_fail_closed"',source)
        self.assertIn('"fabrication_release": False',source)
        self.assertNotIn('ExportGerbers',source)
        self.assertNotIn('ExportDrill',source)

if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed static contract for 201-victim CH038 N-body scratch router."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_nbody_201.py")


class NBody201Tests(unittest.TestCase):
    def test_valid_python_with_all_no_release_gates(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        ast.parse(text)
        for required in (
            'accepted=False', 'routing_completed=False',
            'fabrication_release=False', 'checkpoint_promoted=False',
            'independent_replay_verified=False',
            'schematic_parity_qualified=False',
            'new_vias_added=0',
            'native_candidate_DRC', 'candidate_qualified_136',
            '"violations": 0, "warnings": 0, "unconnected": 136',
        ):
            self.assertIn(required, text)

    def test_exact_201_and_ch038_only_ripup(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for required in (
            "if len(removed) != 201",
            "upperbound_movable(tr.GetNetname())",
            "set(removed) | set(CH038)",
            'tr.GetNetname() != "CH038_P_MUX"',
            "initial_unmodified", "unchanged_fingerprints(board)",
            'victims_restored_original_geometry',
            'victims_routed_new_geometry',
            'blocked_victim_UUIDs',
            'attempted_victim_UUIDs',
            'victims_requiring_new_routing',
            'target_nets_routed',
            'for net in order:',
            'for uid in collided:',
        ):
            self.assertIn(required, text)
        self.assertNotIn('make_via(', text)
        self.assertNotIn('SetLayer(pcbnew.In1_Cu)', text)

    def test_process_and_replay_gates(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for required in (
            'subprocess.run(', 'independent_drc(',
            'isolated_drc(', 'TemporaryDirectory(',
            'file_hash(archive) == original_sha',
            'and report["source_unchanged"]',
            'not_parity_L3_or_replay_qualified',
            'scratch_board_ready_for_independent_DRC',
            'range(len(ORDERS))',
        ):
            self.assertIn(required, text)
        for forbidden in ('ExportGerbers(', 'ExportDrill(',
                          'ExportBOM(', 'ExportCPL('):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

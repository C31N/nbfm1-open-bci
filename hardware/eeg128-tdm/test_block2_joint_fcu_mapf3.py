#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Strict regression: genuine shared-state three-agent A*, never release."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOLVER = (ROOT / "probe_block2_joint_fcu_mapf3.py").read_text()
PIPE = (ROOT / "probe_block2_nbody_201.py").read_text()


class JointMAPF3Tests(unittest.TestCase):
    def test_joint_state_contains_all_three_routes(self) -> None:
        ast.parse(SOLVER)
        ast.parse(PIPE)
        for expected in (
            "def simultaneous_fcu_astar3(",
            "len(endpoints) != 3",
            "len(nets) != 3",
            "all_partial_paths_in_one_state",
            "heads,partial,turn",
            "heads,partial,turn",
            "initial=(starts3,paths,0)",
            "paths2=(next_paths[0],next_paths[1],next_paths[2])",
            "if collision(head,nxt,other_paths):",
            "if all(heads[i]==goals3[i] for i in range(3))",
            "joint_three_FCu_paths_found_unverified",
            "joint_3_state_budget_exhausted",
            "new_vias_added",
        ):
            self.assertIn(expected, SOLVER)
        for forbidden in ("make_via(", "pcbnew.In1_Cu", "ExportGerbers(",
                          "ExportDrill(", "SetLayer(", "SaveBoard("):
            self.assertNotIn(forbidden, SOLVER)

    def test_pipeline_three_targets_then_exact_201_restitution(self) -> None:
        for expected in (
            '"joint_three_enabled": joint_three',
            'simultaneous_fcu_astar3(',
            'joint_endpoints = tuple(opens[n] for n in order)',
            'joint_codes = tuple(board.FindNet(n).GetNetCode() for n in order)',
            '"mapf3_joint_solver_returned"',
            '"mapf3_joint_three_rejected"',
            'set(record["target_nets_routed"]) != set(TARGETS)',
            '"three_targets_completed_restoration_stage_entered"',
            'for uid in collided:',
            '"blocked_victim_UUIDs"',
            '"CH038_pre_return_native_DRC"',
            '"unconnected": 136',
            '"candidate_qualified_136"',
            '"fabrication_release": False',
            '"--joint-three"',
        ):
            self.assertIn(expected, PIPE)
        self.assertNotIn("make_via(", PIPE)

    def test_never_promote_on_geometric_result(self) -> None:
        self.assertIn('"qualified":False', SOLVER)
        self.assertIn('all_partial_paths_in_one_state', SOLVER)
        self.assertIn('"source_unchanged"', PIPE)
        self.assertIn('independent_replay_verified=False', PIPE)
        self.assertIn('fabrication_release=False', PIPE)
        self.assertIn('schematic_parity_qualified=False', PIPE)


if __name__ == "__main__":
    unittest.main()

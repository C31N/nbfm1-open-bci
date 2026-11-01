#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CBS3 multi-net no-release and two-sided conflict branching contracts."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CBS = (ROOT / "probe_block2_cbs_fcu3.py").read_text()
BODY = (ROOT / "probe_block2_nbody_201.py").read_text()


class CBS3Tests(unittest.TestCase):
    def test_spatial_cbs_has_true_disjunctive_branching(self) -> None:
        ast.parse(CBS)
        ast.parse(BODY)
        for term in (
            "def spatial_cbs_fcu3(",
            "len(endpoints) != 3",
            "len(nets) != 3",
            "def low_level(",
            "def first_conflict(",
            "for agent,prohibited in ((i,ei),(j,ej)):",
            "newer[agent]=limits_by_net[agent] | forbidden_edges",
            "newpaths[agent]=reroute",
            "simultaneous_three_net_conflict_search",
            "CBS3_joint_FCu_candidate_unverified",
            "CBS3_conflict_tree_budget_exhausted",
            '"qualified":False',
        ):
            self.assertIn(term, CBS)
        for forbidden in ("make_via(", "SaveBoard(", "pcbnew.In1_Cu",
                          "ExportGerbers(", "ExportDrill("):
            self.assertNotIn(forbidden, CBS)

    def test_conflict_volume_and_exact_clearance_are_bounded(self) -> None:
        for required in (
            'selection: str = "length"',
            'selection in ("length", "conflict-volume")',
            'clearance_threshold = .300 - 1e-9',
            'if d<clearance_threshold:',
            'if line_i.distance(line_j)>=clearance_threshold:',
            'length_cost + 250.0*overlap',
            'copper[i].intersection(copper[j]).area',
        ):
            self.assertIn(required, CBS)
        self.assertIn('cbs_selection: str = "length"', BODY)
        self.assertIn('selection=cbs_selection', BODY)
        self.assertIn('"cbs_selection": cbs_selection', BODY)

    def test_corridor_bundle_is_optional_and_fail_closed(self) -> None:
        for term in (
            'split_mode: str = "single-edge"',
            'split_mode in ("single-edge", "corridor-bundle")',
            'for agent,prohibited in ((i,ei),(j,ej)):',
            'if split_mode == "corridor-bundle":',
            'if segment.distance(rival_line) < clearance_threshold',
            'forbidden_edges |= frozenset(local[:6])',
            'if dist <= 1.05',
            '"last_corridor_bundle_original_overlap_edges"',
            '"last_corridor_bundle_edge_count"',
        ):
            self.assertIn(term, CBS)
        for term in (
            'cbs_split_mode: str = "single-edge"',
            'split_mode=cbs_split_mode',
            '"cbs_split_mode": cbs_split_mode',
            'cbs_split_mode=a.cbs_split_mode',
        ):
            self.assertIn(term, BODY)

    def test_nbody_runs_cbs_before_restitution(self) -> None:
        for term in (
            '"cbs_three_enabled": cbs_three',
            "if joint_three and cbs_three:",
            'from probe_block2_cbs_fcu3 import spatial_cbs_fcu3',
            "routes, diagnostic = spatial_cbs_fcu3(",
            '"CBS3_solver_returned"',
            '"CBS3_joint_three_rejected"',
            '"three_targets_completed_restoration_stage_entered"',
            'for uid in collided:',
            '"blocked_victim_UUIDs"',
            '"CH038_pre_return_native_DRC"',
            '"candidate_qualified_136"',
            '*(["--cbs-three"] if cbs_three else [])',
        ):
            self.assertIn(term, BODY)
        self.assertNotIn("make_via(", BODY)


if __name__ == "__main__":
    unittest.main()

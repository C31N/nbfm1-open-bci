#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed checks for the scratch medial Voronoi macro router."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
MACRO=(ROOT/"probe_block2_macro_voronoi.py").read_text()
BODY=(ROOT/"probe_block2_nbody_201.py").read_text()


class MacroBlock2Tests(unittest.TestCase):
    def test_real_medial_obstacle_components_and_path_segmentation(self) -> None:
        ast.parse(MACRO)
        ast.parse(BODY)
        for term in (
            "def _components(",
            "def _chamfer_distance(",
            "def macro_routes(",
            '"component_counts_by_net"',
            '"medial_ridge_nodes_by_net"',
            "ridge[y,x]=True",
            "blocked=contains_xy(geom,gx,gy)",
            "labels,sizes=_components(blocked)",
            "dist=_chamfer_distance(blocked)",
            'lane_for={"CH028_N_MUX":0,"CH029_N_MUX":1,"CH030_N_MUX":2}',
            "waypoints=[course[i] for i in indices]",
            "indices=sorted(set(round((len(course)-1)*q/4) for q in (1,2,3)))",
            'planned[net]=waypoints',
            'if set(planned)!=set(TARGETS):',
            '"macro_three_waypoint_corridors_preplanned"',
            'for net in order:',
                        "hop_points=[endpoints[net][0]]+waypoints+[endpoints[net][1]]",
            "for start,goal in zip(hop_points,hop_points[1:]):",
            "if hop is None:",
            '"micro_hop_search_attempts"',
            "(3.8,30000,15.)",
            "if (candidate is not None and len(candidate)>=2",
            "layers=(pcbnew.F_Cu,pcbnew.B_Cu)",
            '"macro_three_targets_proposed_unverified"',
            '"native_drc_required":True',
        ):
            self.assertIn(term,MACRO)
        for forbidden in ("make_via(", "pcbnew.In1_Cu", "ExportGerbers(",
                          "ExportDrill(", "SaveBoard("):
            self.assertNotIn(forbidden,MACRO)

    def test_macro_starts_restoration_only_after_all_micro_hops(self) -> None:
        for term in (
            '"macro_three_enabled": macro_three',
            'sum((bool(joint_three), bool(cbs_three), bool(macro_three))) > 1',
            "from probe_block2_macro_voronoi import macro_routes",
            "macro_routes(",
            '"macro_three_solver_returned"',
            '"macro_three_not_routable_with_bounded_waypoints"',
            '"macro_three_proposed_paths_ready_for_all_201_restoration"',
            'for net in TARGETS',
            '"three_targets_completed_restoration_stage_entered"',
            "for uid in collided:",
            '"blocked_victim_UUIDs"',
            '"CH038_pre_return_native_DRC"',
            '"candidate_qualified_136"',
            '"--macro-three"',
        ):
            self.assertIn(term,BODY)
        self.assertNotIn("make_via(",BODY)


if __name__=="__main__":
    unittest.main()

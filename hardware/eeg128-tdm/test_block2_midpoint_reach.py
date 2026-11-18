#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded F.Cu midpoint global-component gating (no-release tests)."""
from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
from shapely.geometry import box

from probe_block2_fcu_reachability import reachable_midpoint_grid_mask

ROOT=Path(__file__).resolve().parent


class MidpointFreePolygonTests(unittest.TestCase):
    def test_midpoint_uses_only_exact_shared_polygon(self) -> None:
        xs=np.linspace(0.,12.,121)
        ys=np.linspace(0.,10.,101)
        roi=box(0.,0.,12.,10.)
        barrier=box(5.8,2.0,6.2,8.0)
        mask,diag,_=reachable_midpoint_grid_mask(
            roi,barrier,(2.,5.),(10.,5.),xs,ys)
        self.assertIsNotNone(mask)
        self.assertTrue(diag["shared_component"])
        self.assertTrue(diag["global_FCu_polygon_gate_applied"])
        self.assertGreater(diag["reachable_grid_nodes"],0)
        self.assertFalse(bool(mask[50,60]))
        self.assertTrue(bool(mask[10,20]))
        self.assertTrue(bool(mask[10,100]))
        self.assertFalse(diag["route_qualified"])

    def test_native_cut_fails_before_midpoint_routing(self) -> None:
        xs=np.linspace(0.,12.,121)
        ys=np.linspace(0.,10.,101)
        mask,diag,witness=reachable_midpoint_grid_mask(
            box(0.,0.,12.,10.),box(5.8,-1.,6.2,11.),
            (2.,5.),(10.,5.),xs,ys)
        self.assertIsNone(mask)
        self.assertFalse(diag["shared_component"])
        self.assertEqual(diag["reachable_grid_nodes"],0)
        self.assertEqual(diag["continuous_polygon_components"],2)
        self.assertAlmostEqual(diag["min_component_gap_mm"],.4)
        self.assertAlmostEqual(witness[0][0],5.8)
        self.assertAlmostEqual(witness[1][0],6.2)
        self.assertIn("bounded_ROI_only",
                      diag["region_boundary_qualifier"])

    def test_native_workflow_requires_polygon_and_UUID_gates(self) -> None:
        cbs=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        reach=(ROOT/"probe_block2_fcu_reachability.py").read_text()
        # Native workflow stays in GitHub repository root.
        workflow=ROOT.parents[1]/".github/workflows/block2-u4-fanout.yml"
        self.assertTrue(workflow.exists())
        wf=workflow.read_text()
        for token in (
            "reachable_midpoint_grid_mask(",
            "midpoint_all_three_shared_components",
            "midpoint_global_polygon_reachability",
            "midpoint_native_UUID_cut_witnesses",
            "CBS3_midpoint_global_FCu_components_disconnected",
            "mask |= ~reachable",
            "post_reservation_component_cut_samples",
            "macro_future_hard_reservation_radius_mm",
            "macro_future_strict_masks",
            "historical_alternatives",
            "macro_history_diversification_count",
        ):
            self.assertIn(token,cbs)
        for token in (
            "return raster,result,witness",
            "continuous_free_reachability(",
            "native_shape_constraints_preserved",
        ):
            self.assertIn(token,reach)
        for token in (
            "test_block2_midpoint_reach.py",
            "midpoint_polygon_constrained_A_star",
        ):
            self.assertIn(token,wf)
        for unsafe in ("SaveBoard(", "ExportGerbers(", "ExportDrill(",
                       "SetNetCode(", "make_via(", "SetLayer("):
            self.assertNotIn(unsafe,reach)


if __name__=="__main__":
    unittest.main()

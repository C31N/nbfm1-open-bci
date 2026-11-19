#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only staged hybrid three-net local corridor diagnostics."""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import GeometryCollection,box

from probe_block2_hybrid_midpoint import (
    WindowBox,_window_slices,hybrid_fcu_preflight,
)

ROOT=Path(__file__).resolve().parent


class HybridMidpointTests(unittest.TestCase):
    def setUp(self)->None:
        self.xs=np.arange(0.,9.00001,.20)
        self.ys=np.arange(0.,7.00001,.20)
        self.starts=((5,8),(5,17),(5,26))
        self.goals=((30,8),(30,17),(30,26))
        self.empty=tuple(GeometryCollection() for _ in range(3))

    def make(self,shapes:tuple[object,...])->tuple[list[object],tuple[object,...]]:
        xx,yy=np.meshgrid(self.xs,self.ys)
        masks=[contains_xy(shape,xx,yy) for shape in shapes]
        tips=tuple(((float(self.xs[a[0]]),float(self.ys[a[1]])),
                    (float(self.xs[b[0]]),float(self.ys[b[1]])))
                   for a,b in zip(self.starts,self.goals))
        return masks,tips

    def test_all_three_have_hard_sequential_copper_reservations(self)->None:
        masks,tips=self.make(self.empty)
        routes,diag=hybrid_fcu_preflight(
            masks,list(self.empty),self.xs,self.ys,
            self.starts,self.goals,tips,
            hotspot=(4.,3.5),budget_seconds=7.)
        self.assertIsNotNone(routes,diag)
        self.assertEqual(len(routes),3)
        self.assertEqual(diag["stage_used"],"sequential")
        self.assertFalse(diag["planar_order_hard_pruning"])
        self.assertTrue(diag["joint_wall_cost_on_preinflated_shapes"])
        self.assertGreaterEqual(
            diag["minimum_complete_centreline_mm"],.300-1e-8)
        self.assertTrue(diag["native_DRC_still_required"])
        self.assertEqual(diag["new_vias_added"],0)

    def test_impenetrable_barrier_is_fail_closed(self)->None:
        shape=box(3.,-.4,3.5,7.4)
        shapes=(shape,shape,shape)
        masks,tips=self.make(shapes)
        routes,diag=hybrid_fcu_preflight(
            masks,list(shapes),self.xs,self.ys,
            self.starts,self.goals,tips,
            hotspot=(3.2,3.5),budget_seconds=5.)
        self.assertIsNone(routes)
        self.assertEqual(diag["stage_used"],"failed")
        self.assertFalse(diag["geometry_unsatisfiable_proven"])
        self.assertIn("anchor_a_star_reasons",diag)
        self.assertIn("anchor_attempts",diag)
        self.assertIn("local_joint_status",diag)
        self.assertIn("local_joint_anchor_audit",diag)
        self.assertFalse(diag["planar_order_hard_pruning"])
        self.assertEqual(diag["new_vias_added"],0)

    def test_window_slices_do_not_imply_rip_up_of_locked_escapes(self)->None:
        nodes=((0,0),(5,5),(10,10),(15,15))
        win=WindowBox(.7,.7,2.2,2.2)
        self.assertEqual(
            _window_slices(nodes,self.xs,self.ys,win),(1,2))
        self.assertEqual(
            _window_slices(nodes,self.xs,self.ys,
                           WindowBox(5.,5.,6.,6.)),None)

    def test_no_pcb_writes_or_vias(self)->None:
        s=(ROOT/"probe_block2_hybrid_midpoint.py").read_text()
        for term in (
            "local_rip_reroute",
            "local_joint_astar",
            "resolve_window_anchors(",
            "anchor_resolution.as_diagnostic()",
            "speculative_outside=True",
            "reassemble_speculative_outside(",
            "outside_replan_diagnostic",
            "hybrid_unresolved_global_joint_fallback_required",
            "line.distance(other)<.300-1e-8",
            "restrict_to_window=True",
            "native_DRC_still_required",
        ):
            self.assertIn(term,s)
        for forbidden in (
            "pcbnew.SaveBoard(","ExportGerbers(","ExportDrill(",
            "SetPosition(","make_via("):
            self.assertNotIn(forbidden,s)


if __name__=="__main__":
    unittest.main()

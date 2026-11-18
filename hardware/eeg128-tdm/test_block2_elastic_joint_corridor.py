#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression tests for three-head simultaneous F.Cu EDT corridor search."""
from __future__ import annotations

import time
import unittest
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import GeometryCollection,LineString,box

from probe_block2_elastic_joint_corridor import (
    BundleState,FCuCorridorGrid,ElasticJointCorridorRouter,
)

ROOT=Path(__file__).resolve().parent


class ElasticJointCorridorTests(unittest.TestCase):
    def setUp(self)->None:
        self.xs=np.arange(0.,10.00001,.20)
        self.ys=np.arange(0.,8.00001,.20)
        self.start=((2,10),(2,17),(2,24))
        self.goal=((29,10),(29,17),(29,24))
        self.empty=(GeometryCollection(),)*3

    def _make_grid(self,shapes:tuple[object,object,object]
                   )->FCuCorridorGrid:
        gx,gy=np.meshgrid(self.xs,self.ys)
        masks=[contains_xy(shape,gx,gy) for shape in shapes]
        return FCuCorridorGrid(masks,shapes,self.xs,self.ys)

    def test_three_heads_simultaneously_close_without_false_release(self)->None:
        grid=self._make_grid(self.empty)
        solver=ElasticJointCorridorRouter(grid)
        tips=tuple((grid.physical(a),grid.physical(b))
                   for a,b in zip(self.start,self.goal))
        geometry=[tuple(tips[0]),tuple(tips[1]),tuple(tips[2])]
        h=grid.lock_escape_segments(geometry)
        res=solver.solve_midpoint(
            self.start,self.goal,exact_tips=tips,
            max_expansions=11000,max_seconds=9.)
        self.assertEqual(res["status"],"MIDPOINT_BUNDLE_SOLVED",res)
        self.assertEqual(res["closed_nets"],3)
        self.assertTrue(grid.verify_escape_integrity(geometry))
        self.assertEqual(grid.locked_escape_sha256,h)
        self.assertTrue(res["native_DRC_still_required"])
        self.assertFalse(res["accepted"])
        self.assertFalse(res["routing_completed"])
        self.assertFalse(res["fabrication_release"])
        self.assertEqual(res["new_vias_added"],0)
        self.assertGreaterEqual(
            res["minimum_complete_centreline_mm"],.300-1e-8)
        self.assertEqual(len(res["routes"]),3)
        self.assertEqual(tuple(p[0] for p in res["routes"]),self.start)
        self.assertEqual(tuple(p[-1] for p in res["routes"]),self.goal)

    def test_native_exact_segment_collision_is_not_raster_only(self)->None:
        # Thin intruding copper can lie between free grid centres.
        shape=box(1.055,0.,1.075,8.)
        grid=self._make_grid((shape,)*3)
        self.assertFalse(grid.is_segment_drc_clear(0,(5,10),(6,10)))
        self.assertTrue(grid.is_point_drc_clear(0,(5,10)))
        self.assertTrue(grid.is_point_drc_clear(0,(6,10)))

    def test_hard_fcu_barrier_and_bounded_failure(self)->None:
        shape=box(3.,-.3,3.5,8.3)
        grid=self._make_grid((shape,)*3)
        tips=tuple((grid.physical(a),grid.physical(b))
                   for a,b in zip(self.start,self.goal))
        res=ElasticJointCorridorRouter(grid).solve_midpoint(
            self.start,self.goal,exact_tips=tips,
            max_expansions=250,max_seconds=6.)
        self.assertNotEqual(res["status"],"MIDPOINT_BUNDLE_SOLVED")
        self.assertEqual(res["closed_nets"],0)
        self.assertFalse(res["geometry_unsatisfiable_proven"])
        self.assertEqual(res["checkpoint_preserved"],139)

    def test_hash_detects_single_escape_waypoint_mutation(self)->None:
        grid=self._make_grid(self.empty)
        sealed=(((1.,2.),(2.,3.)),((3.,4.),(4.,5.)))
        h=grid.lock_escape_segments(sealed)
        self.assertEqual(len(h),64)
        self.assertTrue(grid.verify_escape_integrity(sealed))
        mutated=(((1.,2.),(2.,3.001)),((3.,4.),(4.,5.)))
        self.assertFalse(grid.verify_escape_integrity(mutated))

    def test_parallel_and_stagger_modes_are_available(self)->None:
        grid=self._make_grid(self.empty)
        router=ElasticJointCorridorRouter(grid)
        grid.build_distance_field()
        state=BundleState(*self.start,heading=0,mode="PARALLEL")
        neighbours=router._neighbors(state)
        self.assertTrue(neighbours)
        self.assertTrue(any(x.mode=="PARALLEL" for x in neighbours))
        self.assertTrue(any(x.mode=="STAGGERED_PINCH" for x in neighbours))

    def test_no_board_mutation_and_fail_closed_parent_gates(self)->None:
        solver=(ROOT/"probe_block2_elastic_joint_corridor.py").read_text()
        cbs=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        nbody=(ROOT/"probe_block2_nbody_201.py").read_text()
        for word in (
            "class ElasticJointCorridorRouter:",
            "distance_transform_edt",
            "PITCH_MM = .300",
            "native_DRC_still_required",
            "def lock_escape_segments(",
            "def verify_escape_integrity(",
            "MIDPOINT_BUNDLE_SOLVED",
            "MIDPOINT_PINCH_CORRIDOR_EXHAUSTED",
        ):
            self.assertIn(word,solver)
        for word in (
            "ElasticJointCorridorRouter(",
            "elastic_joint_corridor_diagnostic",
            "combined_immutable_escape_sha256",
            "elastic_joint_corridor_sha256_after",
            '"MIDPOINT_BUNDLE_SOLVED"',
        ):
            self.assertIn(word,cbs)
        for word in (
            "validate_fcu_three_paths(",
            "three_targets_completed_restoration_stage_entered",
            "blocked_victim_UUIDs",
            "fully_restituted",
            "candidate_qualified_136",
        ):
            self.assertIn(word,nbody)
        for unsafe in (
            "SaveBoard(","ExportGerbers(","ExportDrill(",
            "make_via(","SetNetCode(","SetLayer(","SetPosition(",
        ):
            self.assertNotIn(unsafe,solver)


if __name__=="__main__":
    unittest.main()

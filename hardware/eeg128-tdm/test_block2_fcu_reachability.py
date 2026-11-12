#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact continuous native F.Cu reachability; fail-closed regression tests."""
from __future__ import annotations

from pathlib import Path
import time
import unittest

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString,box

from probe_block2_fcu_reachability import (
    component_at,continuous_free_reachability,polygon_components,
)
from probe_block2_target_coupled import coupled_target_open_space_escapes

ROOT=Path(__file__).resolve().parent


class FcuReachabilityTests(unittest.TestCase):
    def test_exact_polygon_split_and_witness(self) -> None:
        roi=box(0.,0.,10.,10.)
        cut=box(4.5,-1.,5.5,11.)
        comps=polygon_components(roi.difference(cut))
        self.assertEqual(len(comps),2)
        self.assertIsNotNone(component_at(comps,(2.,5.)))
        comp,diag,witness=continuous_free_reachability(
            roi,cut,(2.,5.),(8.,5.))
        self.assertIsNone(comp)
        self.assertFalse(diag["shared_component"])
        self.assertEqual(diag["continuous_polygon_components"],2)
        self.assertEqual(diag["min_component_gap_mm"],1.)
        self.assertEqual(round(witness[0][0],3),4.5)
        self.assertEqual(round(witness[1][0],3),5.5)
        self.assertIn(
            "bounded_ROI_only",diag["region_boundary_qualifier"])

    def test_continuous_route_around_finite_barrier(self) -> None:
        roi=box(0.,0.,10.,10.)
        middle=box(4.5,2.,5.5,8.)
        comp,diag,_=continuous_free_reachability(
            roi,middle,(2.,5.),(8.,5.))
        self.assertIsNotNone(comp)
        self.assertTrue(diag["shared_component"])
        self.assertEqual(diag["continuous_polygon_components"],1)
        self.assertTrue(comp.covers(LineString(
            ((2.,1.),(8.,1.))).interpolate(.5,normalized=True)))

    def test_port_outside_free_polygon_cannot_be_claimed_reachable(self) -> None:
        roi=box(0.,0.,10.,10.)
        source_inside_blocker=box(.5,.5,2.5,2.5)
        comp,diag,_=continuous_free_reachability(
            roi,source_inside_blocker,(1.,1.),(8.,8.))
        self.assertIsNone(comp)
        self.assertIsNone(diag["u4_component_index"])
        self.assertFalse(diag["shared_component"])

    def test_target_goals_filtered_by_global_reachable_polygon(self) -> None:
        xs=np.arange(-8.,8.00001,.15)
        ys=np.arange(-3.,13.00001,.15)
        gx,gy=np.meshgrid(xs,ys)
        ports=((0.,1.5),(0.,4.5),(0.,7.5))
        shapes=[box(-7.,10.,7.,12.)]*3
        masks=[contains_xy(s,gx,gy) for s in shapes]
        # All candidate endpoints must remain inside this exact shared
        # free component, rather than a fixed short-offset target lane.
        global_roi=box(-7.,-2.,7.,9.5)
        comps=(global_roi,global_roi,global_roi)
        tips=((-6.,-1.),(-6.,2.),(-6.,5.))
        paths,diag=coupled_target_open_space_escapes(
            masks,shapes,xs,ys,ports,tangent=1,outward=-1.,
            deadline=time.monotonic()+6.,max_expanded=30000,
            reachable_components=comps,u4_macro_tips=tips)
        self.assertIsNotNone(paths,diag)
        self.assertTrue(diag["global_fcu_reachability_required"])
        self.assertEqual(len(paths),3)
        for wire in paths:
            self.assertTrue(global_roi.covers(
                LineString(wire).interpolate(1.,normalized=True)))
        forbidden=box(6.,10.,7.,11.)
        with self.assertRaisesRegex(
            ValueError,"Invalid three-target topological source"):
            coupled_target_open_space_escapes(
                masks,shapes,xs,ys,ports,1,-1.,
                deadline=time.monotonic()+1.,
                reachable_components=(global_roi,None,forbidden),
                u4_macro_tips=tips)

    def test_postseal_joint_reachability_required_before_acceptance(self) -> None:
        xs=np.arange(-8.,8.00001,.15)
        ys=np.arange(-3.,13.00001,.15)
        gx,gy=np.meshgrid(xs,ys)
        ports=((0.,1.5),(0.,4.5),(0.,7.5))
        shapes=[box(-7.,10.,7.,12.)]*3
        masks=[contains_xy(shape,gx,gy) for shape in shapes]
        roi=box(-7.,-2.,7.,9.5)
        comps=(roi,roi,roi)
        tips=((-6.,-1.),(-6.,2.),(-6.,5.))
        checks=[]
        def rejected(
            paths:tuple[tuple[tuple[float,float],...],...],
        ) -> tuple[bool,dict[str,object]]:
            checks.append(tuple(len(p) for p in paths))
            return False,{"reason":"fabricated_joint_seal_disconnection"}
        paths,diag=coupled_target_open_space_escapes(
            masks,shapes,xs,ys,ports,tangent=1,outward=-1.,
            deadline=time.monotonic()+6.,max_expanded=30000,
            reachable_components=comps,u4_macro_tips=tips,
            postseal_validator=rejected)
        self.assertIsNone(paths)
        self.assertGreaterEqual(len(checks),1)
        self.assertGreaterEqual(
            diag["outcomes"]["postseal_continuous_component_disconnected"],1)
        self.assertFalse(diag["geometry_unsatisfiable_proven"])
        self.assertTrue(diag["postseal_failed_candidates"])

    def test_native_no_release_and_cut_witness_contract(self) -> None:
        source=(ROOT/"probe_block2_fcu_reachability.py").read_text()
        target=(ROOT/"probe_block2_target_escape.py").read_text()
        for token in (
            "allowed_roi.difference(inflated_fixed_copper)",
            "native_reachability_components(",
            "obstacles(board,net,.15,.15",
            "native_copper_UUID_witnesses",
            "witness_is_min_cut_proof",
            "geometry_unsatisfiable_proven",
            "same_continuous_FCu_component",
        ):
            self.assertIn(token,source)
        for token in (
            "native_reachability_components(",
            "Target_global_FCu_reachability_blocked",
            "reachable_components=global_components",
            "u4_macro_tips=bundle_targets",
            "all_target_tips_same_component_as_U4",
        ):
            self.assertIn(token,target)
        for file in (source,target):
            for forbidden in (
                "make_via(","SaveBoard(","ExportGerbers(",
                "ExportDrill(","SetLayer(","SetNetCode("):
                self.assertNotIn(forbidden,file)


if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed regression tests for immutable mutual F.Cu reservations."""
from __future__ import annotations

import time
from pathlib import Path
import unittest

from shapely.geometry import GeometryCollection, LineString

from probe_block2_mutual_reservation import (
    CLEARANCE_CENTRE_MM,
    mutually_reserved_macro_search,
)

ROOT=Path(__file__).resolve().parent


class MutualReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixed=(GeometryCollection(),)*3
        self.frozen=(
            LineString(((0.,-10.),(0.,-12.))),
            LineString(((1.,-10.),(1.,-12.))),
            LineString(((2.,-10.),(2.,-12.))),
        )

    def test_three_routes_are_reserved_incrementally_and_in_order(self) -> None:
        observed=[]
        def route(agent,previous):
            observed.append((agent,len(previous)))
            if len(previous)>0:
                self.assertTrue(all(isinstance(v,LineString)
                                    for v in previous))
            return ((agent,3),(agent,4))
        def line(agent,path):
            return LineString(((agent,3.),(agent,4.)))
        routes,diag=mutually_reserved_macro_search(
            route,line,self.fixed,self.frozen,
            deadline=time.monotonic()+3.)
        self.assertIsNotNone(routes)
        self.assertEqual(observed,[(0,0),(1,1),(2,2)])
        self.assertEqual(diag["status"],
                         "three_macro_paths_reserved_unverified")
        self.assertEqual(diag["ordering"],(0,1,2))
        self.assertEqual(diag["locked_U4_escape_count"],3)
        self.assertEqual(diag["new_vias_added"],0)
        self.assertGreaterEqual(
            diag["minimum_post_escape_centreline_mm"],
            CLEARANCE_CENTRE_MM)
        self.assertTrue(diag["native_DRC_still_required"])
        self.assertFalse(diag["fully_restituted"])

    def test_all_orders_fail_closed_on_occupied_same_copper(self) -> None:
        def route(agent,previous):
            return ((agent,0),(agent,1))
        def line(agent,path):
            return LineString(((0.,0.),(0.,3.)))
        routes,diag=mutually_reserved_macro_search(
            route,line,self.fixed,self.frozen,
            deadline=time.monotonic()+5.)
        self.assertIsNone(routes)
        self.assertEqual(diag["orders_started"],6)
        self.assertEqual(diag["max_orders"],6)
        self.assertEqual(diag["status"],
                         "mutual_macro_reservation_bounded_no_solution")
        self.assertEqual(
            diag["macro_search_counts"]["reserved_macro_clearance_violation"],6)
        self.assertFalse(diag["geometry_unsatisfiable_proven"])
        self.assertEqual(diag["new_vias_added"],0)

    def test_native_hard_obstacle_rejects_before_reservation(self) -> None:
        forbidden=(LineString(((0.,0.),(0.,2.))).buffer(.25),
                   GeometryCollection(),GeometryCollection())
        def route(agent,previous):
            return ((agent,0),(agent,1))
        def line(agent,path):
            return LineString(((float(agent),0.),
                               (float(agent),2.)))
        routes,diag=mutually_reserved_macro_search(
            route,line,forbidden,self.frozen,
            deadline=time.monotonic()+4.,max_orders=1)
        self.assertIsNone(routes)
        self.assertEqual(diag["orders_started"],1)
        self.assertGreaterEqual(
            diag["macro_search_counts"]["native_copper_segment_collision"],1)

    def test_native_macro_entry_is_sealed_and_no_cbs_ripup(self) -> None:
        cbs=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        nbody=(ROOT/"probe_block2_nbody_201.py").read_text()
        for token in (
            "from probe_block2_mutual_reservation import (",
            "mutually_reserved_macro_search(",
            "reserved_copper=unary_union(",
            "mask = mask | contains_xy(reserved_copper,gx,gy)",
            '"mutual-reservation" if fanout_wires is not None else split_mode',
            "u4_immutable_fanout_sha256",
            "u4_fanout_sha256_after_macro",
            "u4_full_fanout_vertices_retained",
            "post_escape_macros_all_reserved",
            "CBS3_post_escape_mutual_reservation_bounded_no_solution",
            "CBS3_geometry_unsatisfiable_proven",
        ):
            self.assertIn(token,cbs)
        for token in (
            "validate_fcu_three_paths(",
            "three_targets_completed_restoration_stage_entered",
            "blocked_victim_UUIDs",
            "fully_restituted",
            "candidate_qualified_136",
        ):
            self.assertIn(token,nbody)
        helper=(ROOT/"probe_block2_mutual_reservation.py").read_text()
        for unsafe in ("make_via(", "SaveBoard(", "ExportGerbers(",
                       "ExportDrill(", "SetLayer(", "SetNetCode("):
            self.assertNotIn(unsafe,helper)


if __name__=="__main__":
    unittest.main()

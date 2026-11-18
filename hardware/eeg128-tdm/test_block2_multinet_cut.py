#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded optimistic F.Cu multi-net mincut diagnostic regressions."""
from __future__ import annotations

import unittest
import numpy as np

from probe_block2_multinet_cut import optimistic_fcu_three_net_cut


class FcuThreeNetCutTests(unittest.TestCase):
    def test_obvious_one_vertex_bridge_is_detected(self) -> None:
        blocked=np.ones((12,12),dtype=bool)
        blocked[:,0:4]=False
        blocked[5,4:8]=False
        blocked[:,8:12]=False
        starts=[(1,2),(1,5),(1,8)]
        goals=[(10,2),(10,5),(10,8)]
        xs=np.arange(12,dtype=float)*.22
        ys=np.arange(12,dtype=float)*.22
        for relaxed in (False,True):
            result=optimistic_fcu_three_net_cut(
                [blocked.copy() for _ in range(3)],starts,goals,
                xs,ys,diagonal_corner_override=relaxed)
            self.assertEqual(
                result["optimistic_max_vertex_disjoint_paths"],1)
            self.assertEqual(result["vertex_cut_size"],1)
            self.assertEqual(
                result["status"],
                "optimistic_FCu_raster_vertex_cut_below_three")
            self.assertFalse(
                result["native_continuous_FCu_impossibility_proven"])
            self.assertFalse(result["fabrication_release"])

    def test_open_field_has_three_separate_paths(self) -> None:
        blocked=np.zeros((15,15),dtype=bool)
        xs=np.arange(15,dtype=float)*.22
        ys=np.arange(15,dtype=float)*.22
        result=optimistic_fcu_three_net_cut(
            [blocked.copy() for _ in range(3)],
            [(1,2),(1,7),(1,12)],
            [(13,2),(13,7),(13,12)],xs,ys)
        self.assertEqual(
            result["optimistic_max_vertex_disjoint_paths"],3)
        self.assertEqual(
            result["status"],
            "optimistic_grid_capacity_at_least_three")
        self.assertFalse(result["routing_completed"])
        self.assertTrue(
            result["ignored_required_0_300mm_centreline_spacing"])

    def test_invalid_raster_and_anchor_fail_closed(self) -> None:
        blocked=np.zeros((15,15),dtype=bool)
        xs=np.arange(15,dtype=float)
        ys=np.arange(15,dtype=float)
        with self.assertRaisesRegex(RuntimeError,"Exactly three"):
            optimistic_fcu_three_net_cut(
                [blocked],[(1,1)]*3,[(13,13)]*3,xs,ys)
        with self.assertRaisesRegex(RuntimeError,"Invalid F.Cu"):
            optimistic_fcu_three_net_cut(
                [blocked.copy() for _ in range(3)],
                [(17,1)]*3,[(13,13)]*3,xs,ys)


if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Safe planar ordering, wall costs and exact midpoint-band tests."""
from __future__ import annotations

import unittest

from probe_block2_joint_topology_costs import (
    JointHeuristic,PlanarOrderFilter,WallHuggingCost,
    conflict_window,find_midpoint_connection,octile_distance,
)


class JointTopologyCostsTests(unittest.TestCase):
    def test_unproven_axis_cannot_cut_valid_detour(self)->None:
        start=((0.,0.),(0.,1.),(0.,2.))
        goal=((5.,0.),(5.,1.),(5.,2.))
        order=PlanarOrderFilter(start,goal,(0.,1.))
        self.assertFalse(order.hard)
        allowed,penalty=order.evaluate(
            ((2.,2.),(2.,1.),(2.,0.)))
        self.assertTrue(allowed)
        self.assertGreater(penalty,0.)

    def test_certified_monotone_window_can_filter_inversion(self)->None:
        start=((0.,0.),(0.,1.),(0.,2.))
        goal=((5.,0.),(5.,1.),(5.,2.))
        order=PlanarOrderFilter(
            start,goal,(0.,1.),
            certified_monotone_region=True)
        allowed,_=order.evaluate(((2.,2.),(2.,1.),(2.,0.)))
        self.assertFalse(allowed)

    def test_wall_hugger_uses_already_inflated_distance(self)->None:
        wall=WallHuggingCost(lambda _i,p:abs(p[0]),
                             hug_band_mm=.5,hug_weight=.2)
        self.assertEqual(wall.cost(0,(0.,0.)),0.)
        self.assertAlmostEqual(wall.cost(0,(.25,0.)),.1)
        self.assertAlmostEqual(wall.cost(0,(2.,0.)),.2)
        self.assertEqual(len(wall.cache),3)

    def test_octile_gate_is_preference_not_hard_obstacle(self)->None:
        h=JointHeuristic(
            ((4.,0.),(4.,1.),(4.,2.)),
            gate_point=(2.,.5),gate_x_threshold=2.,
            corridor_capacity=1,congestion_weight=.4,
            epsilon=1.2)
        self.assertGreater(h.estimate(
            ((0.,0.),(0.,1.),(0.,2.))),0.)
        self.assertAlmostEqual(octile_distance((0.,0.),(2.,2.)),
                               2.**.5*2.)

    def test_midpoint_requires_exact_bridge_validation(self)->None:
        forward={((0.,0.),(0.,1.),(0.,2.)):0.}
        back={((.3,0.),(.3,1.),(.3,2.)):0.}
        self.assertIsNone(find_midpoint_connection(
            forward,back,max_gap_mm=.5,
            exact_bridge_validate=lambda _a,_b:False))
        self.assertIsNotNone(find_midpoint_connection(
            forward,back,max_gap_mm=.5,
            exact_bridge_validate=lambda _a,_b:True))

    def test_window_and_safety_module(self)->None:
        b=conflict_window()
        self.assertTrue(b.contains((48.145,35.75)))
        self.assertFalse(b.contains((0.,0.)))


if __name__=="__main__":
    unittest.main()

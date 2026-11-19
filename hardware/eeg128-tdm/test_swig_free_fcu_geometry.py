#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression tests for exact SWIG-independent primitive clearance."""
from __future__ import annotations

import math
import unittest

from swig_free_fcu_geometry import (
    CuPrimitive,Vec2,closest_points_between_segments,
    compute_max_tracks,primitive_distance,
)


def track(y:float,*,x1:float=0.,x2:float=10.,width:float=.2)->CuPrimitive:
    return CuPrimitive("TRACK",Vec2(x1,y),Vec2(x2,y),width/2.)


def via(x:float,y:float,*,diameter:float=.6)->CuPrimitive:
    p=Vec2(x,y)
    return CuPrimitive("VIA",p,p,diameter/2.)


def pad(x:float,y:float,*,w:float=2.,h:float=1.,
        angle:float=0.,kind:str="RECT_PAD")->CuPrimitive:
    p=Vec2(x,y)
    return CuPrimitive(kind,p,p,0.,w,h,math.radians(angle))


class SWIGFreeGeometryTests(unittest.TestCase):
    def test_capsule_parallel_clearance(self)->None:
        centre,gap,a,b=primitive_distance(track(0.),track(1.))
        self.assertAlmostEqual(centre,1.)
        self.assertAlmostEqual(gap,.8)
        self.assertAlmostEqual((a-b).norm(),.8)

    def test_perpendicular_segments_and_overlaps(self)->None:
        a=CuPrimitive("TRACK",Vec2(0.,0.),Vec2(4.,0.),.1)
        b=CuPrimitive("TRACK",Vec2(2.,-2.),Vec2(2.,2.),.1)
        centre,gap,_,_=primitive_distance(a,b)
        self.assertEqual(centre,0.)
        self.assertAlmostEqual(gap,-.2)

    def test_via_to_track_clearance(self)->None:
        centre,gap,a,b=primitive_distance(via(5.,2.),track(0.))
        self.assertAlmostEqual(centre,2.)
        self.assertAlmostEqual(gap,1.6)
        self.assertAlmostEqual((a-b).norm(),1.6)

    def test_rectangle_circle_no_sampling(self)->None:
        centre,gap,_,_=primitive_distance(
            pad(0.,0.),via(1.65,0.,diameter=.3))
        self.assertAlmostEqual(centre,.65)
        self.assertAlmostEqual(gap,.5)

    def test_rotated_oval_circle_no_sampling(self)->None:
        centre,gap,_,_=primitive_distance(
            pad(0.,0.,w=2.,h=1.,angle=90.,kind="OVAL_PAD"),
            via(1.15,0.,diameter=.3))
        self.assertAlmostEqual(centre,1.15,places=9)
        self.assertAlmostEqual(gap,.5,places=9)

    def test_capsule_rectangle_minimum_at_endpoint(self)->None:
        a=CuPrimitive("TRACK",Vec2(-2.,1.5),Vec2(-1.5,1.5),.1)
        b=pad(0.,0.,w=2.,h=2.)
        centre,gap,_,_=primitive_distance(a,b)
        self.assertAlmostEqual(centre,math.hypot(.5,.5))
        self.assertAlmostEqual(gap,math.hypot(.5,.5)-.1)

    def test_rotated_rectangles_and_containment(self)->None:
        a=pad(0.,0.,w=2.,h=1.,angle=30.)
        b=pad(4.,0.,w=2.,h=1.,angle=-30.)
        centre,gap,_,_=primitive_distance(a,b)
        self.assertGreater(gap,0.)
        self.assertAlmostEqual(centre,gap)
        _,overlap,_,_=primitive_distance(a,pad(0.,0.,w=.1,h=.1))
        self.assertEqual(overlap,0.)

    def test_near_tangent_capacity_uses_unrounded_gap(self)->None:
        self.assertEqual(compute_max_tracks(.152312,.15,.15),(0,0))
        self.assertEqual(compute_max_tracks(1.05,.15,.15),(3,3))
        self.assertEqual(compute_max_tracks(1.049,.15,.15)[0],2)

    def test_degenerate_segment_no_division_by_zero(self)->None:
        p=Vec2(0.,0.)
        a,b,d=closest_points_between_segments(
            p,p,Vec2(1.,0.),Vec2(2.,0.))
        self.assertEqual(a,p)
        self.assertEqual(b,Vec2(1.,0.))
        self.assertEqual(d,1.)

    def test_reject_nonfinite_and_unsupported(self)->None:
        with self.assertRaises(ValueError):
            CuPrimitive("ARC",Vec2(0.,0.),Vec2(1.,0.),.1)
        with self.assertRaises(ValueError):
            compute_max_tracks(float("nan"),.15,.15)
        with self.assertRaises(ValueError):
            pad(0.,0.,w=0.)


if __name__=="__main__":
    unittest.main()

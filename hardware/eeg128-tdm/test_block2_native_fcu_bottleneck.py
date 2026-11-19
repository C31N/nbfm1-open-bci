#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure regression gates for read-only native KiCad hot-spot analyzer."""
from __future__ import annotations

from pathlib import Path
import unittest

from shapely.geometry import box

from probe_block2_native_fcu_bottleneck import (
    NativeObject,gap_capacity,measure,
)


class NativeFcuBottleneckTests(unittest.TestCase):
    def test_exact_three_trace_capacity_requires_two_wall_clearances(self)->None:
        self.assertEqual(gap_capacity(1.05)["max_tracks_strict"],3)
        self.assertEqual(gap_capacity(1.049)["max_tracks_strict"],2)
        self.assertEqual(gap_capacity(.75)["max_tracks_strict"],2)
        self.assertEqual(gap_capacity(.74)["max_tracks_strict"],1)
        self.assertEqual(gap_capacity(.299)["max_tracks_strict"],0)

    def test_strict_and_optimistic_caps_are_not_confused(self)->None:
        cap=gap_capacity(.9)
        self.assertEqual(cap["max_tracks_strict"],2)
        self.assertEqual(cap["max_tracks_edge_to_edge"],3)

    def test_real_polygons_yield_exact_closest_segment_points(self)->None:
        a=NativeObject("pad-uuid","PAD","U3/13","MUX_S3",
                       box(0,0,1,1),"SHAPE_POLY_SET_native_0.0001mm")
        b=NativeObject("via-uuid","VIA","VIA","CH040_N_MUX",
                       box(1.8,0,2.8,1),"SHAPE_POLY_SET_native_0.0001mm")
        pairs=measure([a,b])
        self.assertEqual(len(pairs),1)
        self.assertAlmostEqual(pairs[0]["clear_gap_mm"],.8)
        self.assertEqual(pairs[0]["max_tracks_strict"],2)
        self.assertEqual({pairs[0]["uuid_a"],pairs[0]["uuid_b"]},
                         {"pad-uuid","via-uuid"})
        self.assertTrue(pairs[0]["both_native_polygonized"])

    def test_same_net_overlap_does_not_fake_gap_bottleneck(self)->None:
        a=NativeObject("1","TRACK","a","same",box(0,0,1,1),
                       "SHAPE_POLY_SET_native_0.0001mm")
        b=NativeObject("2","TRACK","b","same",box(.5,0,1.5,1),
                       "SHAPE_POLY_SET_native_0.0001mm")
        self.assertEqual(measure([a,b]),[])

    def test_conservative_fallback_is_not_called_native(self)->None:
        a=NativeObject("a","PAD","U3/13","MUX_S3",box(0,0,1,1),
                       "conservative_bbox_fallback:TypeError")
        b=NativeObject("b","VIA","VIA","CH040_N_MUX",box(2,0,3,1),
                       "SHAPE_POLY_SET_native_0.0001mm")
        self.assertFalse(measure([a,b])[0]["both_native_polygonized"])

    def test_straight_copper_avoids_unsupported_swig_transform(self)->None:
        from types import SimpleNamespace
        from probe_block2_native_fcu_bottleneck import _copper

        class FakePcbnew:
            @staticmethod
            def ToMM(value:int)->float:
                return value/1_000_000

        class CopperItem:
            def GetWidth(self)->int:
                return 150_000

            def GetPosition(self)->SimpleNamespace:
                return SimpleNamespace(x=0,y=0)

            def GetStart(self)->SimpleNamespace:
                return SimpleNamespace(x=0,y=0)

            def GetEnd(self)->SimpleNamespace:
                return SimpleNamespace(x=1_000_000,y=0)

            def TransformShapeToPolygon(self,*args:object)->None:
                raise AssertionError("Do not use broken KiCad 8 SWIG")

        for kind in ("TRACK","VIA"):
            with self.subTest(kind=kind):
                shape,grade=_copper(CopperItem(),kind,FakePcbnew)
                self.assertEqual(grade,"SWIG_free_closed_form")
                self.assertGreater(shape.area,0.)

    def test_exact_pair_uses_primitives_not_display_polygons(self)->None:
        from swig_free_fcu_geometry import CuPrimitive,Vec2
        a=CuPrimitive("TRACK",Vec2(0.,0.),Vec2(4.,0.),.1)
        b=CuPrimitive("TRACK",Vec2(0.,1.),Vec2(4.,1.),.1)
        objects=[
            NativeObject("a","TRACK","A","N1",box(0,0,5,5),
                         "SWIG_free_closed_form",a),
            NativeObject("b","TRACK","B","N2",box(0,0,5,5),
                         "SWIG_free_closed_form",b),
        ]
        gap=measure(objects)[0]
        self.assertTrue(gap["closed_form_exact"])
        self.assertEqual(gap["gap_measurement_source"],
                         "closed_form_primitive_pair_exact")
        self.assertAlmostEqual(gap["clear_gap_mm"],.8)

    def test_never_mutates_board_or_claims_global_impossibility(self)->None:
        s=(Path(__file__).resolve().parent/
           "probe_block2_native_fcu_bottleneck.py").read_text()
        for word in (
            "pcbnew.SHAPE_POLY_SET()",
            "TransformShapeToPolygon(",
            "GetFilledPolysList(pcbnew.F_Cu)",
            "native_global_three_net_unroutability_proven",
            "pcb_sha256_before_and_after",
            "max_tracks_edge_to_edge",
            "tightest_clear_gap_mm",
            "tightest_gap_is_fully_native_polygonized",
            "tightest_fully_native_clear_gap_mm",
            "source_board_unchanged",
        ):
            self.assertIn(word,s)
        for forbidden in (
            "pcbnew.SaveBoard(","pcbnew.ZONE_FILLER(",
            "ExportGerbers(","ExportDrill(","SetNetCode(","SetPosition("):
            self.assertNotIn(forbidden,s)


if __name__=="__main__":
    unittest.main()

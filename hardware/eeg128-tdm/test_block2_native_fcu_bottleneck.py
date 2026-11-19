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

    def test_kicad8_track_via_arc_native_polygon_overload(self)->None:
        # Regression: the SHAPE.ConvertToPolygon path produced
        # AttributeError for every track/via on native KiCad 8.0.9.
        from types import SimpleNamespace
        from probe_block2_native_fcu_bottleneck import _copper

        class PolySet:
            def __init__(self)->None:
                self.points=[]

            def OutlineCount(self)->int:
                return int(bool(self.points))

            def Outline(self,index:int)->"PolySet":
                return self

            def PointCount(self)->int:
                return len(self.points)

            def CPoint(self,index:int)->SimpleNamespace:
                return SimpleNamespace(
                    x=self.points[index][0],y=self.points[index][1])

            def HoleCount(self,index:int)->int:
                return 0

        class FakePcbnew:
            F_Cu=0
            ERROR_INSIDE=1
            SHAPE_POLY_SET=PolySet

            @staticmethod
            def FromMM(value:float)->int:
                return round(value*1_000_000)

            @staticmethod
            def ToMM(value:int)->float:
                return value/1_000_000

        class CopperItem:
            def __init__(self)->None:
                self.calls=0

            def GetEffectiveShape(self,*args:object)->object:
                raise AssertionError("Do not use unsupported SWIG SHAPE")

            def TransformShapeToPolygon(
                self,poly:PolySet,layer:int,clearance:int,error:int,error_loc:int
            )->None:
                self.calls+=1
                if (layer,clearance,error,error_loc)!=(0,0,100,1):
                    raise TypeError("Incorrect KiCad 8 transform overload")
                poly.points=[
                    (0,0),(1_000_000,0),
                    (1_000_000,1_000_000),(0,1_000_000),
                ]

            def GetWidth(self)->int:
                return 150_000

            def GetPosition(self)->SimpleNamespace:
                return SimpleNamespace(x=0,y=0)

            def GetStart(self)->SimpleNamespace:
                return SimpleNamespace(x=0,y=0)

            def GetEnd(self)->SimpleNamespace:
                return SimpleNamespace(x=1_000_000,y=0)

        # Exercise both the newer binding and KiCad 8's enum-unexported
        # SWIG module without weakening the hard source DRC constraints.
        old_binding=SimpleNamespace(
            F_Cu=FakePcbnew.F_Cu,
            SHAPE_POLY_SET=PolySet,
            FromMM=FakePcbnew.FromMM,
            ToMM=FakePcbnew.ToMM,
        )
        for kind in ("TRACK","VIA","ARC"):
            with self.subTest(kind=kind,legacy=False):
                item=CopperItem()
                geometry,grade=_copper(item,kind,FakePcbnew)
                self.assertEqual(item.calls,1)
                self.assertEqual(grade,"SHAPE_POLY_SET_native_0.0001mm")
                self.assertAlmostEqual(geometry.area,1.)

        for kind in ("TRACK","VIA"):
            with self.subTest(kind=kind,legacy=True):
                item=CopperItem()
                geometry,grade=_copper(item,kind,old_binding)
                self.assertEqual(item.calls,0)
                self.assertEqual(
                    grade,"native_segment_circle_analytic_approximation:"
                          "KiCad8_ERROR_LOC_unavailable")
                self.assertGreater(geometry.area,0.)

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

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed U4 dog-leg geometry and protected routing contracts."""
from __future__ import annotations

import math
from pathlib import Path
import unittest

from shapely.geometry import LineString, box

from probe_block2_u4_dogleg import (
    U3_PAD7_UUID, build_u4_lateral_dogleg,
)

ROOT = Path(__file__).resolve().parent


class U4LateralDoglegTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ports = ((2.54,0.),(0.,0.),(1.27,0.))
        self.endpoints = tuple(
            ((pad[0],-25.),pad) for pad in self.ports)
        self.u3_bounds = (.8,-3.8,1.2,-2.7)

    def test_order_independent_three_stages_and_exact_pitch(self) -> None:
        wires,sides,normal,diag=build_u4_lateral_dogleg(
            self.ports,self.endpoints,self.u3_bounds,
            side=-1,lateral_mm=-3.2,escape_mm=.25,
            dogleg_run_mm=1.2)
        self.assertEqual(sides,(1,1,1))
        self.assertEqual(normal,(0.,-1.))
        self.assertEqual(
            diag["stages"],
            ["isolated_escape","lateral_dogleg","parallel_bundle"])
        self.assertEqual(diag["tip_pitch_mm"],.300)
        self.assertEqual(diag["parallel_length_mm"],1.5)
        self.assertEqual(diag["dogleg_side"],-1)
        self.assertTrue(diag["no_new_vias"])
        self.assertTrue(diag["physical_DRC_still_required"])
        self.assertEqual(set(w[0] for w in wires),set(self.ports))
        for wire in wires:
            self.assertEqual(len(wire),6)
            self.assertAlmostEqual(
                math.dist(wire[-2],wire[-1]),1.5,places=8)
        tips=sorted(w[-1][0] for w in wires)
        self.assertAlmostEqual(tips[1]-tips[0],.300,places=8)
        self.assertAlmostEqual(tips[2]-tips[1],.300,places=8)
        pad=box(*self.u3_bounds)
        for wire in wires:
            self.assertGreaterEqual(
                LineString(wire).distance(pad),.225-1e-8)
        self.assertGreaterEqual(
            min(LineString(wires[i]).distance(LineString(wires[j]))
                for i in range(3) for j in range(i+1,3)),.300-1e-8)

    def test_longer_isolated_escape_clears_adjacent_pad_row(self) -> None:
        # Longer initial straight copper postpones lateral motion until the
        # neighbouring U4 pad row has been left; no protection is disabled.
        wires,sides,normal,diagnostic=build_u4_lateral_dogleg(
            self.ports,self.endpoints,self.u3_bounds,
            side=-1,lateral_mm=-3.2,escape_mm=1.70,
            dogleg_run_mm=1.20)
        self.assertEqual(sides,(1,1,1))
        self.assertEqual(normal,(0.,-1.))
        self.assertTrue(diagnostic["extended_pad_escape_search"])
        for wire in wires:
            self.assertAlmostEqual(
                math.dist(wire[0],wire[1]),1.70,places=8)
            self.assertGreaterEqual(
                LineString(wire).distance(box(*self.u3_bounds)),
                .225-1e-8)
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                self.ports,self.endpoints,self.u3_bounds,
                side=-1,lateral_mm=-3.2,escape_mm=2.30,
                dogleg_run_mm=1.20)

    def test_staggered_pin_17_escape_preserves_pad_order(self) -> None:
        wires,sides,normal,diagnostic=build_u4_lateral_dogleg(
            self.ports,self.endpoints,self.u3_bounds,
            side=1,lateral_mm=3.2,
            escape_mm=(.65,1.70,.65),dogleg_run_mm=1.2)
        # Input order is pin 19, 17, 18: only pin 17 is extended.
        self.assertEqual(sides,(1,1,1))
        self.assertEqual(normal,(0.,-1.))
        self.assertTrue(diagnostic["staggered_isolated_escapes"])
        self.assertEqual(tuple(diagnostic["escape_lengths_mm"]),
                         (.65,1.70,.65))
        for i,wire in enumerate(wires):
            self.assertAlmostEqual(
                math.dist(wire[0],wire[1]),
                diagnostic["escape_lengths_mm"][i],places=8)
            self.assertGreaterEqual(
                LineString(wire).distance(box(*self.u3_bounds)),
                .225-1e-8)
        self.assertGreaterEqual(
            min(LineString(wires[i]).distance(LineString(wires[j]))
                for i in range(3) for j in range(i+1,3)),.300-1e-8)
        self.assertEqual(diagnostic["tip_pitch_mm"],.300)
        self.assertEqual(diagnostic["parallel_length_mm"],1.5)

    def test_bad_candidate_is_rejected_without_board_changes(self) -> None:
        kwargs=dict(side=-1,lateral_mm=-3.2,escape_mm=.25,
                    dogleg_run_mm=1.2)
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                self.ports,self.endpoints,self.u3_bounds,
                **(kwargs | {"escape_mm":.01}))
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                self.ports,self.endpoints,self.u3_bounds,
                **(kwargs | {"lateral_mm":3.2}))
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                self.ports,self.endpoints,self.u3_bounds,
                **(kwargs | {"pitch_mm":.299}))
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                self.ports,self.endpoints,self.u3_bounds,
                **(kwargs | {"parallel_mm":1.0}))
        with self.assertRaises(RuntimeError):
            build_u4_lateral_dogleg(
                ((0.,0.),(.2,0.),(.4,0.)),
                self.endpoints,self.u3_bounds,**kwargs)

    def test_immutable_u3_ch027_and_l3_release_contract(self) -> None:
        src=(ROOT/"probe_block2_u4_dogleg.py").read_text()
        cbs=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        workflow=(ROOT.parent.parent/".github/workflows/block2-u4-fanout.yml")
        # Workflow path is evaluated only as an optional structural check.
        self.assertEqual(
            U3_PAD7_UUID,"e37256fc-3b9f-435d-8042-f7d4c1147aca")
        for term in (
            "def build_u4_lateral_dogleg(",
            "def native_u4_lateral_preflight(",
            "pad_copper_shape(",
            "CH027_PINS",
            "U3_PAD7_UUID",
            'p.GetNetname()=="CH018_P_MUX"',
            "native_obstacle_preflight_passed",
            "physical_DRC_still_required",
            "obstacles(board,nets[i],.15,.15",
        ):
            self.assertIn(term,src)
        self.assertIn("native_u4_lateral_preflight(",cbs)
        self.assertIn('u4_fanout: bool = False',cbs)
        for forbidden in ("SaveBoard(", "make_via(", "ExportGerbers(",
                          "ExportDrill(", "SetLayer(", "SetNetCode("):
            self.assertNotIn(forbidden,src)
        self.assertTrue(workflow.name.endswith("block2-u4-fanout.yml"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded three-net topological U4 escape regression and no-release gates."""
from __future__ import annotations

import ast
from pathlib import Path
import time
import unittest

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from probe_block2_u4_topological import (
    _astar_grid, _route_candidates,
    GRID_MM, COPPER_CENTRE_PITCH_MM, BUNDLE_MM,
    U3_PAD7_UUID,
)

ROOT=Path(__file__).resolve().parent


class NativeTopologicalEscapeTests(unittest.TestCase):
    def test_a_star_dynamic_grid_respects_hard_copper(self) -> None:
        mask=np.zeros((18,18),dtype=bool)
        mask[:,8]=True
        mask[11,8]=False
        a,status,n=_astar_grid(
            mask,(2,2),(14,2),max_nodes=2000,
            deadline=time.monotonic()+3.)
        self.assertEqual(status,"path_found")
        self.assertIsNotNone(a)
        self.assertGreater(n,12)
        self.assertTrue(any(v[0]==8 and v[1]==11 for v in a))
        self.assertTrue(all(not mask[y,x] for x,y in a))
        mask[11,8]=True
        a,status,n=_astar_grid(
            mask,(2,2),(14,2),max_nodes=2000,
            deadline=time.monotonic()+3.)
        self.assertEqual(status,"frontier_exhausted")
        self.assertIsNone(a)

    def test_hard_bound_and_no_topology_proof(self) -> None:
        mask=np.zeros((60,60),dtype=bool)
        a,status,n=_astar_grid(
            mask,(0,0),(58,58),max_nodes=1,
            deadline=time.monotonic()+5.)
        self.assertIsNone(a)
        self.assertEqual(status,"node_budget_exhausted")
        self.assertEqual(n,1)

    def test_local_three_net_reservation_and_exact_parallel_pitch(self) -> None:
        xs=np.arange(-3.,7.5,GRID_MM)
        ys=np.arange(-9.,1.5,GRID_MM)
        gx,gy=np.meshgrid(xs,ys)
        ports=((0.,0.),(1.27,0.),(2.54,0.))
        fixed=[]
        for agent in range(3):
            others=[box(ports[j][0]-.18,-.23,
                        ports[j][0]+.18,.23).buffer(.225)
                    for j in range(3) if j!=agent]
            # An immutable center obstacle; no route is allowed through it.
            others.append(box(.75,-3.9,1.65,-2.))
            fixed.append(unary_union(others))
        masks=[contains_xy(shape,gx,gy) for shape in fixed]
        goal_y=int(round((-5.0-float(ys[0]))/GRID_MM))
        goal_x=int(round((4.4-float(xs[0]))/GRID_MM))
        wires,diag=_route_candidates(
            masks,fixed,xs,ys,ports,[(goal_x,goal_y)],
            tangent=0,normal_sign=-1,
            deadline=time.monotonic()+12.,max_expanded=75000)
        self.assertIsNotNone(wires,diag)
        self.assertEqual(len(wires),3)
        self.assertTrue(diag["no_new_vias"])
        self.assertEqual(diag["parallel_length_mm"],BUNDLE_MM)
        self.assertEqual(diag["tip_pitch_mm"],COPPER_CENTRE_PITCH_MM)
        self.assertEqual([w[0] for w in wires],list(ports))
        for i,line in enumerate(wires):
            self.assertFalse(LineString(line).relate_pattern(
                fixed[i],"T********"))
        for i in range(3):
            for j in range(i+1,3):
                self.assertGreaterEqual(
                    LineString(wires[i]).distance(LineString(wires[j])),
                    COPPER_CENTRE_PITCH_MM-1e-8)

    def test_topological_integrity_source_contract(self) -> None:
        solver=(ROOT/"probe_block2_u4_topological.py").read_text()
        cbs=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        nbody=(ROOT/"probe_block2_nbody_201.py").read_text()
        self.assertEqual(
            U3_PAD7_UUID,"e37256fc-3b9f-435d-8042-f7d4c1147aca")
        ast.parse(solver)
        for token in (
            "def native_u4_topological_preflight(",
            "def _route_candidates(",
            "def _astar_grid(",
            "CH027_PINS",
            "pad_copper_shape(",
            "obstacles(board,code,.15,.15",
            "COPPER_CENTRE_PITCH_MM-1e-8",
            "time.monotonic()>=deadline",
            "geometry_unsatisfiable_proven",
            "new_vias_added",
            "fixed_copper_unchanged",
        ):
            self.assertIn(token,solver)
        self.assertIn("native_u4_topological_preflight(",cbs)
        self.assertIn("CBS3_U4_topological_escape_preflight_blocked",cbs)
        self.assertIn("u4_fanout=u4_fanout",nbody)
        self.assertIn("for point in wire[:-1]",cbs)
        self.assertIn("reversed(wire[:-1])",cbs)
        self.assertIn("u4_full_fanout_vertices_retained",cbs)
        self.assertIn('"fully_restituted": False',nbody)
        for unsafe in (
            "make_via(", "SetLayer(", "SetNetCode(",
            "SaveBoard(", "ExportGerbers(", "ExportDrill(",
            "pcbnew.In1_Cu",
        ):
            self.assertNotIn(unsafe,solver)


if __name__=="__main__":
    unittest.main()

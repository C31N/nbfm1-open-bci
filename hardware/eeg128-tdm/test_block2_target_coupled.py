#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Non-converged paired target pad escapes: bounded topology tests."""
from __future__ import annotations

from pathlib import Path
import time
import unittest

import numpy as np
from shapely import contains_xy
from shapely.geometry import box
from shapely.ops import unary_union
from shapely.geometry import LineString

from probe_block2_target_coupled import coupled_target_open_space_escapes

ROOT=Path(__file__).resolve().parent


class CoupledTargetTests(unittest.TestCase):
    def test_three_independent_target_exits_without_premature_bundle(self) -> None:
        xs=np.arange(-8.,8.00001,.15)
        ys=np.arange(-3.,13.00001,.15)
        gx,gy=np.meshgrid(xs,ys)
        ports=((0.,1.5),(0.,4.5),(0.,7.5))
        shapes=[]
        for i in range(3):
            foreign=[
                box(ports[j][0]-.3,ports[j][1]-.3,
                    ports[j][0]+.3,ports[j][1]+.3)
                for j in range(3) if j!=i]
            # A native-style obstacle at the middle network's direct exit.
            if i==1:
                foreign.append(box(-1.7,4.,-1.0,5.))
            shapes.append(unary_union(foreign))
        masks=[contains_xy(x,gx,gy) for x in shapes]
        wires,diag=coupled_target_open_space_escapes(
            masks,shapes,xs,ys,ports,tangent=1,outward=-1.,
            deadline=time.monotonic()+5.,max_expanded=22000)
        self.assertIsNotNone(wires,diag)
        self.assertEqual(diag["status"],
                         "target_three_independent_FCu_escapes_proposed")
        self.assertEqual(len(wires),3)
        self.assertEqual([w[0] for w in wires],list(ports))
        self.assertTrue(diag["no_new_vias"])
        self.assertEqual(diag["hard_clearance_centreline_mm"],.300)
        for i in range(3):
            self.assertFalse(LineString(wires[i]).relate_pattern(
                shapes[i],"T********"))
            for j in range(i+1,3):
                self.assertGreaterEqual(
                    LineString(wires[i]).distance(LineString(wires[j])),
                    .300-1e-8)

    def test_blocked_pad_anchor_is_fail_closed(self) -> None:
        xs=np.arange(-6.,6.00001,.15)
        ys=np.arange(-6.,6.00001,.15)
        gx,gy=np.meshgrid(xs,ys)
        shape=box(-6.,-6.,6.,6.)
        masks=[contains_xy(shape,gx,gy)]*3
        wires,diag=coupled_target_open_space_escapes(
            masks,[shape]*3,xs,ys,
            ((0.,-3.),(0.,0.),(0.,3.)),
            tangent=1,outward=-1.,
            deadline=time.monotonic()+2.,max_expanded=1000)
        self.assertIsNone(wires)
        self.assertEqual(diag["status"],"target_native_pad_anchor_blocked")
        self.assertEqual(diag["best_routed_agents"],0)
        self.assertFalse(diag["geometry_unsatisfiable_proven"])

    def test_no_board_mutations_in_coupled_target_planner(self) -> None:
        s=(ROOT/"probe_block2_target_coupled.py").read_text()
        for tok in (
            "priority_orders=((1,2,0)",
            "line.buffer(.300-1e-9",
            "target_speculative_backtracks",
            "target_three_independent_FCu_escapes_proposed",
            "target_coupled_topological_bounded_no_solution",
            "geometry_unsatisfiable_proven",
        ):
            self.assertIn(tok,s)
        for tok in ("make_via(", "SaveBoard(", "SetLayer(",
                    "SetNetCode(", "ExportGerbers(", "ExportDrill("):
            self.assertNotIn(tok,s)


if __name__=="__main__":
    unittest.main()

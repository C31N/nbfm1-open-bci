#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Identity and fail-closed gates for the coupled three-pad target escape."""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase, mock

from probe_block2_target_escape import _target_pads

ROOT=Path(__file__).resolve().parent


class _Pad:
    def __init__(self,agent:int,center:tuple[float,float]):
        self.center=center
        self.net=agent+100
        self.m_Uuid=SimpleNamespace(AsString=lambda: "target-%d" % agent)

    def GetNetCode(self) -> int:
        return self.net

    def IsOnLayer(self,layer:int) -> bool:
        return layer==0

    def GetPosition(self) -> tuple[float,float]:
        return self.center


class _Footprint:
    def __init__(self,pads:list[_Pad]):
        self.pads=pads

    def Pads(self) -> list[_Pad]:
        return self.pads


class _Board:
    def __init__(self,pads:list[_Pad]):
        self.footprints=[_Footprint(pads)]

    def GetFootprints(self) -> list[_Footprint]:
        return self.footprints


class TargetTripletTests(TestCase):
    def test_target_pad_identity_never_confuses_source_and_target(self) -> None:
        centers=((15.,25.),(16.,25.),(17.,25.))
        board=_Board([_Pad(i,center)
                      for i,center in enumerate(centers)])
        endpoints=tuple(((50.+i,10.),center)
                        for i,center in enumerate(centers))
        with mock.patch.dict(sys.modules,{
            "pcbnew":SimpleNamespace(F_Cu=0),
            "route_targeted_closure":SimpleNamespace(xy=lambda p:p),
        }):
            pads,ports=_target_pads(
                board,(100,101,102),endpoints,(0,0,0))
            self.assertEqual(ports,centers)
            self.assertEqual([p.net for p in pads],[100,101,102])
            # Moving the target endpoint away MUST fail closed.
            bad=list(endpoints)
            bad[1]=(bad[1][0],(19.,30.))
            with self.assertRaisesRegex(
                RuntimeError,"native_FCu_target_pad_not_found"
            ):
                _target_pads(
                    board,(100,101,102),tuple(bad),(0,0,0))
            # A wrong net cannot quietly reuse another target pad.
            with self.assertRaisesRegex(
                RuntimeError,"native_FCu_target_pad_not_found"
            ):
                _target_pads(
                    board,(100,101,199),endpoints,(0,0,0))

    def test_source_wires_and_target_wires_are_both_hard(self) -> None:
        source=(ROOT/"probe_block2_cbs_fcu3.py").read_text()
        target=(ROOT/"probe_block2_target_escape.py").read_text()
        mutual=(ROOT/"probe_block2_mutual_reservation.py").read_text()
        for item in (
            "native_target_triplet_preflight(",
            "target_immutable_escape_sha256",
            "target_escape_sha256_after_macro",
            "target_full_escape_vertices_retained",
            "immutable_targets=frozen_targets",
            "target_triplet_deterministic_escape_diagnostic",
        ):
            self.assertIn(item,source)
        for item in (
            "GetNetCode()",
            "pad_copper_shape(",
            "native_FCu_target_pad_not_found_for_agent_",
            "target_escape_immutable_sha256",
            "target_escape_paths_mm",
            "_route_candidates(",
            "geometry_unsatisfiable_proven",
        ):
            self.assertIn(item,target)
        for item in (
            "immutable_targets:",
            "Sealed escape cluster violates pitch",
            "Source-target sealed cross-net collision",
            "locked_target_escape_count",
        ):
            self.assertIn(item,mutual)
        for forbidden in (
            "SaveBoard(", "make_via(", "ExportGerbers(", "ExportDrill(",
            "SetLayer(", "SetNetCode(", "SetPosition(",
        ):
            self.assertNotIn(forbidden,target)


if __name__=="__main__":
    import unittest
    unittest.main()

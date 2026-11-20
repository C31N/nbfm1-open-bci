#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression: real scratch geometry, not pad-centre point estimates."""
from __future__ import annotations

import unittest
from shapely.geometry import LineString

from probe_block2_native_fcu_bottleneck import NativeObject
from probe_block2_scratch_verify import (
    NETS, PITCH, RUN77, U3_UUIDS,
    directions_at_scratch, find_uuids, pos,
)
from swig_free_fcu_geometry import CuPrimitive, Vec2


class FakeUuid:
    def __init__(self, value: str) -> None:
        self.value = value

    def AsString(self) -> str:
        return self.value


class FakePad:
    def __init__(self, uuid: str, num: str, net: str) -> None:
        self.m_Uuid = FakeUuid(uuid)
        self.num = num
        self.net = net

    def GetNumber(self) -> str:
        return self.num

    def GetNetname(self) -> str:
        return self.net

    def IsOnLayer(self, _layer: object) -> bool:
        return True


class FakeFootprint:
    def __init__(self, pads: list[FakePad]) -> None:
        self.pads = pads

    def Pads(self) -> list[FakePad]:
        return self.pads

    def GetReference(self) -> str:
        return "U3"


class FakeBoard:
    def __init__(self, pads: list[FakePad]) -> None:
        self.pads = pads

    def GetFootprints(self) -> list[FakeFootprint]:
        return [FakeFootprint(self.pads)]

    def GetTracks(self) -> list[object]:
        return []

    def Zones(self) -> list[object]:
        return []


class FakePcbnew:
    F_Cu = 0

    class PCB_VIA:
        pass


class ScratchGeometryTests(unittest.TestCase):
    def test_exact_states_are_native_run77_grid(self) -> None:
        self.assertEqual(
            pos(RUN77["MAX_GOAL_PROGRESS"][2][-1]), (46.825, 34.870))
        self.assertEqual(
            pos(RUN77["STAGGERED_EVADE"][0][-1]), (46.385, 34.210))
        self.assertEqual(
            pos(RUN77["LATERAL_EVADE"][1][-1]), (46.385, 34.210))

    def test_u3_pads_found_by_real_object_uuid_and_net(self) -> None:
        names = [(uid, suffix, net)
                 for uid, (name, net) in U3_UUIDS.items()
                 for suffix in (name.split("/")[1],)]
        pads = [FakePad(uid, suffix, net)
                for uid, suffix, net in names]
        inv = find_uuids(FakeBoard(pads), FakePcbnew)
        self.assertEqual(set(inv), set(U3_UUIDS))
        for uuid, (name, net) in U3_UUIDS.items():
            self.assertEqual(inv[uuid]["name"], name)
            self.assertEqual(inv[uuid]["net"], net)

    def test_72_exact_geometry_directions_and_static_pitch(self) -> None:
        # A fixed vertical scratch F.Cu track in the CH030 right lane:
        # track-to-new-track COPPER gap, not distance to pad centre.
        p0, p1 = (47.12, 34.55), (47.12, 35.25)
        primitive = CuPrimitive(
            "TRACK", Vec2(*p0), Vec2(*p1), .075)
        native = NativeObject(
            "scratch-fixed", "TRACK", "TRACK", "MUX_S3",
            LineString((p0, p1)).buffer(.075),
            "SWIG_free_closed_form", primitive)
        states, totals = directions_at_scratch([native])
        self.assertEqual(len(states), 3)
        self.assertEqual(sum(totals.values()), 72)
        self.assertEqual(len(states[0]["direction_probes"]), 24)
        self.assertEqual(len(states[1]["joint_scratch_probes"]), 27)
        right = next(p for p in states[0]["direction_probes"]
                     if p["net"] == NETS[2] and p["heading_index"] == 0)
        self.assertEqual(
            right["scratch_classification"], "SCRATCH_FIXED_FCU_COPPER")
        self.assertEqual(
            right["closest_fcu_objects"][0]["uuid"], "scratch-fixed")
        self.assertEqual(
            right["closest_fcu_objects"][0]["provenance"],
            "actual_post_201_cut_scratch_PCB")
        self.assertLess(
            right["closest_fcu_objects"][0]["new_trace_copper_gap_mm"], .15)
        self.assertAlmostEqual(PITCH, .3)

    def test_joint_checks_are_diagnostic_not_router_gates(self) -> None:
        states, _ = directions_at_scratch([])
        for st in states:
            self.assertTrue(all(
                item["not_full_route_qualification"]
                for item in st["joint_scratch_probes"]))
            self.assertTrue(all(
                item["standalone_step_not_a_three_net_solution"]
                for item in st["direction_probes"]))


if __name__ == "__main__":
    unittest.main()

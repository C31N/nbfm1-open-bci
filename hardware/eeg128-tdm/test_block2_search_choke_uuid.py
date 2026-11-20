#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only PCB UUID correlation must remain fail closed."""
from __future__ import annotations

import unittest

from shapely.geometry import LineString

from probe_block2_native_fcu_bottleneck import NativeObject
from probe_block2_search_choke_uuid import (
    _load_states, correlate_states, rank_fcu_witnesses,
)
from swig_free_fcu_geometry import CuPrimitive, Vec2


def obj(uuid: str, net: str, y: float) -> NativeObject:
    primitive = CuPrimitive(
        "TRACK", Vec2(0., y), Vec2(.50, y), .075)
    return NativeObject(
        uuid, "TRACK", "TRACK", net,
        LineString(((0., y), (.50, y))).buffer(.075),
        "SWIG_free_closed_form", primitive)


class SearchChokeUUIDTests(unittest.TestCase):
    def test_exact_surface_gap_and_whitelist_filter(self) -> None:
        fixed = obj("fixed-uuid", "VCM", .20)
        removed = obj("removed-victim", "OTHER", .10)
        listed = rank_fcu_witnesses(
            [removed, fixed], "CH028_N_MUX",
            (0., 0.), (.50, 0.), {"removed-victim"})
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["uuid"], "fixed-uuid")
        self.assertAlmostEqual(listed[0]["new_trace_copper_gap_mm"], .05)
        self.assertAlmostEqual(listed[0][
            "new_centreline_to_obstacle_surface_mm"], .125)
        self.assertAlmostEqual(
            listed[0]["hard_clearance_deficit_mm"], .10)
        self.assertEqual(listed[0]["measurement_method"],
                         "exact_primitive_pair")

    def test_same_net_copper_does_not_falsely_block(self) -> None:
        tracks = [obj("own", "CH028_N_MUX", .0),
                  obj("other", "CH029_N_MUX", .50)]
        rows = rank_fcu_witnesses(
            tracks, "CH028_N_MUX", (0., 0.), (.50, 0.), set())
        self.assertEqual([r["uuid"] for r in rows], ["other"])

    def test_native_scratch_mask_remains_classification_authority(self) -> None:
        fixed = obj("fixed-vcm", "VCM", .20)
        state = {
            "sample_role": "MAX_GOAL_PROGRESS",
            "progress_from_third_bind_root_mm": .400441,
            "remaining_target_distance_sum_mm": 10.,
            "heads": [],
            "direction_probes": [
                {
                    "net": "CH028_N_MUX", "heading_index": 0,
                    "classification": "HARD_NATIVE_FIXED_COPPER_SEGMENT",
                    "from_mm": [0., 0.], "to_mm": [.5, 0.],
                },
                {
                    "net": "CH029_N_MUX", "heading_index": 1,
                    "classification": "HARD_OTHER_NET_TRACE_PITCH",
                    "from_mm": [0., 0.], "to_mm": [.5, 0.],
                },
            ],
        }
        rows, summary = correlate_states([state], [fixed], set())
        probes = rows[0]["direction_probes"]
        self.assertEqual(
            probes[0]["uuid_attribution"],
            "SOURCE139_UUID_POSSIBLE_NOT_SCRATCH_CERTIFIED")
        self.assertEqual(
            probes[1]["uuid_attribution"],
            "PAIR_OR_SEARCH_RULE_NOT_FIXED_COPPER")
        self.assertEqual(summary[0]["uuid"], "fixed-vcm")
        self.assertEqual(summary[0]["occurrences"], 1)

    def test_rejects_wrong_state_shape_and_unqualified_release(self) -> None:
        worker = {
            "accepted": False, "routing_completed": False,
            "fabrication_release": False,
            "cut_whitelist_UUIDs": [f"victim-{i}" for i in range(201)],
            "CH038_cut_UUIDs": ["a", "b"],
            "cbs_three_diagnostic": {
                "hybrid_corridor_diagnostic": {
                    "partial_free_diagnostic": {
                        "three_net_choke_states": [{
                            "heads": [], "direction_probes": [],
                        }],
                    }
                }
            }
        }
        candidate = {
            "source_unchanged": True, "new_vias_added": 0,
            "accepted": False, "routing_completed": False,
            "fabrication_release": False,
            "child_diagnostic": worker,
        }
        with self.assertRaises(RuntimeError):
            _load_states(candidate)
        worker["accepted"] = True
        with self.assertRaises(RuntimeError):
            _load_states(candidate)


if __name__ == "__main__":
    unittest.main()

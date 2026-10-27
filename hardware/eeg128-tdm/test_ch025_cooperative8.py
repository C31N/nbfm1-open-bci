#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Independent no-promotion and eight-net priority-set safety tests."""
from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from probe_ch025_cooperative8 import (
    FLAGS, NET, NEIGHBORS, SRC, DST, assert_locked_plan, order_schedules,
    write_evidence, _write_child_progress,
    native_staged_mux_corridor_inventory,
)


class CooperativeEightSafety(unittest.TestCase):
    def test_priority_orders_cover_exactly_eight(self) -> None:
        assert_locked_plan()
        orders = order_schedules()
        self.assertEqual(len(orders), 4)
        expected = set(NEIGHBORS.values()) | {NET}
        for order in orders:
            self.assertEqual(len(order), 8)
            self.assertEqual(set(order), expected)
        self.assertIn(NET, orders[0])
        self.assertEqual(SRC, (49.45, 14.90))
        self.assertEqual(DST, (36.105, 48.85))

    def test_atomic_child_progress_remains_nonrelease(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "child.json"
            report = {
                **FLAGS, "status": "evaluating_single_net",
                "order": list(order_schedules()[0]),
                "connected": [], "failure": {
                    "net": NET,
                    "source_mm": [49.45, 14.9],
                    "target_mm": [36.105, 48.85],
                    "trials": [{"margin_mm": 3.0,
                                "status": "native_astar_attempt_in_progress"}],
                },
            }
            _write_child_progress(path, report)
            self.assertEqual(json.loads(path.read_text())["failure"]["net"],
                             NET)
            self.assertFalse(json.loads(path.read_text())["accepted"])
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_corridor_uuid_diagnostic_is_read_only(self) -> None:
        from unittest.mock import patch
        from shapely.geometry import Point, box

        class FakeSegment:
            def GetStart(self) -> tuple[float, float]:
                return (0.0, 0.0)

            def GetEnd(self) -> tuple[float, float]:
                return (10.0, 0.0)

        source_copper = [Point(5.0, 0.0).buffer(.3)]
        objects = [{
            "uuid": "protected-test-copper",
            "net": "VCM", "kind": "track", "protected": True,
        }]
        with (
            patch("analyze_ch025_fcu_blocker_uuids.copper_shapes",
                  return_value=(source_copper, objects)),
            patch("route_targeted_closure.xy", side_effect=lambda x: x),
            patch("route_targeted_closure.routing_domain",
                  return_value=box(-2, -3, 12, 3)),
        ):
            result = native_staged_mux_corridor_inventory(
                object(), "MUX_S2", FakeSegment())
        self.assertEqual(len(result["corridors"]), 7)
        direct = result["corridors"][0]
        self.assertEqual(direct["blocked_item_count"], 1)
        self.assertEqual(direct["protected_blocker_count"], 1)
        self.assertEqual(direct["nearby"][0]["uuid"],
                         "protected-test-copper")
        self.assertFalse(result["native_DRC_qualified"])
        self.assertFalse(result["release_allowed"])

    def test_release_is_fail_closed(self) -> None:
        self.assertTrue(all(value is False for value in FLAGS.values()))

    def test_interrupted_order_evidence_is_always_nonrelease(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "partial.json"
            report = {
                **FLAGS, "status": "isolated_order_process_timeout",
                "order": list(order_schedules()[1]), "connected": [],
                "failure": {"net": None}, "native_DRC": None,
            }
            write_evidence(path, [report])
            out = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(out["orders_tried"], 1)
            self.assertEqual(out["baseline_airwires"], 139)
            self.assertFalse(out["accepted"])
            self.assertFalse(out["fabrication_release"])
            self.assertFalse(out["manufacturing_files"])
            self.assertFalse(out["independent_replay_verified"])


if __name__ == "__main__":
    unittest.main()

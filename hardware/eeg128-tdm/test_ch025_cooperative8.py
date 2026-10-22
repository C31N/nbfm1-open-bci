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
    write_evidence,
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

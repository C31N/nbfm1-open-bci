#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Safety regression tests for local vertical three-lane MUX capacity."""
import unittest
from shapely.geometry import box
from probe_mux_topological_capacity import (
    read_slices, MIN_CENTER_SEPARATION_MM, FLAGS,
)


class LocalCapacityTests(unittest.TestCase):
    def test_two_lane_gap_fails_three_lane_necessity(self):
        domain = box(0, 0, 4, 4)
        rows = read_slices(
            domain, [box(0, 0, 4, 1.5),
                     box(0, 2.05, 4, 4)],
            1, 2, 0, 4, .2)
        self.assertTrue(rows)
        self.assertTrue(all(r["maximum_independent_centerline_slots"] < 3
                            for r in rows))

    def test_three_lanes_is_only_upper_bound(self):
        domain = box(0, 0, 4, 4)
        rows = read_slices(domain, [
            box(0, 0, 4, 1.5), box(0, 2.3, 4, 4)],
            1, 2, 0, 4, .2)
        self.assertTrue(all(r["maximum_independent_centerline_slots"] >= 3
                            for r in rows))

    def test_separation_and_release_flags(self):
        self.assertGreater(MIN_CENTER_SEPARATION_MM, .3)
        for field in ("accepted", "fabrication_release",
                      "manufacturing_files", "routing_completed",
                      "native_DRC_qualified", "checkpoint_promoted"):
            self.assertFalse(FLAGS[field])

    def test_no_zero_height_or_bad_steps(self):
        with self.assertRaises(ValueError):
            read_slices(box(0,0,4,4), [], 2, 1, 0, 4)
        with self.assertRaises(ValueError):
            read_slices(box(0,0,4,4), [], 1, 2, 0, 4, 0)


if __name__ == "__main__":
    unittest.main()

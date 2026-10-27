#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Safety regression tests for local vertical three-lane MUX capacity."""
import unittest
from shapely.geometry import box
from probe_mux_topological_capacity import (
    read_slices, MIN_CENTER_SEPARATION_MM, FLAGS, assess_straight_bundle,
)


class LocalCapacityTests(unittest.TestCase):
    def test_two_lane_gap_fails_three_lane_necessity(self) -> None:
        domain = box(0, 0, 4, 4)
        rows = read_slices(
            domain, [box(0, 0, 4, 1.5),
                     box(0, 2.05, 4, 4)],
            1, 2, 0, 4, .2)
        self.assertTrue(rows)
        self.assertTrue(all(r["maximum_independent_centerline_slots"] < 3
                            for r in rows))

    def test_three_lanes_is_only_upper_bound(self) -> None:
        domain = box(0, 0, 4, 4)
        rows = read_slices(domain, [
            box(0, 0, 4, 1.5), box(0, 2.3, 4, 4)],
            1, 2, 0, 4, .2)
        self.assertTrue(all(r["maximum_independent_centerline_slots"] >= 3
                            for r in rows))

    def test_separation_and_release_flags(self) -> None:
        self.assertGreater(MIN_CENTER_SEPARATION_MM, .3)
        for field in ("accepted", "fabrication_release",
                      "manufacturing_files", "routing_completed",
                      "native_DRC_qualified", "checkpoint_promoted"):
            self.assertFalse(FLAGS[field])

    def test_unobstructed_flat_immutable_bundle(self) -> None:
        domain = box(0, 0, 100, 100)
        report = assess_straight_bundle(domain, [])
        self.assertTrue(report["pairwise_separation_pass"])
        self.assertTrue(report["static_copper_straight_bundle_feasible"])
        self.assertFalse(report["allowed_CH022_closure"])
        self.assertFalse(report["fabrication_release"])

    def test_foreign_protected_copper_blocks_flat_bundle(self) -> None:
        domain = box(0, 0, 100, 100)
        retained = [(box(33, 37.0, 34, 37.35),
                     dict(net="CH021_P_MUX", kind="via",
                          uuid="synthetic-protected", protected=True))]
        report = assess_straight_bundle(domain, retained)
        self.assertFalse(report["static_copper_straight_bundle_feasible"])
        self.assertGreater(
            next(row for row in report["candidate_lines"]
                 if row["net"] == "MUX_EN")["protected_blocker_count"], 0)
        self.assertFalse(report["checkpoint_promotion_allowed"])

    def test_no_zero_height_or_bad_steps(self) -> None:
        with self.assertRaises(ValueError):
            read_slices(box(0,0,4,4), [], 2, 1, 0, 4)
        with self.assertRaises(ValueError):
            read_slices(box(0,0,4,4), [], 1, 2, 0, 4, 0)


if __name__ == "__main__":
    unittest.main()

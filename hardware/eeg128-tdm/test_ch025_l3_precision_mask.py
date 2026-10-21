#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""No KiCad runtime needed: CH022 corridor versus ideal L3 gain mask."""
from __future__ import annotations

import unittest
from shapely.geometry import box
from analyze_ch025_l3_precision_mask import (
    FLAGS, MM2_TO_NATIVE_IU2, native_gain_compatibility,
    PROBE_28_CH022_LAYERS,
)


class L3PrecisionMaskSafety(unittest.TestCase):
    def test_reject_overlap_with_reviewed_CH022_route(self) -> None:
        report = native_gain_compatibility(box(43, 31, 44, 33))
        self.assertFalse(report['protects_reviewed_CH022_in2_corridor'])
        self.assertEqual(report['reviewed_CH022_waypoints'], 23)
        self.assertEqual(report['reviewed_CH022_transitions'], 4)

    def test_allow_disjoint_gain_mask_to_proceed_to_native_trial(self) -> None:
        report = native_gain_compatibility(box(75, 40, 76, 41))
        self.assertTrue(report['protects_reviewed_CH022_in2_corridor'])
        self.assertEqual(MM2_TO_NATIVE_IU2, 10**12)

    def test_never_accept_or_publish(self) -> None:
        self.assertTrue(all(v is False for v in FLAGS.values()))
        self.assertEqual(len(PROBE_28_CH022_LAYERS), 23)


if __name__ == '__main__':
    unittest.main()

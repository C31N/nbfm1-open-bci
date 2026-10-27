#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure free-space geometry test for B.Cu UUID gap survey."""
from __future__ import annotations

import unittest

from shapely.geometry import box
from analyze_ch025_bcu_cut_uuids import distance_gap, PROTECTED, survey


class GapGeometryTests(unittest.TestCase):
    def test_mux_bcu_gap_protection_and_parameter(self) -> None:
        from inspect import signature
        self.assertIn("CH021_P", PROTECTED)
        self.assertIn("CH010_N", PROTECTED)
        self.assertEqual(signature(survey).parameters["target_net"].default,
                         "CH025_N_MUX")

    def test_gap(self) -> None:
        data = distance_gap(box(0, 0, 1, 1), box(1.5, 0, 2, 1))
        self.assertEqual(data['gap_mm'], .5)
        self.assertEqual(data['source_edge_mm'][0], 1.0)
        self.assertEqual(data['target_edge_mm'][0], 1.5)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Validate edge-to-edge 0.505 mm power clearance, nonrelease defaults."""
from __future__ import annotations
import unittest

from probe_ch027_exact_power_endpoints import (
    endpoint_clearance, FLAGS,
)


class EndpointClearanceSafetyTests(unittest.TestCase):
    def test_equal_is_legal(self) -> None:
        r = endpoint_clearance(.580)
        self.assertTrue(r["strict_power_clearance_possible_at_this_point"])
        self.assertEqual(r["new_trace_edge_to_power_surface_mm"], .505)

    def test_below_limit_blocked(self) -> None:
        r = endpoint_clearance(.579)
        self.assertFalse(r["strict_power_clearance_possible_at_this_point"])
        self.assertLess(r["margin_mm"], 0.0)

    def test_never_promote(self) -> None:
        self.assertTrue(all(value is False for value in FLAGS.values()))


if __name__ == "__main__":
    unittest.main()

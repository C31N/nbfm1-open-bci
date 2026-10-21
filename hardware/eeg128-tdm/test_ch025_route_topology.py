#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure fail-closed classification tests for CH025 routing diagnostics."""
from __future__ import annotations

import unittest

from analyze_ch025_route_topology import classify


class RouteCutClassification(unittest.TestCase):
    def test_missing_anchors_not_reported_as_route(self) -> None:
        self.assertEqual(classify(False, True, False),
                         'CH025_In2_anchor_unavailable')
        self.assertEqual(classify(True, False, False),
                         'CH025_In2_anchor_unavailable')

    def test_connected_topology_is_not_qualified_copper(self) -> None:
        self.assertEqual(classify(True, True, True),
                         'CH025_two_layer_topologically_reachable_mesh_unresolved')

    def test_disconnected_topology_blocks_local_route(self) -> None:
        self.assertEqual(classify(True, True, False),
                         'CH025_two_layer_geometric_cut')


if __name__ == '__main__':
    unittest.main()

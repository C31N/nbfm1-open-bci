#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed path classification for CH025 retained-via B.Cu bypass."""
from __future__ import annotations

import unittest

from analyze_ch025_reused_via_pairs import FLAGS, pair_status, expanded_region


class ExistingViaPairSafety(unittest.TestCase):
    def test_expanded_corridor_reaches_previously_excluded_ch025_target(self) -> None:
        from shapely.geometry import Point, box
        old_region = box(15, 0.5, 67, 40.949)
        a, b = (49.455, 16.48), (36.105, 48.85)
        domain = box(1, 0, 88, 70)
        self.assertFalse(old_region.covers(Point(b)))
        expanded = expanded_region(old_region, a, b, domain)
        self.assertTrue(expanded.covers(Point(a)))
        self.assertTrue(expanded.covers(Point(b)))
        self.assertGreater(expanded.bounds[3], 52.0)

    def test_expansion_must_respect_real_board_edges(self) -> None:
        from shapely.geometry import box
        with self.assertRaises(ValueError):
            expanded_region(box(0, 0, 20, 20), (4, 4), (17, 25),
                            box(0.25, 0.25, 19.75, 19.75))


    def test_component_pinning(self) -> None:
        self.assertEqual(pair_status(None, 3),
                         'reused_via_outside_BCu_copper_corridor')
        self.assertEqual(pair_status(3, None),
                         'reused_via_outside_BCu_copper_corridor')
        self.assertEqual(pair_status(3, 4),
                         'reused_via_pair_separated_on_BCu')
        self.assertEqual(pair_status(3, 3),
                         'BCu_component_connected_but_mesh_unqualified')

    def test_release_and_via_gates(self) -> None:
        for key in ('accepted', 'routing_completed', 'fabrication_release',
                    'manufacturing_files', 'native_drc_passed',
                    'schematic_parity_passed', 'independent_replay_verified',
                    'L3_loss_qualified', 'L3_gain_qualified',
                    'CH025_net_restituted_native', 'new_vias_allowed'):
            self.assertIs(FLAGS[key], False)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed path classification for CH025 retained-via B.Cu bypass."""
from __future__ import annotations

import unittest

from analyze_ch025_reused_via_pairs import FLAGS, pair_status


class ExistingViaPairSafety(unittest.TestCase):
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

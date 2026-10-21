#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Guard dual-route trial invariants without native KiCad runtime."""
from __future__ import annotations

import unittest

from probe_ch022_ch025_dual_route import FLAGS, path_is_pinned


class DualNetRouteSafety(unittest.TestCase):
    def test_pinned_endpoints_and_layer_changes(self) -> None:
        route = [
            (0, 44., 15.), (1, 44., 15.), (1, 46., 20.),
            (0, 46., 20.), (0, 45., 30.),
        ]
        self.assertTrue(path_is_pinned(route, (44., 15.), (45., 30.), 0))
        self.assertFalse(path_is_pinned(route, (44., 16.), (45., 30.), 0))
        self.assertFalse(path_is_pinned(route, (44., 15.), (45., 30.), 1))
        self.assertFalse(path_is_pinned(
            [(0, 44., 15.), (1, 45., 15.)],
            (44., 15.), (45., 15.), 0))
        self.assertFalse(path_is_pinned(
            [(0, 44., 15.), (2, 44., 15.), (0, 45., 30.)],
            (44., 15.), (45., 30.), 0))

    def test_zero_release_promotion(self) -> None:
        for key in ('accepted', 'routing_completed', 'fabrication_release',
                    'manufacturing_files', 'native_drc_passed',
                    'schematic_parity_passed', 'independent_replay_verified',
                    'L3_loss_qualified', 'L3_gain_qualified',
                    'CH025_restitution_native_passed'):
            self.assertIs(FLAGS[key], False)


if __name__ == '__main__':
    unittest.main()

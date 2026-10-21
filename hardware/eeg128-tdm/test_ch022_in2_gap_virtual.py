#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed model guards for the pinned CH025_N_MUX."""
from __future__ import annotations

import unittest

from analyze_ch022_in2_gap_virtual import EXPECTED, FLAGS, NET, PIN, pinned_ok


class In2VirtualGuards(unittest.TestCase):
    def test_unique_uuid_and_layer(self) -> None:
        self.assertTrue(pinned_ok(PIN, NET, 'In2.Cu', EXPECTED, .15))
        self.assertFalse(pinned_ok(PIN, NET, 'B.Cu', EXPECTED, .15))
        self.assertFalse(pinned_ok('other', NET, 'In2.Cu', EXPECTED, .15))
        self.assertFalse(pinned_ok(PIN, 'VCM', 'In2.Cu', EXPECTED, .15))
        self.assertFalse(pinned_ok(PIN, NET, 'In2.Cu',
                                   ((44.55, 25.13), EXPECTED[1]), .15))

    def test_no_release_promotion(self) -> None:
        for key in ('accepted', 'routing_completed', 'fabrication_release',
                    'native_qualification', 'independent_replay_verified',
                    'manufacturing_files', 'CH025_N_MUX_restitution_qualified',
                    'L3_loss_qualified', 'L3_gain_qualified'):
            self.assertIs(FLAGS[key], False)


if __name__ == '__main__':
    unittest.main()

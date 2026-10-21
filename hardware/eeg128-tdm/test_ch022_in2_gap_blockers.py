#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CH022 exact blocker attribution safety tests, independent of pcbnew."""
from __future__ import annotations

import unittest

from analyze_ch022_in2_gap_blockers import FLAGS, KEEP_OUT_MM, movement_class


class GapBlockerGuards(unittest.TestCase):
    def test_nonprotected_inner_In2_segment_is_model_only(self) -> None:
        self.assertEqual(
            movement_class('CH031_N_MUX', 'track', 'In2.Cu', 3.0, 1.0),
            'CANDIDATE_REQUIRES_FULL_NATIVE_RESTITUTION')

    def test_vias_power_and_known_traces_are_never_movable(self) -> None:
        protected = ('VCM', 'AGND', 'CH017_N_ELECTRODE',
                     'CH019_P_MUX', 'CH024_P_MUX', 'CH026_P_ELECTRODE',
                     'CH024_N_ELECTRODE', 'CH025_N_ELECTRODE',
                     '3V3A', 'VREG_1V1', 'VDD')
        for net in protected:
            self.assertEqual(movement_class(net, 'track', 'In2.Cu', 10, 10),
                             'IMMUTABLE', net)
        self.assertEqual(movement_class('CH031_N_MUX', 'via', 'THROUGH', 10, 10),
                         'IMMUTABLE')
        self.assertEqual(movement_class('CH031_N_MUX', 'pad', 'In2.Cu', 10, 10),
                         'IMMUTABLE')
        self.assertEqual(movement_class('CH031_N_MUX', 'track', 'F.Cu', 10, 10),
                         'IMMUTABLE')

    def test_pad_and_via_contacts_never_qualify(self) -> None:
        self.assertEqual(movement_class('CH031_N_MUX', 'track', 'In2.Cu', .99, 9),
                         'PAD_OR_VIA_ESCAPE_PROTECTED')
        self.assertEqual(movement_class('CH031_N_MUX', 'track', 'In2.Cu', 9, .649),
                         'PAD_OR_VIA_ESCAPE_PROTECTED')

    def test_release_and_power_gates(self) -> None:
        self.assertEqual(KEEP_OUT_MM, .505)
        for name in ('accepted', 'fabrication_release', 'routing_completed',
                     'native_qualification', 'independent_replay_verified',
                     'manufacturing_files'):
            self.assertIs(FLAGS[name], False)


if __name__ == '__main__':
    unittest.main()

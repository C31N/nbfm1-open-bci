#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CH022 F.Cu micro-displacement is UUID-pinned and fail-closed."""
from __future__ import annotations

from pathlib import Path
import unittest

import probe_ch022_fcu_micro as micro
import probe_block2_r302_joint as joint


class CH022FCuMicroGuards(unittest.TestCase):
    def test_pinned_net_and_exact_uuids(self) -> None:
        self.assertEqual(micro.PINNED_CH024N, (
            '7c87269e-9bef-4b54-82fa-41d657775aac',
            'f489590a-6746-48d2-bd2f-091103b220a3',
        ))
        self.assertNotIn('CH024_N_ELECTRODE', micro.GUARDED_NETS)
        self.assertNotIn('CH025_N_ELECTRODE', micro.GUARDED_NETS)
        self.assertEqual(micro.PINNED_CH025N, '156ba77d-5f3e-4c18-88ee-0f2763e31dfd')
        for name in ('CH017_N_ELECTRODE', 'CH026_P_ELECTRODE',
                     'CH024_P_MUX', 'CH019_P_MUX', 'VCM', 'AGND',
                     'CH028_P_ELECTRODE', 'CH030_N_ELECTRODE',
                     'CH031_P_ELECTRODE'):
            self.assertIn(name, micro.GUARDED_NETS)

    def test_restitution_and_protection_are_mandatory(self) -> None:
        text = Path(micro.__file__).read_text()
        parent = Path(joint.__file__).read_text()
        for guard in ('pad_distance >= 1.0', 'via_distance >= .65',
                      'pinned segment identity/layer mismatch',
                      'protected_before', 'accepted_geometry = False',
                      'displaced_electrode_restitution_blocked',
                      '_copper_signature(board, GUARDED_NETS)',
                      'finally:', 'board.Remove(item)', 'board.Add(item)',
                      'len(restored) != len(subset)',
                      'source.covers(Point(pt))', 'power.buffer(.505)',
                      'CH022 identity changed', 'residual_FCu_gap',
                      'nearby_blocker_uuids', 'pad_or_via_escape_protected',
                      'for subset in variants:', 'CH025N_restituted'):
            self.assertIn(guard, text)
        for guard in ('ch022_fcu_micro_analysis',
                      'args.ch022_fcu_micro',
                      'CH024_N_ELECTRODE',
                      'ch017_native_continuity_ok'):
            self.assertIn(guard, parent)

    def test_ch025_via_contact_is_never_removed(self) -> None:
        from analyze_ch025_via_guard import free_intervals, PINNED, FLAGS
        self.assertEqual(PINNED, micro.PINNED_CH025N)
        self.assertFalse(FLAGS['accepted'])
        self.assertFalse(FLAGS['fabrication_release'])
        self.assertEqual(
            free_intervals((0., 0.), (1., 0.),
                           [(0., 0.), (1., 0.)], []), [])
        allowed = free_intervals((0., 0.), (1., 0.), [(0., 0.)], [])
        self.assertEqual(len(allowed), 1)
        self.assertGreaterEqual(allowed[0]['start_mm'][0], .65)
        self.assertLessEqual(allowed[0]['end_mm'][0], .85)
        self.assertIn('ch025_via_stub_analysis',
                      Path(micro.__file__).read_text())

    def test_no_manufacturing_or_release_promotion(self) -> None:
        for key in ('accepted', 'routing_completed', 'fabrication_release',
                    'native_qualification', 'independent_replay_verified',
                    'manufacturing_files'):
            self.assertIs(micro.FLAGS[key], False)
            self.assertIs(joint.FLAGS[key], False)
        source = Path(micro.__file__).read_text()
        self.assertNotIn('pcbnew.SaveBoard', source)
        self.assertNotIn('generate_manufacturing', source)
        self.assertNotIn("'accepted': True", source)
        self.assertIn("'full_geometry_proposal_needs_native_qualification'", source)


if __name__ == '__main__':
    unittest.main()

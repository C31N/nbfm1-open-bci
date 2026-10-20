#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic, fail-closed structural guards for CH022 AGND hop."""
from __future__ import annotations

import unittest
from pathlib import Path

from shapely.geometry import LineString, box
import probe_ch022_agnd_hop as hop
import probe_block2_r302_joint as joint


class CH022AgndHopGuards(unittest.TestCase):
    def test_all_release_controls_false(self) -> None:
        for flag in ('accepted', 'routing_completed', 'fabrication_release',
                     'native_qualification', 'independent_replay_verified',
                     'manufacturing_files'):
            self.assertIs(hop.FLAGS[flag], False)
            self.assertIs(joint.FLAGS[flag], False)

    def test_candidate_generation_stays_inside_legal_via_window(self) -> None:
        area = box(35, 13, 36, 14)
        direct = LineString([(35, 17), (45, 9)])
        samples = hop._samples(area, direct, (35, 16), 4)
        self.assertTrue(samples)
        self.assertLessEqual(len(samples), 4)
        self.assertEqual(samples, hop._samples(area, direct, (35, 16), 4))
        for x, y in samples:
            self.assertGreater(x, 35)
            self.assertLess(x, 36)
            self.assertGreater(y, 13)
            self.assertLess(y, 14)

    def test_no_foreign_copper_removal_or_power_exceptions(self) -> None:
        source = Path(hop.__file__).read_text()
        probe = Path(joint.__file__).read_text()
        self.assertNotIn('board.Remove(', source)
        self.assertNotIn('SaveBoard(', source)
        for guarded in ('power.buffer(.505)', 'routing_domain',
                        'via_obstacle', 'shapes[0]', 'shapes[1]',
                        'allow_vias=False', 'AGND_Y = 11.0',
                        'layer not in (0, 1)'):
            self.assertIn(guarded, source if guarded != 'routing_domain'
                          else Path(__file__).with_name(
                              'route_targeted_closure.py').read_text())
        for guarded in ('ch017_native_continuity_ok', 'current_immutable',
                        'immutable_tracks', 'CH028_P_ELECTRODE',
                        'CH030_P_ELECTRODE', 'CH031_P_ELECTRODE',
                        'ch022_agnd_hop_analysis', 'L3_loss_mm2',
                        'L3_gain_mm2', 'candidate_136_eligible_for_independent_replay'):
            self.assertIn(guarded, probe)
        self.assertIn('args.ch022_agnd_hop', probe)
        self.assertIn('ch017_local_restore and via_plan', probe)

    def test_no_checkpoint_promotion_in_diagnostic(self) -> None:
        source = Path(joint.__file__).read_text()
        self.assertIn("result['status'] = 'native_audit_only_unaccepted'", source)
        self.assertNotIn("result['accepted'] = True", source)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic CH025_N protected interior cut and release gate tests."""
from __future__ import annotations

from pathlib import Path
import unittest

from probe_ch025_interior_virtual import inner_endpoints, same_net_cut_contacts, FLAGS


class InteriorSafety(unittest.TestCase):
    def test_exact_guarded_middle_with_endpoint_margin(self) -> None:
        left, right = inner_endpoints({
            'start_mm': [45.25, 14.4922],
            'end_mm': [45.3922, 14.4922]})
        self.assertEqual(left, (45.262, 14.4922))
        self.assertEqual(right, (45.3802, 14.4922))
        self.assertAlmostEqual(right[0] - left[0], .1182)

    def test_same_net_branch_intersection_blocks_without_mutating(self) -> None:
        cut = ((45.262, 14.4922), (45.3802, 14.4922))
        touch = same_net_cut_contacts(*cut, [
            ('junction-a', (45.3, 14.4922), (45.3, 15.0)),
        ])
        self.assertEqual(len(touch), 1)
        self.assertEqual(touch[0]['uuid'], 'junction-a')
        self.assertEqual(touch[0]['junction_type'], 'same_net_point_contact')
        self.assertEqual(touch[0]['safety_decision'], 'BLOCK_INTERIOR_MUTATION')
        overlap = same_net_cut_contacts(*cut, [
            ('overlap-a', (45.28, 14.4922), (45.34, 14.4922)),
        ])
        self.assertEqual(overlap[0]['junction_type'], 'collinear_overlap')
        self.assertEqual(same_net_cut_contacts(*cut, [
            ('far-away', (46.0, 14.4922), (46.5, 14.4922)),
        ]), [])

    def test_no_submillimetre_protection_reduction(self) -> None:
        with self.assertRaises(ValueError):
            inner_endpoints({'start_mm': [45.25, 14.4922],
                             'end_mm': [45.3922, 14.4922]}, .005)
        with self.assertRaises(ValueError):
            inner_endpoints({'start_mm': [45.25, 14.49],
                             'end_mm': [45.26, 14.49]})

    def test_guards_and_no_release_or_manufacturing_exports(self) -> None:
        for flag in ('accepted', 'routing_completed', 'fabrication_release',
                     'native_qualification', 'independent_replay_verified',
                     'manufacturing_files'):
            self.assertIs(FLAGS[flag], False)
        script = Path(__file__).with_name('probe_ch025_interior_virtual.py').read_text()
        for statement in ("reserve.buffer(.505)", "edge_clearance_mm': .25",
                          "CH025_contact_stubs_preserved",
                          "Protected VCM or neighbour copper mutated",
                          "Rollback changed board track UUID inventory",
                          "all_trials_rolled_back", "same_net_contact_blockers",
                          "CH025_interior_same_net_contact_guard",
                          "BLOCK_INTERIOR_MUTATION"):
            self.assertIn(statement, script)
        self.assertNotIn('SaveBoard(', script)
        self.assertNotIn('fabrication_release=True', script)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic CH025_N protected interior cut and release gate tests."""
from __future__ import annotations

from pathlib import Path
import unittest

from probe_ch025_interior_virtual import inner_endpoints, FLAGS


class InteriorSafety(unittest.TestCase):
    def test_exact_guarded_middle_with_endpoint_margin(self) -> None:
        left, right = inner_endpoints({
            'start_mm': [45.25, 14.4922],
            'end_mm': [45.3922, 14.4922]})
        self.assertEqual(left, (45.262, 14.4922))
        self.assertEqual(right, (45.3802, 14.4922))
        self.assertAlmostEqual(right[0] - left[0], .1182)

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
                          "all_trials_rolled_back"):
            self.assertIn(statement, script)
        self.assertNotIn('SaveBoard(', script)
        self.assertNotIn('fabrication_release=True', script)


if __name__ == '__main__':
    unittest.main()

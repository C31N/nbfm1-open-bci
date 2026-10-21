#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Conservative existing-via end-anchor classification."""
from __future__ import annotations

import unittest

from analyze_ch025_existing_via_anchor import classify_anchor


class ReuseViaGuard(unittest.TestCase):
    def test_target_with_no_copper(self) -> None:
        self.assertEqual(classify_anchor(False, 3),
                         'CH025_target_has_no_surviving_same_net_contact')

    def test_no_viable_reused_via(self) -> None:
        self.assertEqual(classify_anchor(True, 0),
                         'CH025_target_connected_but_no_existing_via')

    def test_reachable_existing_via(self) -> None:
        self.assertEqual(classify_anchor(True, 1),
                         'CH025_target_has_existing_connected_via')


if __name__ == '__main__':
    unittest.main()

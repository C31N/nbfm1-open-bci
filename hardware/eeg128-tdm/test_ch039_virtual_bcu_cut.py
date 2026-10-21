#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure safe conclusions from CH039 virtual copper cut."""
from __future__ import annotations

import unittest

from analyze_ch039_virtual_bcu_cut import NET, UUID, VCM_UUID, classify


class VirtualCH039Safety(unittest.TestCase):
    def test_pinned_identifiers_and_conclusions(self) -> None:
        self.assertEqual(NET, 'CH039_P_MUX')
        self.assertEqual(UUID, '31aaecea-198a-47c2-bcb6-c5ba10222375')
        self.assertEqual(VCM_UUID, '04530298-f223-5100-ba26-ffbe00945865')
        self.assertIn('restitution_required', classify(True))
        self.assertIn('does_not_open', classify(False))


if __name__ == '__main__':
    unittest.main()

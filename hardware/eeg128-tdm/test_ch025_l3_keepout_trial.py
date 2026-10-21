#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact two-sided L3 zone area gate, zero is never rounded."""
from __future__ import annotations

import unittest

from analyze_ch025_l3_keepout_trial import exact_gate


class KeepoutTests(unittest.TestCase):
    def test_loss_gain_polygon_equality_all_required(self) -> None:
        self.assertTrue(exact_gate(0.0, 0.0, True))
        self.assertFalse(exact_gate(1e-12, 0.0, True))
        self.assertFalse(exact_gate(0.0, 1e-12, True))
        self.assertFalse(exact_gate(0.0, 0.0, False))


if __name__ == '__main__':
    unittest.main()

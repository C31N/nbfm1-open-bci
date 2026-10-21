#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Strict L3 loss/gain and release interlocks, no native PCB required."""
from __future__ import annotations

import unittest

from analyze_ch025_l3_native_refill import FLAGS, classify_delta


class NativeRefillGate(unittest.TestCase):
    def test_delta_exactness(self) -> None:
        self.assertEqual(classify_delta(0.0, 0.0),
                         'removal_only_zero_delta')
        self.assertEqual(classify_delta(0.0, 1e-12),
                         'removal_only_nonzero_delta')
        self.assertEqual(classify_delta(1e-12, 0.0),
                         'removal_only_nonzero_delta')

    def test_block_release(self) -> None:
        self.assertTrue(all(v is False for v in FLAGS.values()))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed constraints for the CH025 F.Cu-only diagnostic."""
import unittest

from probe_ch025_fcu_l3_exact import (
    FLAGS, L3_MASK_OFFSETS_MM, protected_unchanged)


class CH025FCuL3Safety(unittest.TestCase):
    def test_no_release_flags(self):
        self.assertTrue(all(value is False for value in FLAGS.values()))

    def test_mask_offsets_bounded_and_deterministic(self):
        self.assertEqual(L3_MASK_OFFSETS_MM,
                         (-.100, -.050, -.025, 0.0, .025, .050))
        self.assertTrue(all(abs(value) <= .100 for value in L3_MASK_OFFSETS_MM))

    def test_untouched_protected_uuids(self):
        old = {"a": ("VCM", 1), "b": ("CH025_N_MUX", 2),
               "748cc9c4-2d8f-4ec6-9714-133d79d4c7cb": ("CH025_N_MUX", 3)}
        new = {"a": ("VCM", 1), "b": ("CH025_N_MUX", 2)}
        self.assertTrue(protected_unchanged(old, new))
        new["a"] = ("VCM", 0)
        self.assertFalse(protected_unchanged(old, new))


if __name__ == "__main__":
    unittest.main()

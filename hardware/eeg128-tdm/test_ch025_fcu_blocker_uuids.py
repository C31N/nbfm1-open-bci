#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Policy guards independent of pcbnew for the CH025 UUID inventory."""
from __future__ import annotations

import unittest

from analyze_ch025_fcu_blocker_uuids import (
    FLAGS, MICRO_MM, micro_dogleg, protected_net,
)


class CH025FCuInventorySafety(unittest.TestCase):
    def test_mandatory_protections(self) -> None:
        for value in ("VCM", "CH017_N_MUX", "CH019_P_MUX",
                      "CH024_P_MUX", "CH026_P_ELECTRODE",
                      "3V3A", "AGND", "DRL"):
            self.assertTrue(protected_net(value))
        self.assertFalse(protected_net("CH031_N_MUX"))

    def test_fixed_endpoints_and_micro_offsets(self) -> None:
        for magnitude in MICRO_MM:
            for direction in (-1, 1):
                result = micro_dogleg((1.0, 2.0), (4.0, 2.0),
                                      direction * magnitude)
                self.assertEqual(result[0], (1.0, 2.0))
                self.assertEqual(result[-1], (4.0, 2.0))
                self.assertEqual(result[1][1], 2.0 + direction * magnitude)
        with self.assertRaises(ValueError):
            micro_dogleg((1.0, 2.0), (1.2, 2.0), .150)

    def test_release_stays_blocked(self) -> None:
        self.assertTrue(all(value is False for value in FLAGS.values()))


if __name__ == "__main__":
    unittest.main()

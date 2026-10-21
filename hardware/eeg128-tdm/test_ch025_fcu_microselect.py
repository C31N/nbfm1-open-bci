#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed checks for bounded CH025 micro-selective geometry."""
from __future__ import annotations

import unittest

from probe_ch025_fcu_microselect import (
    choose, EXPECTED_START, EXPECTED_END, EXPECTED_OFFSET,
)
from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, BOARD_SHA256


class MicroSelectTests(unittest.TestCase):
    def test_strict_verified_shortlist(self) -> None:
        pair = {"source_uuid": EXPECTED_START, "target_uuid": EXPECTED_END,
                "ranked_direct_corridors": [
                    {"offset_mm": EXPECTED_OFFSET,
                     "blocking_uuid_count": 28,
                     "protected_uuid_count": 19,
                     "edge_clearance_satisfied": True,
                     "blockers": [{} for _ in range(28)]}
                ]}
        alternate = {"source_uuid": "other", "target_uuid": "other",
                     "ranked_direct_corridors": [
                         {"offset_mm": 0.0,
                          "blocking_uuid_count": 31,
                          "protected_uuid_count": 19,
                          "edge_clearance_satisfied": True,
                          "blockers": [{} for _ in range(31)]}
                     ]}
        sample = {"source_archive_sha256": ARCHIVE_SHA256,
                  "source_pcb_sha256": BOARD_SHA256,
                  "via_pairs": 4, "sampled_direct_corridors": 28,
                  "pairs": [pair, alternate]}
        with self.assertRaises(ValueError):
            choose(sample)
        sample["pairs"] = [pair] + [{
            "ranked_direct_corridors": [
                {"offset_mm": .0, "blocking_uuid_count": 40,
                 "protected_uuid_count": 39,
                 "edge_clearance_satisfied": True,
                 "blockers": [{} for _ in range(40)]} for _ in range(9)
            ],
            "source_uuid": "other", "target_uuid": "other",
        }] * 3
        # A hypothetical easy one-obstacle route would have won ranking.
        with self.assertRaises(ValueError):
            choose(sample)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static release and selection rules, runnable without pcbnew."""
from __future__ import annotations
import unittest

from probe_ch025_neighbor_restitution7 import (
    NEIGHBORS, UNCHANGED, PATH, FLAGS, audit_foreign_tracks, check_plan,
)


class NativeRestitutionSafety(unittest.TestCase):
    def test_reviewed_geometry_and_locked_flags(self) -> None:
        check_plan()
        self.assertEqual(len(PATH), 16)
        self.assertEqual(len(NEIGHBORS), 7)
        self.assertEqual(len(UNCHANGED), 2)
        self.assertTrue(all(value is False for value in FLAGS.values()))

    def test_protected_track_must_not_change(self) -> None:
        before = {"protected-vcm": ("VCM", 0, (1, 2), (3, 4), 150000, "PCB_TRACK"),
                  "candidate": ("MUX_S0", 0, (1, 2), (3, 4), 150000, "PCB_TRACK")}
        self.assertRaises(RuntimeError, audit_foreign_tracks,
                          before, {"protected-vcm": ("VCM", 1)})
        self.assertRaises(RuntimeError, audit_foreign_tracks,
                          before, {"candidate": before["candidate"]})


if __name__ == "__main__":
    unittest.main()

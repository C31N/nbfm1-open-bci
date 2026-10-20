# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed structural guards for pinned CH017_N restoration experiment."""
from __future__ import annotations

import unittest
from pathlib import Path

import probe_block2_r302_joint as probe


class CH017NRestitutionGuards(unittest.TestCase):
    def test_pinned_two_segment_scope_and_pad_via_guards(self) -> None:
        source = Path(probe.__file__).read_text()
        for uid in ('d04ea811-0e34-5d4f-8320-88b489821ec6',
                    '4aa24dbb-0a8d-5bc6-afe9-6f73d285e716'):
            self.assertIn(uid, source)
        for required in (
                "'CH017_N_ELECTRODE'", "t.GetLayer() != pcbnew.B_Cu",
                "line.distance(p) < 1.0", "line.distance(v) < .65",
                "len(ch017_pivots) != 1", "len(ch017_ends) != 2",
                "ch017_pivot_preserved", "ch017_local_restitution_blocked"):
            self.assertIn(required, source)

    def test_actual_native_ch017_connectivity_is_required(self) -> None:
        source = Path(probe.__file__).read_text()
        for required in ("ch017_native_continuity_ok", "native_fresh(",
                         "ch017_native_restitution_failed",
                         "ch017_airwires_before", "ch017_airwires_after",
                         "previous == 0 and current == 0 and not errors"):
            self.assertIn(required, source)

    def test_unchanged_released_gates(self) -> None:
        for name in ("accepted", "routing_completed", "fabrication_release",
                     "native_qualification", "independent_replay_verified",
                     "manufacturing_files"):
            self.assertIs(probe.FLAGS[name], False)


if __name__ == "__main__":
    unittest.main()

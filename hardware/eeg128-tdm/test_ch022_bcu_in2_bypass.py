#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed CH022 B.Cu/In2.Cu geometry and protection guards."""
from __future__ import annotations

from pathlib import Path
import unittest

import probe_ch022_bcu_in2_bypass as probe


class In2BypassSafety(unittest.TestCase):
    def test_zero_release_and_exact_power_radius(self) -> None:
        self.assertEqual(probe.KEEP_OUT_MM, .505)
        self.assertEqual(probe.EDGE_CLEARANCE_MM, .25)
        self.assertEqual(probe.SEARCH_MARGIN_MM, 24.0)
        for key in ('accepted', 'fabrication_release', 'routing_completed',
                    'native_qualification', 'independent_replay_verified',
                    'manufacturing_files'):
            self.assertIs(probe.FLAGS[key], False)

    def test_snapped_via_sites_are_in_legal_window(self) -> None:
        from shapely.geometry import Point, box
        legal = box(0, 0, 4, 4).difference(Point(2, 2).buffer(1))
        centres = probe._via_centres(legal)
        self.assertTrue(centres)
        self.assertTrue(all(legal.contains(Point(p)) for p in centres))
        self.assertEqual(centres, sorted(centres))

    def test_source_and_targets_fcu_are_immutable(self) -> None:
        src = Path(probe.__file__).read_text()
        required = (
            "source in existing", "target in existing",
            "(pcbnew.B_Cu, pcbnew.In2_Cu)", "power.buffer(KEEP_OUT_MM)",
            "part.intersection(source_comp).intersection(viafree)",
            "part.intersection(target_comp).intersection(viafree)",
            "reachable_via_component_count", "source_accessible_In2_count",
            "target_accessible_In2_count",
            "len(candidates)", "'foreign_FCu_mutation': False",
            "start_layer=0, goal_layer=0",
            "BCu_In2_geometry_proposed_unqualified",
            "L3_loss_qualified': False", "L3_gain_qualified': False",
        )
        for value in required:
            self.assertIn(value, src)
        self.assertNotIn('pcbnew.SaveBoard(', src)
        self.assertNotIn('board.Remove(', src)
        self.assertNotIn('fabrication_release=True', src)

    def test_cannot_pretend_to_have_replay_gate(self) -> None:
        joint = Path(__file__).with_name('probe_block2_r302_joint.py').read_text()
        self.assertIn('ch022_in2_bypass_analysis', joint)
        self.assertIn('args.ch022_in2_bypass', joint)
        self.assertIn('CH024_N_ELECTRODE', joint)
        self.assertIn('bridge = (None if ch022_in2_bypass else mesh_route(', joint)
        self.assertIn('component_graph = transition_graph(', Path(probe.__file__).read_text())


if __name__ == '__main__':
    unittest.main()

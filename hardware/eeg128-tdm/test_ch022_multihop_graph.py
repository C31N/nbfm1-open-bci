#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Synthetic graph proving one-hop failure need not rule out multi-hop."""
from __future__ import annotations

from pathlib import Path
import unittest

from shapely.geometry import box
from shapely.ops import unary_union
from analyze_ch022_multihop_graph import transition_graph


class CH022GraphSafety(unittest.TestCase):
    def test_two_In2_islands_can_connect_via_intermediate_BCu(self) -> None:
        # No single In2.Cu island contacts both terminal B.Cu islands.
        bs = unary_union((box(0, 8, 4, 10), box(3, 4, 7, 7),
                          box(6, 0, 10, 3)))
        ins = unary_union((box(1, 6, 5, 9), box(5, 2, 9, 5)))
        result = transition_graph(bs, ins, box(0, 0, 10, 10),
                                  (1, 9), (9, 1))
        self.assertTrue(result['multihop_connected'])
        self.assertEqual(result['minimum_layer_transitions'], 4)
        self.assertEqual(len(result['component_path']), 5)
        self.assertEqual(len(result['transition_via_centres_mm']), 4)
        self.assertFalse(result['accepted'])

    def test_disconnected_islands_do_not_get_false_route(self) -> None:
        bs = unary_union((box(0, 8, 4, 10), box(6, 0, 10, 3)))
        ins = unary_union((box(1, 6, 5, 9), box(5, 2, 9, 5)))
        result = transition_graph(bs, ins, box(0, 0, 10, 10),
                                  (1, 9), (9, 1))
        self.assertEqual(result['status'], 'separate_BCu_In2_component_graphs')
        self.assertFalse(result['multihop_connected'])
        self.assertIsNone(result['minimum_layer_transitions'])

    def test_power_keepout_breaks_graph_edges(self) -> None:
        bs = unary_union((box(0, 8, 4, 10), box(3, 4, 7, 7),
                          box(6, 0, 10, 3)))
        ins = unary_union((box(1, 6, 5, 9), box(5, 2, 9, 5)))
        # This legal via centre region does not touch ANY In2 copper.
        result = transition_graph(bs, ins, box(11, 11, 12, 12),
                                  (1, 9), (9, 1))
        self.assertEqual(result['valid_via_transition_edges'], 0)
        self.assertFalse(result['multihop_connected'])

    def test_readonly_and_release_guards(self) -> None:
        source = Path(__file__).with_name('analyze_ch022_multihop_graph.py').read_text()
        bypass = Path(__file__).with_name('probe_ch022_bcu_in2_bypass.py').read_text()
        self.assertIn('multihop_component_graph', bypass)
        self.assertIn('minimum_layer_transitions', source)
        self.assertIn('closest_disconnected_In2_gap_mm', source)
        self.assertNotIn('board.Remove(', source)
        self.assertNotIn('pcbnew.SaveBoard(', source)
        self.assertNotIn('fabrication_release=True', source)


if __name__ == '__main__':
    unittest.main()

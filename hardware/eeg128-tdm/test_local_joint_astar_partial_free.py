#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Genuine None-headed joint routing, immutable-copper and fail-close tests."""
from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import GeometryCollection, box

from local_joint_astar_partial_free import (
    PartialFreeState, partial_free_joint_astar)
from probe_block2_elastic_joint_corridor import FCuCorridorGrid

Node = tuple[int, int]


class PartialFreeJointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.xs = np.arange(0., 3.0801, .22)
        self.ys = np.arange(0., 3.0801, .22)
        self.rows = (3, 7, 11)
        self.masks = [
            np.ones((len(self.ys), len(self.xs)), dtype=bool)
            for _ in range(3)]
        for i, row in enumerate(self.rows):
            self.masks[i][row, 2:9] = False
        self.shapes = [GeometryCollection() for _ in range(3)]
        self.source: tuple[tuple[Node, ...], ...] = tuple(
            ((2, row), (3, row)) for row in self.rows)
        self.goal: tuple[tuple[Node, ...], ...] = tuple(
            ((7, row),) for row in self.rows)

    def grid(self) -> FCuCorridorGrid:
        return FCuCorridorGrid(
            self.masks, self.shapes, self.xs, self.ys)

    def solve(self, max_expansions: int = 900) -> dict[str, object]:
        return partial_free_joint_astar(
            self.grid(), self.source, self.goal,
            max_expansions=max_expansions, max_seconds=3.)

    def test_none_state_is_genuinely_unbound(self) -> None:
        state = PartialFreeState(((), ((4, 7),), ()))
        self.assertEqual(state.heads, (None, (4, 7), None))
        self.assertEqual(state.paths[0], ())

    def test_three_short_tracks_close_with_dynamic_bindings(self) -> None:
        before = tuple(m.tobytes() for m in self.masks)
        result = self.solve()
        self.assertEqual(
            result["status"], "PARTIAL_FREE_THREE_LOCAL_ROUTES_PROPOSED",
            result)
        routes = result["routes"]
        self.assertEqual(len(routes), 3)
        for i, route in enumerate(routes):
            self.assertIn(route[0], self.source[i])
            self.assertIn(route[-1], self.goal[i])
            self.assertTrue(len(route) >= 2)
        self.assertEqual(result["initial_heads"], [None, None, None])
        self.assertGreater(result["binding_actions_valid"], 0)
        self.assertGreater(result["search_states_by_bound_count"][1], 0)
        self.assertTrue(result["density_penalty_applied"])
        self.assertFalse(result["accepted"])
        self.assertFalse(result["routing_completed"])
        self.assertFalse(result["fabrication_release"])
        self.assertEqual(result["new_vias_added"], 0)
        self.assertEqual(tuple(m.tobytes() for m in self.masks), before)

    def test_blocked_fcu_mask_prefilter_never_claims_route(self) -> None:
        # A full raster wall is not allowed to be overcome by cost bias.
        self.masks[1][7, 4] = True
        result = self.solve()
        self.assertNotEqual(
            result["status"], "PARTIAL_FREE_THREE_LOCAL_ROUTES_PROPOSED")
        self.assertEqual(result["completed_routes"], 0)
        self.assertGreater(result["native_mask_prefilter_rejections"], 0)
        self.assertFalse(result["fabrication_release"])

    def test_inflated_native_shape_between_nodes_is_hard(self) -> None:
        x = (float(self.xs[4]) + float(self.xs[5])) / 2
        y = float(self.ys[7])
        self.shapes[1] = box(x - .02, y - .04, x + .02, y + .04)
        result = self.solve()
        self.assertNotEqual(
            result["status"], "PARTIAL_FREE_THREE_LOCAL_ROUTES_PROPOSED")
        self.assertGreater(result["native_segment_rejections"], 0)

    def test_anchor_pitch_cannot_be_reduced(self) -> None:
        with self.assertRaises(ValueError):
            partial_free_joint_astar(
                self.grid(), self.source, self.goal,
                anchor_pitch_mm=.439)
        with self.assertRaises(ValueError):
            partial_free_joint_astar(
                self.grid(), self.source, self.goal,
                hard_pitch_mm=.299)


if __name__ == "__main__":
    unittest.main()

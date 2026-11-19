#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Genuine None-headed joint routing, immutable-copper and fail-close tests."""
from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import GeometryCollection, box

from local_joint_astar_partial_free import (
    PartialFreeState, _evasion_fair_due, _nearest_target_node,
    partial_free_joint_astar)
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

    def test_fair_queue_first_candidate_is_immediately_eligible(self) -> None:
        self.assertTrue(_evasion_fair_due(True, 1566, -8))
        self.assertTrue(_evasion_fair_due(True, 1, -8))
        self.assertFalse(_evasion_fair_due(False, 1566, -8))

    def test_fair_queue_rate_limit_tracks_last_actual_pop(self) -> None:
        self.assertFalse(_evasion_fair_due(True, 1567, 1566))
        self.assertFalse(_evasion_fair_due(True, 1573, 1566))
        self.assertTrue(_evasion_fair_due(True, 1574, 1566))
        with self.assertRaises(ValueError):
            _evasion_fair_due(True, 8, 0, interval=0)

    def test_nearest_native_target_selection_is_deterministic(self) -> None:
        candidates = ((5, 1), (2, 1), (9, 1))
        def distance(a: Node, b: Node) -> float:
            return abs(a[0] - b[0])
        self.assertEqual(
            _nearest_target_node((4, 1), candidates, distance),
            (5, 1))
        self.assertEqual(
            _nearest_target_node(None, candidates, distance),
            candidates[0])
        self.assertEqual(
            _nearest_target_node((7, 1), candidates, distance),
            candidates[0])
        with self.assertRaises(ValueError):
            _nearest_target_node((1, 1), (), distance)

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
        self.assertEqual(result["weighted_heuristic_epsilon"], 2.0)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["routing_completed"])
        self.assertFalse(result["fabrication_release"])
        self.assertEqual(result["new_vias_added"], 0)
        self.assertEqual(tuple(m.tobytes() for m in self.masks), before)

    def test_third_binding_survival_and_rejection_telemetry(self) -> None:
        report = self.solve()
        self.assertGreater(report["third_binding_transition_attempts"], 0)
        self.assertGreater(report["third_binding_native_valid"], 0)
        self.assertLessEqual(
            report["third_binding_admitted"],
            report["third_binding_native_valid"])
        self.assertLessEqual(
            report["third_binding_survived_after_one_step"],
            report["third_binding_admitted"])
        self.assertGreaterEqual(
            report["third_binding_survival_rate"], 0.)
        self.assertLessEqual(
            report["third_binding_survival_rate"], 1.)
        self.assertLessEqual(
            report["third_binding_roots_with_goal_progress"],
            report["third_binding_survived_after_one_step"])
        self.assertGreaterEqual(report["third_binding_goal_progress_rate"], 0.)
        self.assertLessEqual(report["third_binding_goal_progress_rate"], 1.)
        self.assertGreaterEqual(
            report["third_binding_best_goal_progress_mm"], 0.)
        self.assertGreaterEqual(
            report["third_binding_max_targets_reached"], 0)
        self.assertLessEqual(
            report["third_binding_max_targets_reached"], 3)
        self.assertGreaterEqual(
            report["average_progress_sync_penalty"], 0.)
        self.assertGreaterEqual(
            report["average_progress_sync_penalty_after_third_binding"], 0.)
        self.assertEqual(set(report["rejections_by_bound_count"]),
                         {"0", "1", "2", "3"})
        self.assertGreaterEqual(
            report["three_net_evasion_fair_queue_pop_count"], 0)
        self.assertGreaterEqual(
            report["three_net_evasion_average_expansion_ms"], 0.)
        self.assertGreaterEqual(
            report["three_net_evasion_max_expansion_ms"], 0.)
        self.assertLessEqual(report["three_net_evasion_fair_queue_peak"], 32)
        self.assertGreaterEqual(
            report["three_net_evasion_fair_queue_stale_pops"], 0)
        for metric in ("three_net_evasion_stages_generated",
                       "three_net_evasion_stages_admitted",
                       "three_net_evasion_stages_expanded"):
            self.assertEqual(set(report[metric]), {
                "SYNC_GOAL", "SINGLE_EVADE", "PAIR_EVADE",
                "COUPLED_TURN", "STAGGERED_EVADE", "ASYMMETRIC_EVADE"})
        self.assertGreaterEqual(sum(
            report["three_net_evasion_stages_generated"].values()), 0)
        self.assertIn("three_net_evasion_first_expanded_probe", report)
        self.assertEqual(report["cost_model"], "PartialFreeCostModel-v1")
        self.assertFalse(report["accepted"])
        self.assertFalse(report["fabrication_release"])

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

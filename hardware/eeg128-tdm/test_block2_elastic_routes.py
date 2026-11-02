#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic unit checks for elastic, fail-closed topology primitives."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from probe_block2_elastic_routes import _nearest_distance, repel_waypoints
from probe_block2_clearance_cutset import spacing_scenarios
from probe_block2_frontier_diagnostics import sampled_reachability

ROOT = Path(__file__).resolve().parent
ELASTIC = (ROOT / "probe_block2_elastic_routes.py").read_text()
BODY = (ROOT / "probe_block2_nbody_201.py").read_text()


class ElasticPathTests(unittest.TestCase):
    def test_distance_is_to_segment_not_to_vertices(self) -> None:
        self.assertAlmostEqual(_nearest_distance((5., 1.), [
            (0., 0.), (10., 0.)]), 1.)
        self.assertAlmostEqual(_nearest_distance((5., 0.), [
            (0., 0.), (10., 0.)]), 0.)

    def test_repel_never_moves_into_obstacle_or_other_component(self) -> None:
        import numpy as np

        xs = np.arange(0., 10.5, .5)
        ys = np.arange(0., 10.5, .5)
        blocked = np.zeros((len(ys), len(xs)), dtype=bool)
        labels = np.zeros_like(blocked, dtype=int)
        ridge = np.ones_like(blocked, dtype=bool)
        blocked[12, :] = True
        labels[13:, :] = 1
        course = [(1., 3.), (2., 3.), (3., 3.), (4., 3.),
                  (5., 3.), (6., 3.), (7., 3.), (8., 3.), (9., 3.)]
        waypoints, details = repel_waypoints(
            course, xs, ys, blocked, labels, ridge,
            [[(0., 3.), (10., 3.)]])
        self.assertEqual(len(waypoints), 3)
        self.assertTrue(any(row["shift_mm"] > 0 for row in details))
        for (x, y), row in zip(waypoints, details):
            self.assertLessEqual(row["shift_mm"], 1.4)
            self.assertFalse(blocked[int(round(y * 2)), int(round(x * 2))])
            self.assertEqual(labels[int(round(y * 2)), int(round(x * 2))], 0)
            self.assertTrue(row["same_component"])

    def test_only_hypothetical_reduction_and_design_hard_gate(self) -> None:
        measured = spacing_scenarios(.22)
        self.assertAlmostEqual(
            measured["enforced_0_15"]["shortfall_mm"], .08)
        self.assertAlmostEqual(
            measured["hypothetical_0_10_not_authorized"]["shortfall_mm"], .03)
        self.assertFalse(
            measured["hypothetical_0_10_not_authorized"]
            ["valid_under_current_rules"])

    def test_uuid_detour_registry_is_pinned_and_unmodifiable(self) -> None:
        from probe_block2_uuid_detours import FIXED_DETOUR_ITEMS
        self.assertEqual(len(FIXED_DETOUR_ITEMS), 5)
        self.assertEqual(FIXED_DETOUR_ITEMS[
            "0c622acd-a2a9-440d-a4d0-7d8cdbdc7014"],
            ("MUX_EN", "pad"))
        self.assertEqual(FIXED_DETOUR_ITEMS[
            "3af750bf-ef0a-495a-9e9c-4af1480ec59d"],
            ("CH038_P_MUX", "track"))
        self.assertIn("uuid_detours=True", BODY)
        self.assertIn("detour_reach=7.2 if uuid_detours else 4.",
                      (ROOT / "probe_block2_macro_voronoi.py").read_text())
        self.assertIn("detour_reach = 7.2 if uuid_detours else 3.2",
                      (ROOT / "probe_block2_cbs_fcu3.py").read_text())
        for forbidden in ("SaveBoard(", "make_via(", "ExportGerbers("):
            self.assertNotIn(forbidden,
                (ROOT / "probe_block2_uuid_detours.py").read_text())

    def test_failed_search_frontier_grid_diagnosis_only(self) -> None:
        import numpy as np

        xs = np.arange(0., 8., .22)
        ys = np.arange(0., 8., .22)
        blocked = np.zeros((len(ys), len(xs)), dtype=bool)
        blocked[:, 18] = True
        out = sampled_reachability(
            xs, ys, blocked, (1., 1.), (7., 7.))
        self.assertFalse(out["same_sampled_free_component"])
        self.assertTrue(out["not_a_cutset_or_DRC_proof"])
        self.assertGreater(out["visited_nodes"], 20)
        self.assertGreater(len(out["frontier_points_mm"]), 0)

    def test_no_release_or_layer_relaxation(self) -> None:
        ast.parse(ELASTIC)
        for token in (
            "def repulsion_field(",
            "def repel_waypoints(",
            "def rubber_band_routes(",
            "def _rubber_trace(",
            '"topology_crossing_free"',
            '"zero_width_is_not_DRC": True',
            '"rubber_inflation_requires_cbs"',
            '"rubber_pairwise_minimum_mm"',
            '"topology_separated_for_inflation"',
            "separation_mm=.30001",
            "width_aware_corridor_priority_checked",
            "\"topology_separation_attempts\"",
            "\"width_aware_fixed_copper\"",
            "native_fixed_copper_0.15mm_width_clearance",
            "fixed_copper_cutset_analysis",
            "failed_topology_frontier",
            "inspect_failed_frontier",
            "uuid_detours_enabled",
            "detour_reach = 7.2 if uuid_detours else 4.4",
            "hard_detours",
            "inspect_cutset(",
            "tuple(reversed(order))",
            "rubber_repulsion = np.zeros",
            "rubber_repulsion[y, x]",
            'layers=(pcbnew.F_Cu, pcbnew.B_Cu)',
            'max_nodes=budget',
            '"rubber_inflated_three_unverified"',
        ):
            self.assertIn(token, ELASTIC)
        for forbidden in ("make_via(", "SaveBoard(", "ExportGerbers(",
                          "ExportDrill(", "pcbnew.In1_Cu"):
            self.assertNotIn(forbidden, ELASTIC)

    def test_nbody_new_solver_is_bounded_and_fail_closed(self) -> None:
        for token in (
            '"elastic_three_enabled": elastic_three',
            "from probe_block2_elastic_routes import rubber_band_routes",
            "rubber_band_routes(",
            "repulsion_guidance",
            "require_unchanged_components(",
            '"--elastic-three"',
        ):
            self.assertIn(token, BODY)


if __name__ == "__main__":
    unittest.main()

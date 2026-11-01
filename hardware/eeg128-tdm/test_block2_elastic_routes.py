#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic unit checks for elastic, fail-closed topology primitives."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from probe_block2_elastic_routes import _nearest_distance, repel_waypoints

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
            "bounded_preinflation_separation_pass_",
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

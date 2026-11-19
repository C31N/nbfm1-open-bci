#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native hard-clearance and early continuous-segment anchor preflight."""
from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import GeometryCollection, box

from local_joint_anchor_preflight import preflight_joint_entry_exit
from probe_block2_elastic_joint_corridor import FCuCorridorGrid

Node = tuple[int, int]


class JointAnchorFirstStepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.xs = np.arange(0., 5.5001, .22)
        self.ys = np.arange(0., 4.4001, .22)
        self.starts: tuple[Node, Node, Node] = (
            (6, 4), (6, 7), (6, 10))
        self.goals: tuple[Node, Node, Node] = (
            (16, 4), (16, 7), (16, 10))
        self.masks = [
            np.zeros((len(self.ys), len(self.xs)), dtype=bool)
            for _ in range(3)]
        self.shapes = [GeometryCollection() for _ in range(3)]

    def grid(self) -> FCuCorridorGrid:
        return FCuCorridorGrid(
            self.masks, self.shapes, self.xs, self.ys)

    def test_valid_three_head_neighbourhood_is_drc_conservative(self) -> None:
        diag = preflight_joint_entry_exit(
            self.grid(), self.starts, self.goals)
        self.assertEqual(
            diag["status"], "JOINT_ANCHOR_FIRST_STEP_FEASIBLE")
        self.assertGreater(diag["source_legal_moves"], 0)
        self.assertGreater(diag["target_reverse_legal_moves"], 0)
        self.assertTrue(diag["native_exact_segment_gate"])
        self.assertFalse(diag["accepted"])
        self.assertFalse(diag["fabrication_release"])

    def test_no_move_with_native_masks_fails_closed(self) -> None:
        for i, (source, goal) in enumerate(zip(self.starts, self.goals)):
            self.masks[i][:] = True
            self.masks[i][source[1], source[0]] = False
            self.masks[i][goal[1], goal[0]] = False
        diag = preflight_joint_entry_exit(
            self.grid(), self.starts, self.goals)
        self.assertEqual(diag["status"], "JOINT_ANCHOR_FIRST_STEP_BLOCKED")
        self.assertEqual(diag["source_legal_moves"], 0)
        self.assertEqual(diag["target_reverse_legal_moves"], 0)

    def test_native_copper_between_grid_points_is_blocking(self) -> None:
        # The endpoints remain raster-free; copper crosses their segment.
        middle_x = float(self.xs[6] + .11)
        y = float(self.ys[4])
        self.shapes[0] = box(
            middle_x - .02, y - .02,
            middle_x + .02, y + .02)
        grid = self.grid()
        self.assertTrue(grid.is_point_drc_clear(0, (6, 4)))
        self.assertTrue(grid.is_point_drc_clear(0, (7, 4)))
        self.assertFalse(
            grid.is_segment_drc_clear(0, (6, 4), (7, 4)))
        diag = preflight_joint_entry_exit(
            grid, self.starts, self.goals)
        self.assertGreater(
            diag["reject_reasons"].get(
                "native_fixed_copper_or_mask", 0), 0)
        self.assertTrue(diag["native_exact_segment_gate"])

    def test_refuses_clearance_relaxation(self) -> None:
        with self.assertRaises(ValueError):
            preflight_joint_entry_exit(
                self.grid(), self.starts, self.goals,
                hard_pitch_mm=.299)


if __name__ == "__main__":
    unittest.main()

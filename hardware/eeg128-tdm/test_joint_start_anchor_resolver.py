#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic read-only Block2 boundary-anchor and frozen-copper tests."""
from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import GeometryCollection

from joint_start_anchor_resolver import AnchorResolution, resolve_window_anchors


class Window:
    def contains(self, p: tuple[float, float]) -> bool:
        return .2 <= p[0] <= 2.4 and 0. <= p[1] <= 2.5


class AnchorResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.xs = np.arange(0., 2.8001, .2)
        self.ys = np.arange(0., 2.8001, .2)
        self.paths = tuple(tuple((x, row) for x in range(13))
                           for row in (2, 6, 10))
        self.spans = ((3, 9), (3, 9), (3, 9))
        self.masks = [np.zeros((len(self.ys), len(self.xs)),
                               dtype=bool) for _ in range(3)]
        self.shapes = [GeometryCollection() for _ in range(3)]

    def resolve(
        self, *,
        paths: tuple[tuple[tuple[int, int], ...], ...] | None = None,
        masks: list[np.ndarray] | None = None,
        max_shift_nodes: int = 5,
    ) -> AnchorResolution:
        return resolve_window_anchors(
            paths if paths is not None else self.paths,
            self.spans,
            masks if masks is not None else self.masks,
            self.shapes, self.xs, self.ys, Window(),
            max_shift_nodes=max_shift_nodes)

    def test_direct_window_entry_preserves_outer_paths(self) -> None:
        result = self.resolve()
        self.assertEqual(result.status, "direct_window_entry")
        self.assertEqual(result.starts, (3, 3, 3))
        self.assertEqual(result.targets, (9, 9, 9))
        audit = result.as_diagnostic()
        self.assertTrue(audit["fixed_outside_paths_preserved"])
        self.assertFalse(audit["accepted"])
        self.assertFalse(audit["routing_completed"])
        self.assertFalse(audit["fabrication_release"])
        self.assertEqual(audit["new_vias_added"], 0)

    def test_shifted_along_path_keeps_original_endpoints(self) -> None:
        self.masks[0][2, 3] = True
        result = self.resolve()
        self.assertEqual(result.status, "shifted_along_path")
        self.assertEqual(result.starts, (4, 3, 3))
        self.assertEqual(result.targets, (9, 9, 9))

    def test_partial_free_net_is_diagnostic_not_a_waiver(self) -> None:
        self.masks[0][2, 3:9] = True
        result = self.resolve()
        self.assertEqual(result.status, "partial_free_net")
        self.assertIsNone(result.starts)
        self.assertIsNone(result.targets)
        self.assertTrue(result.as_diagnostic()[
            "partial_free_net_is_diagnostic_only"])

    def test_frozen_foreign_wires_block_invalid_triple(self) -> None:
        routes = list(self.paths)
        # Net 1 shares source-side copper with net 0, but diverges
        # before both window-entry anchors. Local rip-up must not silently
        # legalize the shared frozen copper.
        routes[1] = tuple([(0, 2), (1, 2), (2, 2)]
                          + [(x, 6) for x in range(3, 13)])
        result = self.resolve(paths=tuple(routes))
        self.assertEqual(
            result.status, "MIDPOINT_JOINT_START_ANCHORS_INVALID")
        self.assertIsNone(result.starts)

    def test_speculative_foreign_paths_may_be_discarded_not_frozen(self) -> None:
        routes = list(self.paths)
        routes[1] = tuple([(0, 2), (1, 2), (2, 2)]
                          + [(x, 6) for x in range(3, 13)])
        speculative = resolve_window_anchors(
            tuple(routes), self.spans, self.masks, self.shapes,
            self.xs, self.ys, Window(), speculative_outside=True)
        self.assertEqual(speculative.status, "speculative_joint_entry_exit")
        self.assertIsNotNone(speculative.starts)
        self.assertIsNotNone(speculative.targets)
        diag = speculative.as_diagnostic()
        self.assertTrue(diag["speculative_outside_replan_required"])
        self.assertFalse(diag["fixed_outside_paths_preserved"])
        self.assertFalse(diag["accepted"])
        self.assertFalse(diag["fabrication_release"])
        self.assertFalse(diag["locked_escape_ripup_permitted"])

    def test_speculative_mode_never_bypasses_native_masks(self) -> None:
        self.masks[0][2, 3:9] = True
        speculative = resolve_window_anchors(
            self.paths, self.spans, self.masks, self.shapes,
            self.xs, self.ys, Window(), speculative_outside=True)
        self.assertEqual(speculative.status, "partial_free_net")
        self.assertIsNone(speculative.starts)

    def test_multi_anchor_choices_are_bounded_and_deterministic(self) -> None:
        req = dict(
            paths=self.paths, spans=self.spans, masks=self.masks,
            shapes=self.shapes, xs=self.xs, ys=self.ys, window=Window(),
            speculative_outside=True, min_anchor_pitch_mm=.44,
            max_side_triplets=12, max_solutions=4)
        a = resolve_window_anchors(**req)
        b = resolve_window_anchors(**req)
        self.assertEqual(a.candidate_pairs, b.candidate_pairs)
        self.assertEqual(len(a.candidate_pairs), 4)
        self.assertEqual(len(set(a.candidate_pairs)), 4)
        self.assertGreater(len(set(c[0] for c in a.candidate_pairs)), 1)
        self.assertGreater(len(set(c[1] for c in a.candidate_pairs)), 1)
        self.assertEqual(a.candidate_pairs[0], (a.starts, a.targets))
        self.assertEqual(a.as_diagnostic()["eligible_candidate_count"], 4)
        self.assertFalse(a.as_diagnostic()["accepted"])
        self.assertFalse(a.as_diagnostic()["fabrication_release"])

    def test_anchor_minimum_pitch_is_not_relaxed_for_multiple_pairs(self) -> None:
        routes = tuple(tuple((x, row) for x in range(13))
                       for row in (2, 3, 4))
        result = resolve_window_anchors(
            routes, self.spans, self.masks, self.shapes,
            self.xs, self.ys, Window(), speculative_outside=True,
            min_anchor_pitch_mm=.44, max_solutions=4)
        for start, goal in result.candidate_pairs:
            for triplet in (start, goal):
                coords = [
                    (self.xs[routes[i][triplet[i]][0]],
                     self.ys[routes[i][triplet[i]][1]])
                    for i in range(3)]
                self.assertGreaterEqual(min(
                    float(np.linalg.norm(np.subtract(coords[i], coords[j])))
                    for i in range(3) for j in range(i + 1, 3)),
                    .44 - 1e-8)

    def test_rejects_unbounded_number_of_candidate_solutions(self) -> None:
        with self.assertRaises(ValueError):
            resolve_window_anchors(
                self.paths, self.spans, self.masks, self.shapes,
                self.xs, self.ys, Window(),
                speculative_outside=True, max_solutions=13)

    def test_wrong_mask_dimensions_fail_closed(self) -> None:
        self.masks[1] = np.zeros((3, 3), dtype=bool)
        with self.assertRaises(ValueError):
            self.resolve()

    def test_off_grid_paths_fail_closed(self) -> None:
        paths = list(self.paths)
        paths[0] = tuple((99, y) if idx == 4 else (x, y)
                         for idx, (x, y) in enumerate(paths[0]))
        with self.assertRaises(ValueError):
            self.resolve(paths=tuple(paths))

    def test_no_excessive_pitch_relaxation(self) -> None:
        with self.assertRaises(ValueError):
            resolve_window_anchors(
                self.paths, self.spans, self.masks, self.shapes,
                self.xs, self.ys, Window(), pitch_mm=.29)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Atomic speculative three-net outside reroute with strict validation."""
from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import GeometryCollection, box

from local_joint_rip_reroute import reassemble_speculative_outside

Node = tuple[int, int]


class SpeculativeOutsideRerouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.xs = np.arange(0., 2.8001, .2)
        self.ys = np.arange(0., 2.8001, .2)
        self.starts: tuple[Node, Node, Node] = (
            (0, 2), (0, 6), (0, 10))
        self.goals: tuple[Node, Node, Node] = (
            (12, 2), (12, 6), (12, 10))
        self.local_routes: tuple[tuple[Node, ...], ...] = tuple(
            tuple((x, row) for x in range(4, 9))
            for row in (2, 6, 10))
        self.tips = tuple(
            ((float(self.xs[a[0]]), float(self.ys[a[1]])),
             (float(self.xs[b[0]]), float(self.ys[b[1]])))
            for a, b in zip(self.starts, self.goals))
        self.empty = tuple(GeometryCollection() for _ in range(3))
        self.calls = 0

    def route_one(
        self, net: int, begin: Node, end: Node,
        reserved: list[object],
    ) -> tuple[Node, ...] | None:
        self.calls += 1
        if begin[1] != end[1]:
            return None
        if begin[0] <= end[0]:
            return tuple((x, begin[1])
                         for x in range(begin[0], end[0] + 1))
        return tuple((x, begin[1])
                     for x in range(begin[0], end[0] - 1, -1))

    def assemble(
        self, shapes: tuple[object, ...] | None = None,
    ) -> tuple[object, dict[str, object]]:
        return reassemble_speculative_outside(
            self.local_routes, self.starts, self.goals, self.tips,
            shapes if shapes is not None else self.empty,
            self.xs, self.ys, self.route_one)

    def test_complete_scratch_routes_are_continuously_validated(self) -> None:
        original = self.local_routes
        routes, diag = self.assemble()
        self.assertIsNotNone(routes)
        self.assertEqual(diag["status"],
                         "LOCAL_JOINT_SCRATCH_PROPOSAL_REVALIDATED")
        self.assertEqual(routes[0][0], self.starts[0])
        self.assertEqual(routes[0][-1], self.goals[0])
        self.assertEqual(self.local_routes, original)
        self.assertGreaterEqual(
            diag["minimum_complete_centreline_mm"], .3)
        self.assertFalse(diag["accepted"])
        self.assertFalse(diag["routing_completed"])
        self.assertFalse(diag["fabrication_release"])
        self.assertEqual(diag["new_vias_added"], 0)
        self.assertTrue(diag["native_DRC_still_required"])

    def test_outer_native_collision_rolls_back_all_nets(self) -> None:
        shape = box(.55, .25, .75, .55)
        shapes = (shape, self.empty[1], self.empty[2])
        routes, diag = self.assemble(shapes)
        self.assertIsNone(routes)
        self.assertEqual(diag["status"],
                         "LOCAL_JOINT_OUTSIDE_REPLAN_EXHAUSTED")
        self.assertTrue(diag["rollback_on_any_failure"])
        self.assertTrue(diag["locked_escapes_unchanged"])

    def test_hard_pairwise_local_collision_before_any_search(self) -> None:
        self.local_routes = (
            self.local_routes[0], self.local_routes[0],
            self.local_routes[2])
        routes, diag = self.assemble()
        self.assertIsNone(routes)
        self.assertEqual(diag["status"], "LOCAL_JOINT_PAIRWISE_COLLISION")
        self.assertEqual(self.calls, 0)

    def test_bad_callback_does_not_produce_partial_candidate(self) -> None:
        def wrong(
            net: int, begin: Node, end: Node,
            reserved: list[object],
        ) -> tuple[Node, ...]:
            return (begin, (99, 99))
        routes, diag = reassemble_speculative_outside(
            self.local_routes, self.starts, self.goals, self.tips,
            self.empty, self.xs, self.ys, wrong)
        self.assertIsNone(routes)
        self.assertEqual(diag["complete_candidates_checked"], 0)

    def test_smaller_than_minimum_pitch_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reassemble_speculative_outside(
                self.local_routes, self.starts, self.goals, self.tips,
                self.empty, self.xs, self.ys, self.route_one,
                pitch_mm=.2999)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Backtracking controller regression without requiring pcbnew."""
from __future__ import annotations
import time
import unittest
from collections.abc import Sequence
from typing import Any

from ch025_ripup_backtrack import bounded_ripup


class BoundedBacktrackTests(unittest.TestCase):
    def test_real_rollback_then_alternate_path_success(self) -> None:
        names = tuple(f"N{i}" for i in range(8))
        placed: dict[str, tuple[float, ...]] = {}
        gone = []
        def probe(name: str, margin: float, weight: float, pending: Sequence[str]) -> tuple[list[tuple[int, float, float]] | None, dict[str, Any]]:
            if name == "N1" and placed["N0"] == (3., .5):
                return None, {"blocked_by": "N0-first-choice"}
            return [(0, margin, weight), (0, margin+1, weight)], {}
        def place(name: str, path: list[tuple[int, float, float]]) -> list[str]:
            assert name not in placed
            placed[name] = (path[0][1], path[0][2])
            return [f"generated-{name}-{len(gone)}"]
        def undo(name: str, uuids: Sequence[str]) -> None:
            self.assertEqual(len(uuids), 1)
            self.assertTrue(uuids[0].startswith("generated-"+name))
            del placed[name]
            gone.append(name)
        out = bounded_ripup(names, probe, place, undo,
                            deadline=time.monotonic()+10)
        self.assertTrue(out["eight_geometric_paths_proposed"])
        self.assertGreaterEqual(out["backtracks"], 1)
        self.assertIn("N0", gone)
        self.assertEqual(len(placed), 8)
        self.assertFalse(out["accepted"])
        self.assertFalse(out["fabrication_release"])

    def test_incomplete_cleans_all_created_tracks(self) -> None:
        names = tuple(f"N{i}" for i in range(8))
        placed = set()
        def probe(name: str, margin: float, weight: float, pending: Sequence[str]) -> tuple[list[tuple[int, float, float]] | None, dict[str, Any]]:
            if name == "N7":
                return None, {"no_legal_corridor": True}
            return [(0, margin, weight), (0, margin+1, weight)], {}
        def place(name: str, path: list[tuple[int, float, float]]) -> list[str]:
            placed.add(name)
            return [f"new-{name}"]
        def undo(name: str, uuids: Sequence[str]) -> None:
            self.assertEqual(uuids, ["new-"+name] if isinstance(uuids, list)
                             else ("new-"+name,))
            placed.remove(name)
        out=bounded_ripup(names, probe, place, undo,
                          deadline=time.monotonic()+10,
                          max_probes=40, max_backtracks=3)
        self.assertFalse(out["eight_geometric_paths_proposed"])
        self.assertGreaterEqual(out["best_partial_count"], 7)
        self.assertEqual(placed, set())
        self.assertEqual(out["connected"], [])
        self.assertFalse(out["fabrication_release"])

    def test_joint_three_net_group_is_one_bounded_task(self) -> None:
        names = ("A", "B", "__JOINT__", "C", "D", "E")
        placed: set[str] = set()
        def probe(name: str, margin: float, weight: float,
                  pending: Sequence[str]) -> tuple[list[tuple[int, float, float]] | None, dict[str, Any]]:
            return [(0, margin, weight), (0, margin+1, weight)], {}
        def place(name: str, path: list[tuple[int, float, float]]) -> list[str]:
            placed.add(name)
            return ["generated-" + name]
        def undo(name: str, uuids: Sequence[str]) -> None:
            placed.remove(name)
        out = bounded_ripup(
            names, probe, place, undo, deadline=time.monotonic()+10)
        self.assertTrue(out["all_tasks_geometrically_proposed"])
        self.assertFalse(out["eight_geometric_paths_proposed"])
        self.assertEqual(len(placed), 6)
        self.assertFalse(out["accepted"])

    def test_duplicate_nets_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            bounded_ripup(("N",)*8, lambda *a: (None, {}),
                          lambda *a: [], lambda *a: None,
                          deadline=time.monotonic()+1)


if __name__ == "__main__":
    unittest.main()

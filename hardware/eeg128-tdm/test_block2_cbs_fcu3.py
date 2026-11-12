#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""CBS3 multi-net no-release and two-sided conflict branching contracts."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CBS = (ROOT / "probe_block2_cbs_fcu3.py").read_text()
BODY = (ROOT / "probe_block2_nbody_201.py").read_text()


class CBS3Tests(unittest.TestCase):
    def test_spatial_cbs_has_true_disjunctive_branching(self) -> None:
        ast.parse(CBS)
        ast.parse(BODY)
        for term in (
            "def spatial_cbs_fcu3(",
            "len(endpoints) != 3",
            "len(nets) != 3",
            "def low_level(",
            "def first_conflict(",
            "for agent,prohibited in ((i,ei),(j,ej)):",
            "newer[agent]=limits_by_net[agent] | forbidden_edges",
            "newpaths[agent]=reroute",
            "simultaneous_three_net_conflict_search",
            "CBS3_joint_FCu_candidate_unverified",
            "CBS3_conflict_tree_budget_exhausted",
            '"qualified":False',
        ):
            self.assertIn(term, CBS)
        for forbidden in ("make_via(", "SaveBoard(", "pcbnew.In1_Cu",
                          "ExportGerbers(", "ExportDrill("):
            self.assertNotIn(forbidden, CBS)

    def test_conflict_volume_and_exact_clearance_are_bounded(self) -> None:
        for required in (
            'selection: str = "length"',
            'selection in ("length", "conflict-volume")',
            'clearance_threshold = .300 - 1e-9',
            'if d<clearance_threshold:',
            'if line_i.distance(line_j)>=clearance_threshold:',
            'length_cost + 250.0*overlap',
            'copper[i].intersection(copper[j]).area',
        ):
            self.assertIn(required, CBS)
        self.assertIn('cbs_selection: str = "length"', BODY)
        self.assertIn('selection=cbs_selection', BODY)
        self.assertIn('"cbs_selection": cbs_selection', BODY)
        self.assertIn("reference_paths=tuple(references.get(net) for net in order)", BODY)
        self.assertIn("elif references or u4_fanout:", BODY)

    def test_corridor_bundle_is_optional_and_fail_closed(self) -> None:
        for term in (
            'split_mode: str = "single-edge"',
            'split_mode in ("single-edge", "corridor-bundle",',
            'for agent,prohibited in ((i,ei),(j,ej)):',
            'if post_fanout_split_mode == "corridor-bundle":',
            'if segment.distance(rival_line) < clearance_threshold',
            'bundle = frozenset((prohibited,)) | frozenset(local[:2])',
            'if gap <= 1.05',
            '"last_corridor_bundle_original_overlap_edges"',
            '"last_corridor_bundle_edge_count"',
        ):
            self.assertIn(term, CBS)
        for term in (
            'cbs_split_mode: str = "single-edge"',
            'split_mode="u4-corridor" if u4_fanout else cbs_split_mode',
            '"cbs_split_mode": cbs_split_mode',
            'cbs_split_mode=a.cbs_split_mode',
            'cbs_grid_mm=a.cbs_grid_mm',
            'step_mm=cbs_grid_mm',
        ):
            self.assertIn(term, BODY)

    def test_guided_CBS3_only_adds_positive_soft_corridor_cost(self) -> None:
        code = (Path(__file__).with_name("probe_block2_cbs_fcu3.py")).read_text()
        for token in (
            "reference_paths: tuple[list[Point] | None, ...] | None = None",
            "partial_reference_count",
            "missing_reference_agents",
            "reference_masks",
            "corridor_cost = (2.75",
            "rubber_band_guidance",
            "competitor_masks",
            "neighbor_cost = (12.0",
        ):
            self.assertIn(token, code)

    def test_connected_corridor_cbs_and_pinned_u4_escapes(self) -> None:
        from probe_block2_u4_corridors import (
            CH027_PINS, adaptive_cbs_regions,
            connected_conflict_corridor, rasterized_conflict_region_edges,
        )

        class Segment:
            def __init__(self, distance: float) -> None:
                self.distance_value = distance

            def distance(self, _rival: object) -> float:
                return self.distance_value

        segments = [(Segment(d), i) for i, d in enumerate(
            (1., .1, .07, .01, .03, .04, .5, 1.))]
        result = connected_conflict_corridor(
            segments, object(), 3, .3, max_edges=10)
        self.assertEqual(result, frozenset((0, 1, 2, 3, 4, 5, 6)))
        self.assertEqual(CH027_PINS, ("9a811be0", "515dd677"))
        import numpy as np
        xs = np.arange(0., 4., .3)
        ys = np.arange(0., 4., .3)
        corridor = frozenset({((4, 4), (5, 4))})
        expanded = rasterized_conflict_region_edges(
            corridor, xs, ys, padding_mm=.16)
        self.assertTrue(corridor.issubset(expanded))
        self.assertGreater(len(expanded), len(corridor))
        self.assertLessEqual(len(expanded), 320)
        strict = adaptive_cbs_regions(
            expanded, corridor, ((4, 4), (5, 4)),
            expanded=1, queued=0)
        self.assertEqual([mode for mode, _ in strict], ["spatial"])
        sparse = adaptive_cbs_regions(
            expanded, corridor, ((4, 4), (5, 4)),
            expanded=50, queued=0)
        self.assertEqual([mode for mode, _ in sparse],
                         ["spatial", "strand"])
        separate = adaptive_cbs_regions(
            frozenset(("a", "b", "c")), frozenset(("a", "b")),
            "a", expanded=50, queued=0)
        self.assertEqual([mode for mode, _ in separate],
                         ["spatial", "strand", "single-edge-rescue"])
        self.assertTrue(all(((4, 4), (5, 4)) in edges
                            for _, edges in sparse))
        with self.assertRaises(ValueError):
            rasterized_conflict_region_edges(
                corridor, xs, ys, padding_mm=.5)
        self.assertIn('split_mode="u4-corridor"', BODY)
        for token in (
            '"u4-corridor"',
            "verify_u4_escape_group(",
            "u4_first_conflict_priority",
            "connected_conflict_corridor(",
            '"u4_corridor_splits"',
            '"last_u4_corridor_edge_count"',
            "rasterized_conflict_region_edges(",
            '"last_u4_spatial_region_edges"',
            "adaptive_cbs_regions(",
            '"u4_disconnected_spatial_children"',
            '"u4_secondary_branches"',
        ):
            self.assertIn(token, CBS)
        for forbidden in ("SaveBoard(", "make_via(",
                          "ExportGerbers(", "ExportDrill("):
            self.assertNotIn(forbidden,
                (ROOT / "probe_block2_u4_corridors.py").read_text())

    def test_spatial_limit_fallback_and_exit_semantics(self) -> None:
        from probe_block2_u4_corridors import rasterized_conflict_region_edges
        import numpy as np
        xs = np.arange(0., 4., .3)
        ys = np.arange(0., 4., .3)
        corridor = frozenset(
            ((4 + i, 4), (5 + i, 4)) for i in range(4))
        record: dict[str, object] = {}
        fallback = rasterized_conflict_region_edges(
            corridor, xs, ys, max_region_edges=30, telemetry=record)
        self.assertEqual(fallback, corridor)
        self.assertIs(record["CBS3_spatial_limit_fallback_triggered"], True)
        self.assertEqual(record["CBS3_spatial_limit_fallback_count"], 1)
        self.assertGreater(record["CBS3_spatial_limit_fallback_last_edges"], 30)
        self.assertEqual(record["CBS3_spatial_limit_fallback_limit"], 30)

        no_fallback: dict[str, object] = {}
        expanded = rasterized_conflict_region_edges(
            corridor, xs, ys, max_region_edges=320,
            telemetry=no_fallback)
        self.assertGreater(len(expanded), len(corridor))
        self.assertNotIn("CBS3_spatial_limit_fallback_triggered", no_fallback)

        for token in (
            '"CBS3_lowlevel_outcomes"',
            '"CBS3_both_children_unspawned_count"',
            '"CBS3_last_conflict_both_children_unspawned"',
            '"CBS3_conflict_tree_bounded_dead_end"',
            '"CBS3_lowlevel_node_budget_limited"',
            '"CBS3_geometry_unsatisfiable_proven"',
            'telemetry=diag',
        ):
            self.assertIn(token, CBS)

    def test_deterministic_u4_fanout_geometry(self) -> None:
        from probe_block2_u4_corridors import (
            deterministic_u4_fanout_geometry,
        )
        import math
        from shapely.geometry import LineString
        # Three U4 pads on a 1.27-mm row, shuffled with the solver order.
        pads=((2.54,0.),(0.,0.),(1.27,0.))
        ends=tuple(((x,-12.),pad) for x,pad in
                   zip((2.54,0.,1.27),pads))
        wires,sides,normal,diag=deterministic_u4_fanout_geometry(
            pads,ends,lead_mm=2.,parallel_mm=1.5)
        self.assertEqual(sides,(1,1,1))
        self.assertEqual(normal,(0.,-1.))
        self.assertEqual(diag["tip_pitch_mm"],.300)
        self.assertEqual(diag["parallel_length_mm"],1.5)
        self.assertTrue(diag["no_new_vias"])
        self.assertEqual(set(wire[0] for wire in wires),set(pads))
        tips=sorted(wire[-1] for wire in wires)
        self.assertAlmostEqual(tips[1][0]-tips[0][0],.300,places=8)
        self.assertAlmostEqual(tips[2][0]-tips[1][0],.300,places=8)
        for wire in wires:
            self.assertAlmostEqual(
                math.dist(wire[1],wire[2]),1.5,places=8)
        for i in range(3):
            for j in range(i+1,3):
                self.assertGreaterEqual(
                    LineString(wires[i]).distance(LineString(wires[j])),
                    .300-1e-8)
        with self.assertRaises(RuntimeError):
            deterministic_u4_fanout_geometry(pads,ends,lead_mm=1.0)
        with self.assertRaises(RuntimeError):
            deterministic_u4_fanout_geometry(
                ((0.,0.),(.2,0.),(.4,0.)),ends)

    def test_u4_fanout_is_a_no_release_bounded_solver_stage(self) -> None:
        mod=(ROOT/"probe_block2_u4_corridors.py").read_text()
        for token in (
            "def native_u4_fanout_preflight(",
            "def deterministic_u4_fanout_geometry(",
            "def validate_fcu_three_paths(",
            '"native_obstacle_preflight_passed"',
            '"CH027_protected_UUIDs"',
            "min_d-1e-8",
            "all_201_whitelist_victims_still_required",
        ):
            self.assertIn(token,mod)
        for token in (
            "u4_fanout: bool = False",
            "native_u4_topological_preflight(",
            '"u4_deterministic_fanout_enabled"',
            '"u4_deterministic_fanout_diagnostic"',
            "fanout_sides[agent]",
            "mask |= u4_local_guard & (projection < (",
            "macro_global_detour_window",
            "u4_local_escape_guard_radius_mm",
            "LineString(fanout_wires[j]).buffer(.300-1e-9",
        ):
            self.assertIn(token,CBS)
        for token in (
            '"--u4-fanout"',
            "u4_fanout=u4_fanout",
            "validate_fcu_three_paths(",
            '"U4_fanout_triplet_preflight_rejected"',
            '"u4_fanout_triplet_preflight"',
        ):
            self.assertIn(token,BODY)
        for forbidden in ("make_via(", "SaveBoard(", "ExportGerbers(",
                          "ExportDrill("):
            self.assertNotIn(forbidden,mod)

    def test_nbody_runs_cbs_before_restitution(self) -> None:
        for term in (
            '"cbs_three_enabled": cbs_three',
            "if sum((bool(joint_three), bool(cbs_three), bool(macro_three))) > 1:",
            'from probe_block2_cbs_fcu3 import spatial_cbs_fcu3',
            "routes, diagnostic = spatial_cbs_fcu3(",
            '"CBS3_solver_returned"',
            '"CBS3_joint_three_rejected"',
            '"three_targets_completed_restoration_stage_entered"',
            'for uid in collided:',
            '"blocked_victim_UUIDs"',
            '"CH038_pre_return_native_DRC"',
            '"candidate_qualified_136"',
            '*(["--cbs-three"] if cbs_three else [])',
        ):
            self.assertIn(term, BODY)
        self.assertNotIn("make_via(", BODY)


if __name__ == "__main__":
    unittest.main()

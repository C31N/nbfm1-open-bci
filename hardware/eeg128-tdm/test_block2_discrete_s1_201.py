#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed exact-201, three-discrete-candidate S1 static CH018 test."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

SOURCE=(Path(__file__).with_name("probe_block2_discrete_s1_201.py")
        .read_text(encoding="utf-8"))


class DiscreteS1Tests(unittest.TestCase):
    def test_exact_pinned_201_and_immutable_ch038(self) -> None:
        ast.parse(SOURCE)
        for phrase in (
            "S1_UUID=",
            "PINNED_CANDIDATE_SHA",
            "source.parent.name!=\"CH038_PROBE_ONLY\"",
            "file_hash(pinned)!=PINNED_CANDIDATE_SHA",
            'len(removed)!=201 or S1_UUID not in removed',
            'set(removed)&set(CH038)',
            "strip_track_segments_by_uuid(source_text,set(removed))",
            "unchanged_fingerprints(board)!=protected",
            "track_inventory(board)",
            "pcbnew.PCB_VIA",
            "S2_S3_original_copper_readded",
        ):
            self.assertIn(phrase,SOURCE)

    def test_three_static_fcu_s1_routes_then_ch018(self) -> None:
        for phrase in (
            "for iteration in range(3):",
            "cost_regions=costs",
            "line.hausdorff_distance(p)",
            '"S1_homotopy_independence_proven":False',
            '"topological_independence_proven":False',
            "if chpath is None or len(chpath)<2",
            "if current[\"restored_victim_count\"]!=201:",
            "for uid in collided:",
            '"blocked_victim_UUIDs"',
            '"native_DRC_candidate_paths"',
            '"unconnected":138',
            "result[\"CH038_pre_return_DRC\"]!=BASE",
            '"fabrication_release":False',
        ):
            self.assertIn(phrase,SOURCE)

    def test_never_claim_topology_or_release_from_spatial_diversity(self) -> None:
        for bad in ("make_via(", "pcbnew.In1_Cu", "ExportGerbers(",
                    "ExportDrill(", "ExportBOM(", "ExportCPL("):
            self.assertNotIn(bad,SOURCE)
        self.assertIn("homotopy",SOURCE)
        self.assertIn("NO_RELEASE",SOURCE)


if __name__=="__main__":
    unittest.main()

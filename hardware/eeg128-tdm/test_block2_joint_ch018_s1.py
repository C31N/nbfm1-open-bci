#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed checks for the two-head CH018_P/MUX_S1 A* scratch trial."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_joint_ch018_s1.py")


class JointStateAStarTests(unittest.TestCase):
    def test_joint_a_star_is_one_queue_with_both_paths_in_state(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        ast.parse(text)
        for mandatory in (
            'def joint_fcu_astar(',
            'initial = (a0, b0, 0, (a0,), (b0,))',
            'a, b, turn, path_a, path_b',
            'queue = [(h(a0, b0), next(seq), 0.0, initial)]',
            'for dx, dy in MOVES:',
            'if collides(coord(head), coord(nxt), other_path):',
            'p1, p2 = path_a+(nxt,), path_b',
            'p1, p2 = path_a, path_b+(nxt,)',
            'next_turn = 1-which',
            'visited.add((path_a, path_b, turn))',
            'max_states=16000, seconds=95',
        ):
            self.assertIn(mandatory, text)
        self.assertNotIn('make_via(', text)

    def test_s1_exact_uuid_and_s2_s3_unmodified(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for mandatory in (
            'S1_UUID = "2ac3aecb-9a62-4bc7-846a-75a782ad0474"',
            'S1_removed_UUID',
            'S2_S3_original_copper_immutable',
            'strip_track_segments_by_uuid(',
            'source.read_text(encoding="utf-8"), {S1_UUID}',
            'if uid != S1_UUID',
            'unchanged_fingerprints(board)',
            'pcbnew.PCB_VIA',
            'PINNED_CANDIDATE_SHA',
            'layers=(pcbnew.F_Cu, pcbnew.B_Cu)',
            'any(p[0] != 0 for p in path)',
        ):
            self.assertIn(mandatory, text)

    def test_no_acceptance_without_independent_native_drc(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for mandatory in (
            'subprocess.run(', 'TemporaryDirectory(',
            'isolated_drc(board, baseline)',
            'isolated_drc(',
            'file_sha(archive) == source_sha',
            '"unconnected": 138',
            '"joint_138_DRC_qualified"',
            '"accepted": False', '"fabrication_release": False',
            '"checkpoint_promoted": False',
        ):
            self.assertIn(mandatory, text)
        for forbidden in (
            'ExportGerbers(', 'ExportDrill(', 'ExportBOM(',
            'ExportCPL(', 'SetLayer(pcbnew.In1_Cu)',
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

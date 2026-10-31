#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static contract checks for the non-producing fixed-copper upper bound."""
import ast
import re
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_fcu_fixed_cut_upperbound.py")


class FixedCutUpperboundTests(unittest.TestCase):
    def test_source_guards_and_protected_copper(self) -> None:
        source = SOURCE.read_text()
        for required in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "native_open_positions", "baseline_DRC",
            "CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX",
            "PRESERVE_CHANNELS", '"CH022_"', '"CH025_"', '"CH027_"',
            "upperbound_movable(net)", "pcbnew.F_Cu",
            "same_free_component", "original", "immutable_tracks_unchanged",
            "protected_footprints_unchanged", "via_UUID_set_unchanged",
            "source_unchanged", "fixed_only_partitioned_targets",
            '"accepted": False', '"fabrication_release": False',
        ):
            self.assertIn(required, source)
        for forbidden in (
            "pcbnew.SaveBoard(", "make_via(", "ExportGerbers",
            "ExportDrill", "ExportBOM", "ExportCPL",
            "SetLayer(pcbnew.In1_Cu)",
        ):
            self.assertNotIn(forbidden, source)

    def test_uuid_precise_scratch_cut_preserves_vias_and_other_tracks(self) -> None:
        source = SOURCE.read_text()
        tree = ast.parse(source)
        function = next(x for x in tree.body
                        if isinstance(x, ast.FunctionDef)
                        and x.name == "strip_track_segments_by_uuid")
        ns = {"re": re}
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     "<fixed-cut-test>", "exec"), ns)
        cut = ns["strip_track_segments_by_uuid"]
        board = (
            '(kicad_pcb\n'
            '  (segment (start 1 2) (end 3 4) (uuid "dead-beef"))\n'
            '  (segment (start 4 5) (end 6 7) (uuid "keep-this"))\n'
            '  (via (at 1 2) (uuid "keep-via"))\n'
            ')\n'
        )
        result = cut(board, {"dead-beef"})
        self.assertNotIn("dead-beef", result)
        self.assertIn("keep-this", result)
        self.assertIn("keep-via", result)
        with self.assertRaises(RuntimeError):
            cut(board, {"not-present"})

    def test_each_native_target_has_separate_progress_and_no_promotion(self) -> None:
        source = SOURCE.read_text()
        for required in (
            '"topology_requested_targets": list(topology_targets)',
            '"topology_completed_targets": []',
            'persist("fixed_only_topology_started_" + net)',
            'persist("fixed_only_topology_finished_" + net)',
            'if set(report["topology_completed_targets"]) != set(topology_targets)',
            'choices=TARGETS',
            'if target is not None and target not in TARGETS',
            '"fixed_only_partitioned_targets"',
        ):
            self.assertIn(required, source)

    def test_ch038_two_uuid_probe_is_protected_disposable_diagnostic(self) -> None:
        source = SOURCE.read_text()
        for required in (
            'CH038_EXPLORATORY_UUIDS = frozenset({',
            '"1a5c9937-f30d-4bf9-b20a-c65f47d46040"',
            '"f1271355-bfbd-4e09-b95f-b9d10b867e72"',
            'if explore_ch038 and target is None:',
            'if explore_ch038:',
            'if v["uuid"] in CH038_EXPLORATORY_UUIDS',
            'v["net"] != "CH038_P_MUX"',
            'strip_track_segments_by_uuid(',
            '"CH038_eligible_for_ripup_whitelist": False',
            '"CH038_restitution_verified": False',
            '"CH038_candidate_accepted": False',
            '"opens_FCu_path_diagnostic_only": False',
            '"candidate_qualified": False',
            'expected = {uid: signature for uid, signature in original.items()',
            'if uid not in remove_set',
            'via_set_same = (',
        ):
            self.assertIn(required, source)
        self.assertNotIn('return movable(net) or net == "CH038_P_MUX"', source)
        self.assertNotIn("pcbnew.SaveBoard(", source)

    def test_upperbound_source_never_publishes_candidate(self) -> None:
        source = SOURCE.read_text()
        self.assertIn('"saved_candidate_PCB": False', source)
        self.assertIn('"native_candidate_DRC_pass": False', source)
        self.assertIn("upperbound_only_not_routing_qualified", source)
        self.assertIn("TemporaryDirectory", source)
        self.assertIn("strip_track_segments_by_uuid", source)
        self.assertNotIn("board.Remove(item)", source)


if __name__ == "__main__":
    unittest.main()

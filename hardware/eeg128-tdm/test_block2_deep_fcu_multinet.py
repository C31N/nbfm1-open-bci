#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static fail-closed deep Block2 three-net cut and restitution checks."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_block2_deep_fcu_multinet.py")

class DeepBlock2Test(unittest.TestCase):
    def test_predictive_restitution_never_uses_unverified_fallback(self) -> None:
        text = SOURCE.read_text()
        for required in (
            "RESTITUTION_HOTSPOTS", "predictive_restitution_blocked_UUIDs",
            "predictive_restitution_routes_found",
            "predictive_restitution_native_DRC_clean",
            "predictive_restitution_deadlock_rejected",
            "reject_no_verified_FCu_return",
            "preserve-hotspots-32", "expanded-48",
            "candidate_L3_exact_zero", "candidate_In1_exact_zero",
        ):
            self.assertIn(required, text)
        self.assertNotIn("original_fallback_needs_native_DRC", text)
        self.assertNotIn("make_via(", text)

    def test_rollback_uses_scratch_native_drc_or_original_topology_restitution(self) -> None:
        text = SOURCE.read_text()
        rollback = text.split("            finally:", 1)[1]
        self.assertIn("pcbnew.LoadBoard(str(pcb_path))", rollback)
        self.assertIn("source_tracks = {", rollback)
        self.assertIn("PINNED_CANDIDATE_SHA", rollback)
        self.assertIn("predictive_deadlock_diagnostic_DRC", rollback)
        self.assertIn("Purely topological candidate", rollback)
        self.assertIn("board.Add(source_tracks[uid])", rollback)
        self.assertIn("row[\"rollback_from_pristine_source\"] = True", rollback)

    def test_victim_first_mux_s2_is_scratch_only_and_no_via(self) -> None:
        text = SOURCE.read_text()
        for required in (
            '"mux-s2-first-32"',
            'mux_s2_uid = "31a40ce9-1b3f-4f1a-b654-7fec9e793976"',
            'avoid_target_lanes',
            'early_mux_s2_reserved_UUIDs',
            'early_mux_s2_scratch_DRC',
            'early_FCu_copper_native_verification_pending',
            'victim_first_scratch_native_DRC_complete',
            'any(p[0] != 0 for p in early_path)',
            'rollback_from_pristine_source',
        ):
            self.assertIn(required, text)
        self.assertNotIn('make_via(', text)
        self.assertNotIn('SetLayer(pcbnew.In1_Cu)', text)

    def test_three_net_native_release_gates(self) -> None:
        text = SOURCE.read_text()
        for x in (
            "PINNED_CANDIDATE_SHA", "ARCHIVE_SHA256",
            "CH025_N_MUX", "CH027_N_MUX", "CH022_N_ELECTRODE",
            "MUX_EN", "full_eight_net_bbox_mm",
            "all_bbox_FCu_inventory", "deep_cut_order_UUIDs",
            "after_cut_components", "victim_restitution",
            "reachable_targets", "candidate_native_net_reduction_qualified",
            "same_free_component", "add_path",
            "native_target_open", "139 - len(row",
            "regressed_nets", "exact_native_difference",
            "native_In1_exact", "native_L3_exact",
            "new_vias_added", "all_originals_restituted",
            '"accepted": False', '"fabrication_release": False',
            "independent_replay_verified",
        ):
            self.assertIn(x, text)
        for forbidden in (
            "make_via(", "ExportGerbers", "ExportDrill",
            "ExportBOM", "ExportCPL", "SetLayer(pcbnew.In1_Cu)",
        ):
            self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()

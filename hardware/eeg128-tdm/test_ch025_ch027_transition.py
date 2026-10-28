#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static release checks for CH025/CH027 transition graph discovery."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("probe_ch025_ch027_transition.py")

class CH025CH027TransitionContract(unittest.TestCase):
    def test_protected_native_probe(self) -> None:
        source = SOURCE.read_text()
        funcs = {n.name for n in ast.parse(source).body
                 if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"run", "graph_components",
                         "power_via_guard", "main"} <= funcs)
        for token in ("PINNED_CANDIDATE_SHA", "CH027_ALT_VIA", "cooperative_all_originals_restored", "CH027_one_via_native_L3_and_mesh_trial",
                      "CH019_MUX_EN_frozen", "original_tracks_restored",
                      "power_via_copper_clearance_mm", "native_L3_full_route_qualified"):
            self.assertIn(token, source)
        self.assertIn("def component_cut_diagnostic", source)
        self.assertIn('"component_cut_diagnostic"', source)
        for token in ('"not_a_legal_route": True',
                      '"native_DRC_qualified": False',
                      '"exact_L3_qualified": False'):
            self.assertIn(token, source)
        self.assertIn("def gap_blocker_inventory", source)
        self.assertIn('"gap_blocker_inventory"', source)
        self.assertIn('"immutable_do_not_ripup"', source)
        self.assertIn('"ripup_authorized": False', source)
        self.assertIn('"native_DRC_qualified": False', source)
        self.assertIn('"virtual_specific_gap_cuts"', source)
        self.assertIn('"virtual_specific_gap_cuts_all_restituted"', source)
        self.assertIn('"unapproved_originals_physically_modified": False', source)
        self.assertIn('topo.get("component_cut_diagnostic", {})', source)
        for required in ('"existing_target_via_FCu_copper_contact"',
                         '"source_reaches_existing_via_FCu_copper"',
                         '"new_vias_required_by_this_screen": False',
                         '"native_DRC_qualified": False',
                         '"topological_via_paths_preview"'):
            self.assertIn(required, source)
        for forbidden in ("SaveBoard(", "ExportGerbers",
                          "ExportDrill", "fabrication_release\": True"):
            self.assertNotIn(forbidden, source)

if __name__ == "__main__":
    unittest.main()

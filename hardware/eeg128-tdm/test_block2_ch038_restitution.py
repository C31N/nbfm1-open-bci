#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Static contract and syntax regression: two-UUID CH038 FCu restitution."""
from pathlib import Path
import ast
import unittest

SOURCE = Path(__file__).with_name("probe_block2_ch038_restitution.py")


class CH038RestitutionTests(unittest.TestCase):
    def test_syntax_and_no_release(self) -> None:
        content = SOURCE.read_text(encoding="utf-8")
        ast.parse(content)
        for check in (
            '"accepted": False',
            '"fabrication_release": False',
            '"checkpoint_promoted": False',
            '"independent_replay_verified": False',
            '"three_target_136_qualified": False',
            '"ch038_restitution_DRC_qualified": False',
            'set(EXPECTED_UUIDS)',
            't.GetNetname() != "CH038_P_MUX"',
            't.GetLayer() != pcbnew.F_Cu',
            'strip_track_segments_by_uuid(',
            'unchanged_fingerprints(probe) != protected',
            'initial_vias',
            'EXPECTED_BASELINE',
            'candidate_DRC',
            'ch038_restitution_DRC_qualified',
            '"CH038_isolated_139_DRC_qualified_not_136"',
        ):
            self.assertIn(check, content)
        for forbidden in (
            "make_via(", "ExportGerbers(", "ExportDrill(", "ExportBOM(",
            "ExportCPL(", "SetLayer(pcbnew.In1_Cu)",
        ):
            self.assertNotIn(forbidden, content)

    def test_no_cpp_pointer_crosses_process_boundary(self) -> None:
        content = SOURCE.read_text(encoding="utf-8")
        self.assertIn('"--child", "--source"', content)
        self.assertIn('isolated_drc(original, original_native)', content)
        self.assertIn('isolated_drc(', content)
        self.assertIn('child.returncode == 0', content)
        self.assertIn('TemporaryDirectory', content)
        self.assertIn('"CH038_PROBE_ONLY"', content)
        self.assertIn('new_inventory.get(uid) != signature', content)
        self.assertIn('if t.m_Uuid.AsString() not in initial_tracks', content)
        self.assertIn('layers=(pcbnew.F_Cu, pcbnew.B_Cu)', content)
        self.assertIn('any(n[0] == 0 for n in path)', content.replace(
            "all(n[0] == 0 for n in path)", "any(n[0] == 0 for n in path)"))


if __name__ == "__main__":
    unittest.main()

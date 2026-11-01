#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed process boundaries for cooperative Block2 MUX_S1/S2."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
WORKER = (ROOT / "probe_block2_deep_fcu_multinet.py").read_text()
SUPERVISOR = (ROOT / "probe_block2_isolated_s1s2.py").read_text()


class IsolatedS1S2Tests(unittest.TestCase):
    def test_python_syntax_and_no_swig_supervisor_import(self) -> None:
        ast.parse(WORKER)
        tree = ast.parse(SUPERVISOR)
        imports = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        names = [alias.name for item in imports for alias in item.names]
        self.assertNotIn("pcbnew", names)
        self.assertNotIn("route_targeted_closure", names)

    def test_both_victims_owned_by_same_disposable_child(self) -> None:
        for literal in (
            '"mux-s1s2-first-32"',
            '"31a40ce9-1b3f-4f1a-b654-7fec9e793976"',
            '"2ac3aecb-9a62-4bc7-846a-75a782ad0474"',
            '"MUX_S2"', '"MUX_S1"',
            'early_mux_s1s2_reserved_UUIDs',
            'if disposable_worker:',
            'worker_scratch_disposable_no_reuse',
            'isolated_worker_closed_without_Swig_reload',
            'any(p[0] != 0 for p in early_path)',
            'cost_regions=((0, avoid_target_lanes, 40.0),)',
        ):
            self.assertIn(literal, WORKER)
        self.assertNotIn("make_via(", WORKER)

    def test_parent_independently_checks_pinned_139_and_never_accepts(self) -> None:
        for literal in (
            'subprocess.run(', '--single-strategy',
            '--disposable-worker', 'subprocess_baseline(',
            'EXPECTED_BASELINE',
            'source_archive_unchanged',
            'worker_scratch_discarded',
            '"accepted": False',
            '"fabrication_release": False',
            '"checkpoint_promoted": False',
            '"independent_replay_verified": False',
            'worker.returncode == 0',
        ):
            self.assertIn(literal, SUPERVISOR)
        for forbidden in (
            "import pcbnew", "pcbnew.LoadBoard(", "pcbnew.SaveBoard(",
            "ExportGerbers", "ExportDrill", "ExportBOM", "ExportCPL",
        ):
            self.assertNotIn(forbidden, SUPERVISOR)


if __name__ == "__main__":
    unittest.main()

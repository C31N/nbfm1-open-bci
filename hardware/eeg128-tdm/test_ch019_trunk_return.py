# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure offline tests: fail-closed CH019 segment restoration diagnostics."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock

import probe_ch019_trunk_return as mod


class CH019ReturnGuards(unittest.TestCase):
    def test_scope_is_exact(self) -> None:
        self.assertEqual(len(mod.TRUNK), 3)
        self.assertEqual(len(mod.ELECTRODE), 2)
        self.assertEqual(mod.COMBINATIONS['isolated'], mod.TRUNK[:1])
        self.assertEqual(mod.COMBINATIONS['adjacent'], mod.TRUNK[:2])
        self.assertEqual(mod.COMBINATIONS['entire_trunk'], mod.TRUNK)

    def test_all_release_claims_false(self) -> None:
        for field in ('accepted', 'routing_completed', 'fabrication_release',
                      'independent_replay_verified', 'native_qualification',
                      'manufacturing_files'):
            self.assertIs(mod.FLAGS[field], False)

    def test_missing_uuid_fails_closed(self) -> None:
        board = MagicMock()
        board.GetTracks.return_value = []
        with self.assertRaisesRegex(ValueError, 'UUID set'):
            mod.protected_selection(board, 'isolated')

    def test_pinned_endpoints_identified(self) -> None:
        self.assertEqual(mod.TRUNK[0], '752f59d7-57f9-46ee-b7cc-b45beae0a553')

    def test_no_untrusted_output_location(self) -> None:
        source = Path(mod.__file__).read_text()
        self.assertIn('args.output.resolve().is_relative_to(SOURCE)', source)
        self.assertIn('frozen_archive(args.archive)', source)
        self.assertNotIn("'accepted': True", source)
        self.assertNotIn('kicad-cli pcb export', source)

    def test_alternate_ic_first_sequence_is_explicit(self) -> None:
        text = Path(mod.__file__).read_text()
        self.assertIn("choices=('ch024-first', 'ch019-first')", text)
        self.assertIn("choices=('R295.2', 'R39.1', 'U3.6')", text)
        self.assertIn("sequence == 'ch019-first'", text)
        self.assertIn("'ch019_root': ch019_root", text)

    def test_save_is_only_in_temporary_trial(self) -> None:
        source = Path(mod.__file__).read_text()
        self.assertIn('with tempfile.TemporaryDirectory', source)
        self.assertIn('finally:', source)
        self.assertIn('for track in chosen:', source)
        self.assertIn("result['L3_loss_mm2']", source)
        self.assertIn("result['L3_gain_mm2']", source)


if __name__ == '__main__':
    unittest.main()

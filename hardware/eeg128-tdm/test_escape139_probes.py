#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed guards for unadopted 139-airwire preparatory reroutes."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

import replay_escape139_probes as replay


class PreparatoryEscapeGuards(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        with zipfile.ZipFile(replay.ROOT / 'engineering/block2-ch019-electrode-closed139.zip') as bundle:
            bundle.extractall(self.folder)
        self.board = self.folder / 'eeg128-tdm.kicad_pcb'
        self.original = self.board.read_bytes()
        self.data = replay.recipe()

    def test_both_exact_applies_match_reviewed_hashes(self) -> None:
        for case in replay.ALLOWED:
            self.board.write_bytes(self.original)
            replay.apply(self.board, self.data, case)
            self.assertEqual(replay.digest(self.board), self.data['cases'][case]['expected_applied_sha256'])
            self.assertIs(self.data['cases'][case]['accepted'], False)

    def test_wrong_baseline_rejected_before_write(self) -> None:
        self.board.write_bytes(self.original + b'\n')
        before = self.board.read_bytes()
        with self.assertRaisesRegex(ValueError, 'baseline PCB SHA-256'):
            replay.apply(self.board, self.data, 'c22')
        self.assertEqual(before, self.board.read_bytes())

    def test_recipe_digest_pinned(self) -> None:
        altered = self.folder / 'altered.json'
        altered.write_bytes(replay.RECIPE.read_bytes() + b'\n')
        with patch.object(replay, 'RECIPE', altered):
            with self.assertRaisesRegex(ValueError, 'recipe SHA-256'):
                replay.recipe()

    def test_other_layer_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(iter(data['cases']['c22']['additions']))
        data['cases']['c22']['additions'][uid] = data['cases']['c22']['additions'][uid].replace(
            '"In2.Cu"', '"In1.Cu"')
        with self.assertRaisesRegex(ValueError, 'single-layer segment scope'):
            replay.apply(self.board, data, 'c22')
        self.assertEqual(self.original, self.board.read_bytes())

    def test_via_drop_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        data['cases']['c22']['additions']['bbed7fba-b23d-4964-a0b2-32259ff96307'] = (
            '(via (at 35.6 17.275) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") '
            '(net 1) (uuid "bbed7fba-b23d-4964-a0b2-32259ff96307"))')
        with self.assertRaisesRegex(ValueError, 'single-layer segment scope'):
            replay.apply(self.board, data, 'c22')
        self.assertEqual(self.original, self.board.read_bytes())


if __name__ == '__main__':
    unittest.main()

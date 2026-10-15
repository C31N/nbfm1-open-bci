#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-before-write checks for the unadopted CH030 B.Cu diagnostic."""
import copy
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import replay_ch030_probe as replay
from merge_native_closure import copper


class Ch030ProbeGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        with zipfile.ZipFile(replay.ROOT / 'engineering/block2-ch025-electrode-closed140.zip') as bundle:
            bundle.extractall(self.folder)
        self.board = self.folder / 'eeg128-tdm.kicad_pcb'
        self.original = self.board.read_bytes()
        self.data = replay.recipe()

    def test_exact_apply_matches_reviewed_hash(self) -> None:
        replay.apply(self.board, self.data)
        self.assertEqual(replay.digest(self.board), self.data['expected_applied_sha256'])
        self.assertEqual(len(copper(self.board.read_text())), 12228)

    def test_wrong_baseline_fails_before_write(self) -> None:
        self.board.write_bytes(self.original + b'\n')
        before = self.board.read_bytes()
        with self.assertRaisesRegex(ValueError, 'baseline PCB SHA-256'):
            replay.apply(self.board, self.data)
        self.assertEqual(self.board.read_bytes(), before)

    def test_modified_recipe_is_rejected(self) -> None:
        modified = self.folder / 'modified.json'
        modified.write_bytes(replay.RECIPE.read_bytes() + b'\n')
        with patch.object(replay, 'RECIPE', modified):
            with self.assertRaisesRegex(ValueError, 'recipe SHA-256'):
                replay.recipe()

    def test_l3_mutation_is_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(iter(data['additions']))
        data['additions'][uid] = data['additions'][uid].replace('(layer "B.Cu")', '(layer "In2.Cu")')
        with self.assertRaisesRegex(ValueError, 'outside the reviewed neighbor scope'):
            replay.apply(self.board, data)
        self.assertEqual(self.board.read_bytes(), self.original)

    def test_foreign_net_is_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(iter(data['additions']))
        foreign = re.search(r'\(net (\d+) "CH029_P_ELECTRODE"\)', self.original.decode())[1]
        data['additions'][uid] = re.sub(r'\(net \d+\)', f'(net {foreign})', data['additions'][uid])
        with self.assertRaisesRegex(ValueError, 'outside the reviewed neighbor scope'):
            replay.apply(self.board, data)
        self.assertEqual(self.board.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()

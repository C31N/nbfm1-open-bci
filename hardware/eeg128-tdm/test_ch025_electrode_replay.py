#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression checks for the immutable CH025 electrode closure."""
import copy
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import replay_ch025_electrode as replay
from replay_ch018_neighbors import number_pair
from merge_native_closure import copper


class Ch025ElectrodeGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        with zipfile.ZipFile(replay.ROOT / 'engineering/block2-ch029-electrode-closed141.zip') as bundle:
            bundle.extractall(self.folder)
        self.board = self.folder / 'eeg128-tdm.kicad_pcb'
        self.original = self.board.read_bytes()
        self.data = replay.recipe()

    def test_exact_apply_matches_reviewed_hash(self) -> None:
        replay.apply(self.board, self.data)
        self.assertEqual(replay.digest(self.board), self.data['expected_applied_sha256'])
        self.assertEqual(len(copper(self.board.read_text())), 12226)

    def test_wrong_baseline_fails_before_write(self) -> None:
        self.board.write_bytes(self.original + b'\n')
        before = self.board.read_bytes()
        with self.assertRaisesRegex(ValueError, 'baseline PCB SHA-256'):
            replay.apply(self.board, self.data)
        self.assertEqual(self.board.read_bytes(), before)

    def test_recipe_digest_is_pinned(self) -> None:
        modified = self.folder / 'modified.json'
        modified.write_bytes(replay.RECIPE.read_bytes() + b'\n')
        with patch.object(replay, 'RECIPE', modified):
            with self.assertRaisesRegex(ValueError, 'recipe SHA-256'):
                replay.recipe()

    def test_l2_mutation_is_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(uid for uid, block in data['additions'].items() if '(layer "F.Cu")' in block)
        data['additions'][uid] = data['additions'][uid].replace('(layer "F.Cu")', '(layer "In1.Cu")')
        with self.assertRaisesRegex(ValueError, 'outside the reviewed neighbor scope'):
            replay.apply(self.board, data)
        self.assertEqual(self.board.read_bytes(), self.original)

    def test_incomplete_via_is_rejected_before_write(self) -> None:
        data = copy.deepcopy(self.data)
        uid, via = next((uid, block) for uid, block in data['additions'].items()
                        if block.startswith('(via') and '(at 36 9.4)' in block)
        point = number_pair(via, 'at')
        for key, block in list(data['additions'].items()):
            if (block.startswith('(segment') and '(layer "F.Cu")' in block
                    and point in (number_pair(block, 'start'), number_pair(block, 'end'))):
                del data['additions'][key]
        self.assertIn(uid, data['additions'])
        with self.assertRaisesRegex(ValueError, 'Incomplete signal via'):
            replay.apply(self.board, data)
        self.assertEqual(hashlib.sha256(self.board.read_bytes()).digest(), hashlib.sha256(self.original).digest())


if __name__ == '__main__':
    unittest.main()

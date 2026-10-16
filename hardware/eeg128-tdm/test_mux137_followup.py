# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import copy
import hashlib
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from replay_mux137_followup import ROOT, apply, recipe


class S0PreparationGuards(unittest.TestCase):
    case = 's0'
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = recipe(cls.case)
        with zipfile.ZipFile(ROOT / 'engineering/followup-2026-10-16-trunks139/joint-trunks-closed137.zip') as bundle:
            cls.baseline = bundle.read('eeg128-tdm.kicad_pcb')

    def reject_without_write(self, data: dict[str, Any], message: str, content: bytes | None = None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'eeg128-tdm.kicad_pcb'
            before = self.baseline if content is None else content
            path.write_bytes(before)
            with self.assertRaisesRegex(ValueError, message):
                apply(path, data, self.case)
            self.assertEqual(path.read_bytes(), before)

    def test_exact_apply_and_closed_release(self) -> None:
        self.assertTrue(all(self.data[k] is False for k in
                            ('accepted', 'routing_completed', 'fabrication_release')))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'eeg128-tdm.kicad_pcb'
            path.write_bytes(self.baseline)
            apply(path, self.data, self.case)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             self.data['expected_applied_sha256'])

    def test_wrong_baseline_rejected(self) -> None:
        self.reject_without_write(self.data, 'Wrong baseline', self.baseline + b'\n')

    def test_unreviewed_layer_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(iter(data['additions']))
        block = data['additions'][uid]
        data['additions'][uid] = re.sub(
            r'\(layer "[^"]+"\)', '(layer "In1.Cu")', block)
        self.reject_without_write(data, 'reviewed layers')

    def test_new_via_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        additions = data['additions']
        code = re.search(r'\(net\s+(\d+)\)', next(iter(additions.values())))[1]
        uid = 'ffffffff-1370-4000-8000-000000000001'
        additions[uid] = ('(via (at 1 1) (size 0.6) (drill 0.3) '
                          '(layers "F.Cu" "B.Cu") (net ' + code + ') (uuid "' + uid + '"))')
        self.reject_without_write(data, 'Unreviewed via')

    def test_diagnostic_cannot_be_promoted(self) -> None:
        data = copy.deepcopy(self.data)
        data['accepted'] = True
        self.reject_without_write(data, 'scope or release flags')


class P25PreparationGuards(S0PreparationGuards):
    case = 'p25'


class JointPreparationGuards(S0PreparationGuards):
    case = 'joint'


if __name__ == '__main__':
    unittest.main()

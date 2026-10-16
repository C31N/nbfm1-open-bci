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
from replay_controls_header139 import ROOT, apply, recipe


class Round2Guards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = recipe()
        with zipfile.ZipFile(ROOT / 'engineering/block2-ch019-electrode-closed139.zip') as bundle:
            cls.baseline = bundle.read('eeg128-tdm.kicad_pcb')

    def reject_without_write(self, data: dict[str, Any], case: str,
                             message: str, content: bytes | None = None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'eeg128-tdm.kicad_pcb'
            before = self.baseline if content is None else content
            path.write_bytes(before)
            with self.assertRaisesRegex(ValueError, message):
                apply(path, data, case)
            self.assertEqual(path.read_bytes(), before)

    def test_exact_apply_and_closed_release(self) -> None:
        self.assertTrue(all(self.data[k] is False for k in
                            ('accepted', 'routing_completed', 'fabrication_release')))
        for case in ('controls', 'header'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'eeg128-tdm.kicad_pcb'
                path.write_bytes(self.baseline)
                apply(path, self.data, case)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 self.data['cases'][case]['expected_applied_sha256'])

    def test_wrong_baseline_rejected(self) -> None:
        self.reject_without_write(self.data, 'controls', 'Wrong immutable', self.baseline + b'\n')

    def test_unreviewed_layer_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        uid = next(iter(data['cases']['controls']['additions']))
        block = data['cases']['controls']['additions'][uid]
        data['cases']['controls']['additions'][uid] = re.sub(
            r'\(layer "[^"]+"\)', '(layer "In1.Cu")', block)
        self.reject_without_write(data, 'controls', 'reviewed layers')

    def test_isolated_via_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        additions = data['cases']['header']['additions']
        uid = next(u for u, block in additions.items() if block.startswith('(via'))
        additions[uid] = re.sub(r'\(at [^)]*\)', '(at 199 199)', additions[uid], count=1)
        self.reject_without_write(data, 'header', 'Incomplete signal via')

    def test_diagnostic_cannot_be_promoted(self) -> None:
        data = copy.deepcopy(self.data)
        data['cases']['header']['accepted'] = True
        self.reject_without_write(data, 'header', 'cannot become an accepted')


if __name__ == '__main__':
    unittest.main()

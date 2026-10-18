# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure guard tests for selective MUX/ELECTRODE trunk replacement."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock
import zipfile

import probe_block2_selective as mod


class SelectiveGuards(unittest.TestCase):
    def test_no_acceptance_or_manufacturing_flag(self) -> None:
        self.assertFalse(mod.OUTPUT_FLAGS['accepted'])
        self.assertFalse(mod.OUTPUT_FLAGS['fabrication_release'])
        self.assertFalse(mod.OUTPUT_FLAGS['routing_completed'])
        self.assertFalse(mod.OUTPUT_FLAGS['manufacturing_exports'])
        self.assertFalse(mod.OUTPUT_FLAGS['replay_qualified'])

    def test_requires_both_neighbor_nets_locally_displaced(self) -> None:
        e = MagicMock()
        e.GetNetname.return_value = 'CH022_N_ELECTRODE'
        m = MagicMock()
        m.GetNetname.return_value = 'CH018_N_MUX'
        self.assertFalse(mod.restored_each([e], ('CH022_N_ELECTRODE', 'CH018_N_MUX')))
        self.assertTrue(mod.restored_each([e, m], ('CH022_N_ELECTRODE', 'CH018_N_MUX')))

    def test_wrong_frozen_zip_cannot_be_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'fixture.zip'
            with zipfile.ZipFile(f, 'w') as archive:
                archive.writestr(mod.PCB, 'wrong')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                mod.frozen_archive(f)

    def test_expected_three_pad_guide(self) -> None:
        import json
        data = json.loads(mod.GUIDES.read_text())
        self.assertEqual(data['pads'], ['R49.1', 'U3.23', 'R305.2'])
        self.assertEqual(data['baseline_archive_sha256'], mod.ZIP_SHA)
        self.assertEqual(data['input_pcb_sha256'], mod.PCB_SHA)
        self.assertEqual(tuple(data['route_layer_indices']),
                         ('F.Cu', 'B.Cu', 'In2.Cu'))
        self.assertEqual(len(data['routes']), 2)

    def test_route_does_not_update_project_or_fabricate(self) -> None:
        body = Path(mod.__file__).read_text()
        self.assertNotIn("'accepted': True", body)
        self.assertNotIn('kicad-cli pcb export', body)
        self.assertNotIn('gerber', body.lower())
        self.assertNotIn('nc-drill', body.lower())
        self.assertIn('finally:', body)
        self.assertIn('for track in selected:', body)

    def test_sha_determinism(self) -> None:
        self.assertEqual(mod.digest(b'abc'), hashlib.sha256(b'abc').hexdigest())


if __name__ == '__main__':
    unittest.main()

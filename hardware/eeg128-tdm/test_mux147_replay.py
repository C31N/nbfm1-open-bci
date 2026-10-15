#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Incomplete signal vias and L2 mutations must fail before any PCB write."""
import copy
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from replay_mux147_routes import apply


class Mux147ReplayGuards(unittest.TestCase):
    def test_incomplete_via_and_l2_route_leave_baseline_bytes_unchanged(self) -> None:
        archive = Path(__file__).parent/'engineering/block2-ch099-closed147.zip'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(folder)
            board = folder/'eeg128-tdm.kicad_pcb'
            original = board.read_bytes()
            recipe = {'baseline_pcb_sha256': hashlib.sha256(original).hexdigest(),
                      'closed_nets': ['CH018_N_MUX'],
                      'routes': [{'net': 'CH018_N_MUX', 'secondary_layer': 'B.Cu',
                                  'path': [[0, 38.25, 26], [0, 38.75, 26],
                                           [1, 38.75, 26], [0, 38.75, 26],
                                           [0, 38.25, 26]]}]}
            with self.assertRaisesRegex(ValueError, 'Incomplete signal via'):
                apply(board, recipe)
            self.assertEqual(board.read_bytes(), original)
            illegal = copy.deepcopy(recipe)
            illegal['routes'][0]['secondary_layer'] = 'In1.Cu'
            with self.assertRaisesRegex(ValueError, 'L2 is protected'):
                apply(board, illegal)
            self.assertEqual(board.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()

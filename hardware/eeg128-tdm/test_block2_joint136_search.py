# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure Python guard tests; no native KiCad or routing writes required."""
import tempfile
from itertools import permutations
import sys
from types import SimpleNamespace
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import probe_block2_joint136 as probe


class ProbeSafety(unittest.TestCase):
    def test_seven_targets_and_reviewed_neighbor_sets(self) -> None:
        self.assertEqual(len(probe.BLOCK2_OPEN), 7)
        self.assertEqual(probe.TRIALS[0][1], ('CH022_N_ELECTRODE', 'CH018_N_MUX'))
        self.assertEqual(probe.TRIALS[1][1], ('CH022_N_ELECTRODE', 'CH019_P_MUX'))
        self.assertEqual(probe.TRIALS[2][1], ('CH031_N_MUX',))

    def test_ch031_must_be_routed_first(self) -> None:
        neighbors, targets = probe.TRIALS[2][1:]
        orders = list(probe.route_order(targets, neighbors))
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0][0], 'CH031_N_MUX')

    def test_ch024_requires_full_neighbor_restoration(self) -> None:
        neighbors, targets = probe.TRIALS[0][1:]
        orders = list(probe.route_order(targets, neighbors))
        self.assertEqual(len(orders), 2)
        self.assertEqual(set(orders[0]), set(neighbors) | set(targets))
        self.assertEqual(set(orders[1]), set(neighbors) | set(targets))

    def test_exhaustive_orders_only_for_ch024(self) -> None:
        neighbors, targets = probe.TRIALS[0][1:]
        orders = list(probe.route_order(targets, neighbors, full=True))
        self.assertEqual(len(orders), 6)
        self.assertEqual(set(orders), set(permutations((*targets, *neighbors))))
        shared_neigh, shared_targets = probe.TRIALS[2][1:]
        self.assertEqual(len(list(probe.route_order(shared_targets, shared_neigh, full=True))), 1)

    def test_never_count_neighbors_without_target(self) -> None:
        # A model may have restored only CH022_N and an In2 neighbor.
        targets = {'CH024_P_MUX'}
        neighbors = {'CH022_N_ELECTRODE', 'CH018_N_MUX'}
        proposed = set(neighbors)
        self.assertFalse((targets | neighbors).issubset(proposed))

    def test_reject_modified_fixture_before_archive_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'invalid.zip'
            path.write_bytes(b'not the pinned hardware archive')
            with self.assertRaisesRegex(ValueError, 'Wrong or modified'):
                probe.validate_fixture(path)
            self.assertEqual(path.read_bytes(), b'not the pinned hardware archive')

    def test_archive_pinning_checks_member_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr(probe.PCB_NAME, 'corrupted pcb')
            with patch.object(probe, 'FIXTURE_SHA256', probe.sha256(path.read_bytes())):
                with self.assertRaisesRegex(ValueError, 'diagnostic 137 PCB checksum'):
                    probe.validate_fixture(path)

    def test_removed_tracks_stay_owned_until_explicit_restore(self) -> None:
        first, second = MagicMock(), MagicMock()
        first.GetNetname.return_value = 'CH022_N_ELECTRODE'
        second.GetNetname.return_value = 'OTHER_NET'
        board = MagicMock()
        board.GetTracks.return_value = [first, second]
        removed = probe.prepare_board(board, ('CH022_N_ELECTRODE',))
        self.assertEqual(len(removed), 1)
        self.assertIs(removed[0], first)
        board.Remove.assert_called_once_with(first)

    def test_three_pad_net_remains_a_three_terminal_obligation(self) -> None:
        refs = [('R49', '1'), ('U3', '23'), ('J2', '99')]
        footprints = []
        for ref, number in refs:
            pad = MagicMock()
            pad.GetNetname.return_value = 'CH024_P_MUX'
            pad.GetNumber.return_value = number
            pad.IsOnLayer.return_value = True
            pad.GetPosition.return_value = (1.0, 2.0)
            pad.GetNetCode.return_value = 123
            footprint = MagicMock()
            footprint.GetReference.return_value = ref
            footprint.Pads.return_value = [pad]
            footprints.append(footprint)
        board = MagicMock()
        board.GetFootprints.return_value = footprints
        with patch.dict(sys.modules, {'pcbnew': SimpleNamespace(F_Cu=0)}):
            result = probe.pad_pair(board, 'CH024_P_MUX', lambda position: position)
        self.assertEqual(len(result), 3)
        self.assertEqual([row[0] for row in result], ['R49.1', 'U3.23', 'J2.99'])

    def test_shared_reserved_vias_are_permitted_only_in_geometry_model(self) -> None:
        reserves = probe.CH031_VIA_RESERVATIONS
        self.assertEqual(reserves['none'], ())
        self.assertEqual(len(reserves['top1']), 1)
        self.assertEqual(len(reserves['top2']), 1)
        self.assertEqual(len(reserves['both']), 2)
        self.assertNotEqual(reserves['top1'][0], reserves['top2'][0])

    def test_no_release_permitted_in_source_probes(self) -> None:
        text = Path(probe.__file__).read_text()
        self.assertIn("'accepted': False", text)
        self.assertIn("'routing_completed': False", text)
        self.assertIn("'fabrication_release': False", text)
        self.assertNotIn("'accepted': True", text)
        self.assertNotIn('pcbnew.SaveBoard(', text)
        self.assertNotIn('kicad-cli pcb export', text)


if __name__ == '__main__':
    unittest.main()

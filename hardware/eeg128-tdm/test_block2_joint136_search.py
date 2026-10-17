# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure Python guard tests; no native KiCad or routing writes required."""
import tempfile
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

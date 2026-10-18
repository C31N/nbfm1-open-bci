# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_block2_joint_pad_survey as s


class JointPadSurveySafety(unittest.TestCase):
    def test_no_release(self) -> None:
        for k in ('accepted','routing_completed','fabrication_release',
                  'independent_replay_verified','manufacturing_files'):
            self.assertIs(s.FLAGS[k], False)

    def test_no_source_board_writes(self) -> None:
        body=Path(s.__file__).read_text()
        self.assertNotIn("pcbnew.SaveBoard(", body)
        self.assertNotIn("kicad-cli pcb export", body)
        self.assertIn("J2.23",body)
        self.assertIn("R302.1",body)
        self.assertIn("U3.23",body)
        self.assertIn("FROZEN_INPUT_SHA",body)


if __name__ == '__main__':
    unittest.main()

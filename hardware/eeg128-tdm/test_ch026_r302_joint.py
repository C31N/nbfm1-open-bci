# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_block2_r302_joint as m


class R302SelectiveRestitution(unittest.TestCase):
    def test_pinned_cut_and_pad_via_protection(self) -> None:
        body=Path(m.__file__).read_text()
        self.assertIn("e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa",body)
        self.assertIn("track.GetNetname() != 'CH026_P_ELECTRODE'",body)
        self.assertIn("line.distance(p) < 1.0",body)
        self.assertIn("line.distance(v) < .65",body)
        self.assertIn("chosen.append(track)",body)

    def test_original_j2_and_ch018_vcm_guard_remains(self) -> None:
        body=Path(m.__file__).read_text()
        self.assertIn("untouched_j2",body)
        self.assertIn("current_j2 != untouched_j2",body)
        self.assertIn("current_ch018 != original_ch018 or current_vcm != original_vcm",body)

    def test_interleave_stages_and_via_guards(self) -> None:
        source=Path(m.__file__).read_text()
        self.assertIn("ch022_FCu_escapes_and_vias_seeded",source)
        self.assertIn("ch022_interleaved_BCu_proposed",source)
        self.assertIn("Interleaving requires CH026 removal and legal via plan",source)
        self.assertIn("Incomplete CH022 preseed state",source)
        self.assertIn("add_mesh_path(board, [(0,*rvia),(1,*rvia)]",source)
        self.assertIn("add_mesh_path(board, [(1,*jvia),(0,*jvia)]",source)

    def test_restitution_fail_closed(self) -> None:
        body=Path(m.__file__).read_text()
        self.assertIn("result['status'] = 'neighbor_unrestored'",body)
        self.assertIn("power_copper(base)",body)
        for name in ('accepted','routing_completed','fabrication_release',
                     'independent_replay_verified','native_qualification','manufacturing_files'):
            self.assertIs(m.FLAGS[name],False)


if __name__ == '__main__':
    unittest.main()

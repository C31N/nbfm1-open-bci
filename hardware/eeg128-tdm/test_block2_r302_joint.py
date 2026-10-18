# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest

import probe_block2_r302_joint as module


class CoupledR302U323Guards(unittest.TestCase):
    def test_release_flags_are_false(self) -> None:
        for k in ('accepted', 'routing_completed', 'fabrication_release',
                  'independent_replay_verified', 'native_qualification',
                  'manufacturing_files'):
            self.assertIs(module.FLAGS[k], False)

    def test_immutable_j2_and_analog_nets(self) -> None:
        text = Path(module.__file__).read_text()
        self.assertIn("untouched_j2", text)
        self.assertIn("in untouched_j2 for t in chosen", text)
        self.assertIn("'CH018_N_MUX'", text)
        self.assertIn("original_vcm", text)
        self.assertIn("current_j2 != untouched_j2", text)

    def test_coordination_uses_real_resource_reservation(self) -> None:
        text = Path(module.__file__).read_text()
        self.assertIn("extra_obstacles=extra", text)
        self.assertIn("Point(joint_pads[competing]).buffer(reserve_radius)", text)
        self.assertIn("'R302.1'", text)
        self.assertIn("'U3.23'", text)
        self.assertIn("'R305.2'", text)

    def test_strict_forced_via_windows(self) -> None:
        text = Path(module.__file__).read_text()
        self.assertIn("windows(board, code, pt, region, reserve)", text)
        self.assertIn("metric['windows'][0]['point']", text)
        self.assertIn("add_mesh_path(board, [(0,*rvia),(1,*rvia)]", text)
        self.assertIn("add_mesh_path(board, [(1,*jvia),(0,*jvia)]", text)
        self.assertIn("allow_vias=allow_vias", text)

    def test_no_production_export_or_release(self) -> None:
        text = Path(module.__file__).read_text()
        self.assertIn("TemporaryDirectory", text)
        self.assertNotIn("'accepted': True", text)
        self.assertNotIn("kicad-cli pcb export", text)
        self.assertIn("power_copper", text)
        self.assertIn("regressed_nets", text)


if __name__ == '__main__':
    unittest.main()

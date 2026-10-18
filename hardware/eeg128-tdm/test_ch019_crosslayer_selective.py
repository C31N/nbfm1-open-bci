# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations
from pathlib import Path
import unittest
import probe_ch019_crosslayer_selective as m


class CrosslayerSafeguards(unittest.TestCase):
    def test_immutable_control_nets(self) -> None:
        content=Path(m.__file__).read_text()
        self.assertIn("original_ch018",content)
        self.assertIn("original_vcm",content)
        self.assertIn("current_ch018 != original_ch018 or current_vcm != original_vcm",content)
        self.assertNotIn("GetNetname() == 'CH018_N_MUX' and",content)

    def test_selective_plan_scoped(self) -> None:
        self.assertEqual(len(m.CASES),7)
        self.assertTrue(all(k in ('CH026_P_MUX','CH027_P_MUX','MUX_EN','CH019_N_MUX','BANK1_P_MUX_OUT')
                            for case in m.CASES.values() for k in case))
        self.assertEqual(len(m.UUID_GROUPS['CH026_P_MUX']),4)
        self.assertEqual(len(m.UUID_GROUPS['CH027_P_MUX']),2)

    def test_release_unconditionally_locked(self) -> None:
        for key in ('accepted','routing_completed','fabrication_release',
                    'independent_replay_verified','native_qualification','manufacturing_files'):
            self.assertIs(m.FLAGS[key],False)

    def test_natives_are_temporary_only(self) -> None:
        content=Path(m.__file__).read_text()
        self.assertIn("with tempfile.TemporaryDirectory",content)
        self.assertIn("routing_domain(board, .30, .25)",content)
        self.assertNotIn("'accepted': True",content)
        self.assertNotIn("kicad-cli pcb export",content)


if __name__=='__main__':
    unittest.main()

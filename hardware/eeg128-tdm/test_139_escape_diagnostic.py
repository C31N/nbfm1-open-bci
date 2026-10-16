# SPDX-License-Identifier: CERN-OHL-S-2.0
import copy
import hashlib
import unittest
import zipfile
from replay_139_escape_diagnostic import ROOT, apply, reviewed_recipe

class EscapeDiagnosticGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=reviewed_recipe()
        with zipfile.ZipFile(ROOT/'engineering/block2-ch019-electrode-closed139.zip') as z:
            cls.text=z.read('eeg128-tdm.kicad_pcb').decode()

    def test_exact_replay_proposal_and_closed_release(self):
        result=apply(self.text,self.data)
        self.assertEqual(hashlib.sha256(result.encode()).hexdigest(),self.data['expected_applied_sha256'])
        self.assertTrue(all(self.data[k] is False for k in ('accepted','routing_completed','fabrication_release')))

    def test_wrong_baseline_rejected(self):
        with self.assertRaises(ValueError):apply(self.text+'\n',self.data)

    def test_inner_layer_addition_rejected(self):
        data=copy.deepcopy(self.data);uid=next(iter(data['additions']))
        data['additions'][uid]=data['additions'][uid].replace('"F.Cu"','"In2.Cu"')
        with self.assertRaisesRegex(ValueError,'Only reviewed'):apply(self.text,data)

    def test_unreviewed_via_rejected(self):
        data=copy.deepcopy(self.data);uid=next(iter(data['additions']))
        data['additions'][uid]=data['additions'][uid].replace('(segment','(via',1)
        with self.assertRaisesRegex(ValueError,'Only reviewed'):apply(self.text,data)

    def test_neighbor_net_change_rejected(self):
        data=copy.deepcopy(self.data);uid=next(iter(data['additions']))
        data['additions'][uid]=data['additions'][uid].replace('(net 584)','(net 1)')
        with self.assertRaisesRegex(ValueError,'Only reviewed'):apply(self.text,data)

if __name__=='__main__':unittest.main()

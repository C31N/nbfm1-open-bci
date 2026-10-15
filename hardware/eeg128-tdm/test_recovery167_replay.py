#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reject unsafe changes in the recovered 167-checkpoint copper recipe."""
import copy
import json
import re
import unittest
import zipfile
from pathlib import Path
from replay_copper_checkpoint import validate_recovery167


class RecoveryGuards(unittest.TestCase):
    def test_reviewed_recipe_and_unsafe_changes(self) -> None:
        root = Path(__file__).resolve().parent/'engineering'
        recipe = json.loads((root/'recovery167-recipes.json').read_text())
        with zipfile.ZipFile(root/'recovery-baseline167.zip') as z:
            text = z.read('eeg128-tdm.kicad_pcb').decode()
        self.assertTrue(validate_recovery167(recipe,text))
        removed = next(i for i,x in enumerate(recipe['changes']) if x['before'] is not None)
        segment = next(i for i,x in enumerate(recipe['changes']) if x['after'] and x['after'].startswith('(segment'))
        via = next(i for i,x in enumerate(recipe['changes']) if x['after'] and x['after'].startswith('(via'))
        cases = {
            'wrong baseline':lambda q:q['baseline_sha256'].__setitem__('.kicad_pcb','0'*64),
            'ADC replacement':lambda q:q['changes'][segment].__setitem__('net','ADC6_N'),
            'power mutation':lambda q:q['changes'][segment].__setitem__('net','3V3A'),
            'missing ripup':lambda q:q['changes'].pop(removed),
            'different removal':lambda q:q['changes'][removed].__setitem__('before',q['changes'][removed]['before'].replace('(width 0.15)','(width 0.2)')),
            'duplicate UUID':lambda q:q['changes'].append(copy.deepcopy(q['changes'][segment])),
            'ground-plane signal':lambda q:q['changes'][segment].__setitem__('after',re.sub(r'\(layer "[^\"]+"\)','(layer "In1.Cu")',q['changes'][segment]['after'])),
            'narrow track':lambda q:q['changes'][segment].__setitem__('after',q['changes'][segment]['after'].replace('(width 0.15)','(width 0.1)')),
            'small via':lambda q:q['changes'][via].__setitem__('after',q['changes'][via]['after'].replace('(size 0.6)','(size 0.5)')),
            'small drill':lambda q:q['changes'][via].__setitem__('after',q['changes'][via]['after'].replace('(drill 0.3)','(drill 0.2)')),
            'outside corridor':lambda q:q['changes'][segment].__setitem__('after',re.sub(r'\(start [-\d.]+ [-\d.]+\)','(start 90 60)',q['changes'][segment]['after'])),
            'wrong declared net':lambda q:q['changes'][segment].__setitem__('after',re.sub(r'\(net \d+\)','(net 0)',q['changes'][segment]['after'])),
            'missing restored net':lambda q:q.__setitem__('changes',[x for x in q['changes'] if x['net']!='CH004_N_MUX']),
        }
        if any(x['net']=='CH016_P_MUX' for x in recipe['changes']):
            cases['missing P counterpart'] = lambda q:q.__setitem__('changes',[x for x in q['changes'] if x['net']!='CH016_P_MUX'])
        for name,edit in cases.items():
            bad = copy.deepcopy(recipe)
            edit(bad)
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_recovery167(bad,text)
        print(f'{len(cases)} unsafe recovery recipes rejected')


if __name__=='__main__':
    unittest.main()

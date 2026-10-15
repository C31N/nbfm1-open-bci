# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import copy
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manufacturing',ROOT/'hardware/eeg128-tdm/generate_manufacturing.py')
manufacturing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manufacturing)


def test_drc_gate_rejects_each_nonzero_or_missing_category() -> None:
    clean = {'kicad_version':'8.0.9','violations':[],'unconnected_items':[],'schematic_parity':[]}
    manufacturing.require_clean_drc(clean)
    for key in ['violations','unconnected_items','schematic_parity']:
        for bad in [[{'severity':'warning'}],None,'0']:
            report = copy.deepcopy(clean);report[key] = bad
            with pytest.raises(RuntimeError):manufacturing.require_clean_drc(report)


def test_false_flags_block_without_cli_or_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = json.loads((ROOT/'hardware/eeg128-tdm/RELEASE_STATUS.json').read_text())
    flags = {key:True for key,value in baseline.items() if isinstance(value,bool)}
    status = tmp_path/'status.json';status.write_text(json.dumps(flags))
    monkeypatch.setattr(manufacturing,'STATUS',status)
    manufacturing.require_release()
    flags['routing_completed'] = 'false'
    status.write_text(json.dumps(flags))
    with pytest.raises(RuntimeError):manufacturing.require_release()
    output = tmp_path/'manufacturing'
    result = subprocess.run([sys.executable,str(ROOT/'hardware/eeg128-tdm/generate_manufacturing.py'),
                             '--output',str(output)],capture_output=True)
    assert result.returncode != 0 and not output.exists()


def test_all_true_flags_cannot_bypass_source_hash_gate() -> None:
    with pytest.raises(RuntimeError,match='source hashes'):
        manufacturing.native_release_preflight({})


def test_workflows_have_no_direct_manufacturing_export_commands() -> None:
    pattern = re.compile(r'kicad-cli\s+pcb\s+(?:export\s+)?(?:gerbers?|drill|pos)\b')
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        assert not pattern.search(path.read_text()), path


def test_native_placement_conversion_and_duplicate_rejection(tmp_path: Path) -> None:
    expected = tmp_path/'expected.txt';expected.write_text('Designator\nU_TEST\n')
    native = tmp_path/'native.txt';native.write_text('Ref,PosX,PosY,Rot,Side\nU_TEST,1.2,-3.4,-90,top\n')
    result = tmp_path/'result.txt'
    manufacturing.write_jlc_cpl(native,result,expected)
    assert 'U_TEST,1.200000mm,-3.400000mm,Top,270.000000' in result.read_text()
    native.write_text(native.read_text()+'U_TEST,1.2,-3.4,-90,top\n')
    with pytest.raises(RuntimeError):manufacturing.write_jlc_cpl(native,result,expected)

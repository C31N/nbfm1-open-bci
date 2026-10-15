#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fresh filled-power comparison to the immutable user-approved 143 baseline."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
import pcbnew
from audit_block1_corridor_geometry import power_copper, outlines

BASELINE_ZIP_SHA256 = 'e8d60a9835aea686af2d34d9e0e31b3a948b8c7dd2caae81c2c24786e4a3a8e1'
BASELINE_PCB_SHA256 = '497b588e580caf24766d5d60e9753def8dfe10ad3495b75faf5cd3fdd6276f24'


def audit(board: Path) -> dict[str,object]:
    archive = Path(__file__).parent/'engineering/block2-electrode-closed143.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != BASELINE_ZIP_SHA256:
        raise ValueError('Wrong power reference archive')
    with zipfile.ZipFile(archive) as bundle:
        data = bundle.read('eeg128-tdm.kicad_pcb')
    if hashlib.sha256(data).hexdigest() != BASELINE_PCB_SHA256:
        raise ValueError('Wrong power reference PCB')
    with tempfile.TemporaryDirectory(prefix='eeg128-power-reference-') as directory:
        source = Path(directory)/'reference.kicad_pcb';source.write_bytes(data)
        b0,b1 = pcbnew.LoadBoard(str(source)),pcbnew.LoadBoard(str(board))
        if not pcbnew.Version().startswith('8.') or outlines(b0) != outlines(b1):
            raise ValueError('KiCad version or power-zone outlines changed')
        p0,p1 = power_copper(b0),power_copper(b1)
        if p0.is_empty or not p0.is_valid or not p1.is_valid:
            raise ValueError('Invalid/empty reference geometry')
        result = {'baseline_pcb_sha256':BASELINE_PCB_SHA256,
                  'pcb_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),
                  'L3_power_loss_mm2':p0.difference(p1).area,
                  'L3_power_gain_mm2':p1.difference(p0).area}
        if result['L3_power_loss_mm2'] != 0:
            raise ValueError('Manufacturing blocked: L3 power copper displaced')
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.board)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Verify the engineering recovery archive and replay in fresh child processes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from native_connectivity import airwire_counts, regressed_nets
from run_native_closure import verify

HERE = Path(__file__).resolve().parent
ENGINEERING = HERE / 'engineering'
MEMBERS = tuple('eeg128-tdm' + ext for ext in
                ('.kicad_pcb', '.kicad_pro', '.kicad_dru'))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack(archive: Path, destination: Path, expected: dict[str, str]) -> Path:
    destination.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(MEMBERS):
            raise ValueError('Archive must contain exactly the three project members')
        for name in MEMBERS:
            target = destination / name
            target.write_bytes(bundle.read(name))
            if digest(target) != expected[name]:
                raise ValueError(f'Archive member hash differs: {name}')
    return destination / MEMBERS[0]


def clean_native(board: Path, expected_open: int) -> dict:
    hashes = {name: digest(board.parent / name) for name in MEMBERS}
    report = verify(board, board.parent / 'drc-native.json')
    all_items = (report['violations'] + report['unconnected_items']
                 + report.get('schematic_parity', []))
    if (report['kicad_version'] != '8.0.9' or report['violations']
            or any(item['severity'] == 'warning' for item in all_items)
            or len(report['unconnected_items']) != expected_open):
        raise ValueError('Native checkpoint metrics differ')
    if hashes != {name: digest(board.parent / name) for name in MEMBERS}:
        raise ValueError('Native refill changed an archived member')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path,
                        help='New, empty directory; existing directories are refused')
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    status = json.loads((ENGINEERING / 'STATUS.json').read_text())
    recipe = json.loads((ENGINEERING / 'recovery167-recipes.json').read_text())
    if status['routing_completed'] or status['fabrication_release']:
        raise ValueError('Recovery must remain engineering-only')
    subprocess.run(['sha256sum', '--quiet', '-c', 'CHECKPOINT_SHA256SUMS'],
                   cwd=ENGINEERING, check=True)
    if digest(ENGINEERING / 'latest-pcb.zip') != status['archive_sha256']:
        raise ValueError('Checkpoint archive hash differs')
    baseline_hashes = {'eeg128-tdm' + ext: value for ext, value
                       in recipe['baseline_sha256'].items()}
    baseline = unpack(ENGINEERING / 'recovery-baseline167.zip',
                      root / 'baseline', baseline_hashes)
    final = unpack(ENGINEERING / 'latest-pcb.zip', root / 'checkpoint',
                   status['package_sha256'])
    before = clean_native(baseline, 167)
    after = clean_native(final, status['unconnected'])
    if regressed_nets(before, after):
        raise ValueError('A previously closed net reopened')
    subprocess.run([sys.executable, str(HERE / 'replay_copper_checkpoint.py'),
                    '--board', str(baseline), '--recipe',
                    str(ENGINEERING / 'recovery167-recipes.json'),
                    '--output-dir', str(root / 'replay')], check=True)
    for name in MEMBERS:
        if (root / 'replay' / name).read_bytes() != (final.parent / name).read_bytes():
            raise ValueError(f'Replay is not byte-identical: {name}')
    counts = airwire_counts(after)
    result = {'kicad_version': after['kicad_version'], 'violations': 0,
              'warnings': 0, 'unconnected': len(after['unconnected_items']),
              'MUX_open': sum(v for n, v in counts.items() if n.endswith('_MUX')),
              'ELECTRODE_open': sum(v for n, v in counts.items()
                                    if n.endswith('_ELECTRODE')),
              'archive_sha256': digest(ENGINEERING / 'latest-pcb.zip'),
              'replay_byte_identical': True, 'manifest_verified': True,
              'routing_completed': False, 'fabrication_release': False,
              'independent_lvs_signoff': False}
    (root / 'verification-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

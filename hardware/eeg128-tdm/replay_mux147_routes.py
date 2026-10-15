#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Apply complete signal paths in isolation; independently verify every replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import uuid
from pathlib import Path
from typing import Any

from merge_native_closure import copper
from native_connectivity import regressed_nets
from replay_block2_source_window import MEMBERS, reproducible_zip
from run_native_closure import verify


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(board: Path, recipe: dict[str, Any]) -> None:
    import pcbnew
    from route_targeted_closure import add_path, xy
    from shapely.geometry import LineString, Point
    if digest(board) != recipe['baseline_pcb_sha256']:
        raise ValueError('Wrong baseline board')
    original = {ext: board.with_suffix(ext).read_bytes() for ext in ('.kicad_pro', '.kicad_dru')}
    existing = copper(board.read_text())
    b = pcbnew.LoadBoard(str(board))
    allowed = set(recipe['closed_nets'])
    if len(recipe['routes']) != len(allowed):
        raise ValueError('One complete route per declared net is required')
    seen = set()
    for route in recipe['routes']:
        name = route['net']
        if name in seen or name not in allowed or not re.fullmatch(r'CH\d{3}_[PN]_(MUX|ELECTRODE)', name):
            raise ValueError('Invalid or duplicate signal')
        seen.add(name)
        secondary = route.get('secondary_layer', 'B.Cu')
        if secondary not in ('B.Cu', 'In2.Cu'):
            raise ValueError('Only L3/L4 are permitted alongside L1; L2 is protected')
        path = route['path']
        if (len(path) < 2 or path[0][0] != 0 or path[-1][0] != 0
                or any(point[0] not in (0, 1) for point in path)):
            raise ValueError('Only complete F.Cu-to-F.Cu paths are allowed')
        if any(a[0] != z[0] and a[1:] != z[1:] for a, z in zip(path, path[1:])):
            raise ValueError('A via must not change coordinates')
        net = b.FindNet(name)
        if net is None:
            raise ValueError('Unknown signal')
        add_path(b, path, net.GetNetCode(), .15, .60,
                 layers=(pcbnew.F_Cu, pcbnew.B_Cu if secondary == 'B.Cu' else pcbnew.In2_Cu))
    # Drop incomplete probes before any PCB write. A signal via must have
    # actual nonzero copper support on at least two layers, not just a neck.
    for via in b.GetTracks():
        if not isinstance(via, pcbnew.PCB_VIA) or via.m_Uuid.AsString() in existing:
            continue
        support = {track.GetLayer() for track in b.GetTracks()
                   if not isinstance(track, pcbnew.PCB_VIA)
                   and track.GetNetCode() == via.GetNetCode()
                   and track.GetLength() > 0
                   and LineString([xy(track.GetStart()), xy(track.GetEnd())]).distance(Point(xy(via.GetPosition()))) < 2e-6}
        if len(support) < 2:
            raise ValueError('Incomplete signal via rejected before PCB write')
    pcbnew.SaveBoard(str(board), b)
    text = board.read_text()
    # Stable copper UUIDs make the native refill and archive replay byte-identical.
    additions = [(uid, block) for uid, block in copper(text).items() if uid not in existing]
    canonical = lambda item: re.sub(r'\s+', '', item[1].replace(item[0], ''))
    for index, (uid, block) in enumerate(sorted(additions, key=canonical)):
        stable = str(uuid.uuid5(uuid.NAMESPACE_URL,
                               recipe['baseline_pcb_sha256']+canonical((uid, block))+str(index)))
        text = text.replace(uid, stable)
    board.write_text(text)
    for ext, content in original.items():
        board.with_suffix(ext).write_bytes(content)


def geometry(baseline: Path, candidate: Path, names: set[str]) -> dict[str, Any]:
    import pcbnew
    from audit_block1_corridor_geometry import outlines, power_copper
    from verify_hardware_identity import balanced_blocks
    old, new = copper(baseline.read_text()), copper(candidate.read_text())
    norm = lambda s: re.sub(r'\s+', '', s)
    if not all(uid in new and norm(block) == norm(new[uid]) for uid, block in old.items()):
        raise ValueError('Existing copper changed')
    codes = {int(code): name for code, name in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', candidate.read_text())}
    added = {uid: block for uid, block in new.items() if uid not in old}
    if not added or any(codes[int(re.search(r'\(net\s+(\d+)\)', block)[1])] not in names for block in added.values()):
        raise ValueError('Unexpected new copper')
    if any('(segment' in block and not re.search(r'\(layer "(?:F|B|In2)\.Cu"\)', block) for block in added.values()):
        raise ValueError('New signal copper outside L1/L3/L4')
    if sorted(norm(x) for x in balanced_blocks(baseline.read_text(), 'footprint')) != sorted(norm(x) for x in balanced_blocks(candidate.read_text(), 'footprint')):
        raise ValueError('Footprints changed')
    b0, b1 = pcbnew.LoadBoard(str(baseline)), pcbnew.LoadBoard(str(candidate))
    if outlines(b0) != outlines(b1):
        raise ValueError('Zone outlines changed')
    if any(baseline.with_suffix(ext).read_bytes() != candidate.with_suffix(ext).read_bytes() for ext in ('.kicad_pro', '.kicad_dru')):
        raise ValueError('Project rules changed')
    p0, p1 = power_copper(b0), power_copper(b1)
    from shapely.geometry import LineString
    from route_targeted_closure import xy
    minimum = None
    for track in b1.GetTracks():
        if (track.m_Uuid.AsString() not in added or isinstance(track, pcbnew.PCB_VIA)
                or track.GetLayer() != pcbnew.In2_Cu):
            continue
        spacing = LineString([xy(track.GetStart()), xy(track.GetEnd())]).buffer(pcbnew.ToMM(track.GetWidth())/2).distance(p0)
        if spacing < .20-2e-6:
            raise ValueError('New L3 track invades the baseline power clearance')
        minimum = spacing if minimum is None else min(minimum, spacing)
    return {'existing_copper_unchanged': True, 'footprints_unchanged': True,
            'zone_outlines_unchanged': True, 'project_rules_unchanged': True,
            'added_copper_objects': len(added), 'L3_power_loss_mm2': p0.difference(p1).area,
            'L3_power_gain_mm2': p1.difference(p0).area,
            'minimum_new_L3_to_baseline_power_mm': minimum}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-zip', required=True, type=Path)
    parser.add_argument('--recipe', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--apply-only', action='store_true')
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    board = args.output_dir/'eeg128-tdm.kicad_pcb'
    if args.apply_only:
        apply(board, recipe)
        return
    # Keep native replay chains sequential as well as process-isolated.
    # The apply-only child must not reacquire its supervisor's lock.
    replay_lock = (Path(tempfile.gettempdir())/'eeg128-native-replay.lock').open('a+b')
    if sys.platform == 'win32':
        import msvcrt
        if replay_lock.tell() == 0:
            replay_lock.write(b'0')
            replay_lock.flush()
        replay_lock.seek(0)
        msvcrt.locking(replay_lock.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(replay_lock, fcntl.LOCK_EX)
    if digest(args.baseline_zip) != recipe['baseline_archive_sha256']:
        raise ValueError('Wrong baseline archive')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.baseline_zip) as z:
        if sorted(z.namelist()) != sorted(MEMBERS):
            raise ValueError('Exactly PCB/PRO/DRU are required')
        for name in MEMBERS:
            (args.output_dir/name).write_bytes(z.read(name))
    if digest(board) != recipe['baseline_pcb_sha256']:
        raise ValueError('Wrong baseline PCB')
    shutil.copy2(Path(__file__).parent/'engineering/eeg128-tdm.kicad_sch', board.with_suffix('.kicad_sch'))
    before = verify(board, args.output_dir/'drc-before.json')
    if before['kicad_version'] != '8.0.9':
        raise ValueError('The approved replay chain requires KiCad 8.0.9')
    if len(before['unconnected_items']) != recipe['before_unconnected']:
        raise ValueError('Wrong baseline connection count')
    # Preserve a separate geometry reference. Mutation and refill/DRC run
    # in different processes; no live mutated SWIG board enters verification.
    reference = args.output_dir/'reference'
    reference.mkdir()
    for name in MEMBERS:
        shutil.copy2(args.output_dir/name, reference/name)
    subprocess.run([sys.executable, __file__, '--baseline-zip', str(args.baseline_zip),
                    '--recipe', str(args.recipe), '--output-dir', str(args.output_dir),
                    '--apply-only'], check=True)
    from route_targeted_closure import native_fresh, metrics, net_of
    after = native_fresh(board, args.output_dir/'drc-after.json')
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
                    '--all-track-errors', '--format', 'json', '--output',
                    str(args.output_dir/'parity.json'), str(board)], check=True)
    parity = json.loads((args.output_dir/'parity.json').read_text())
    geo = geometry(reference/board.name, board, set(recipe['closed_nets']))
    (args.output_dir/'geometry.json').write_text(json.dumps(geo, indent=2)+'\n')
    remaining = {net_of(item) for item in after['unconnected_items']}
    accepted = (not after['violations'] and metrics(after)['warnings'] == 0
                and not parity['violations'] and not parity.get('schematic_parity')
                and not regressed_nets(before, after) and geo['L3_power_loss_mm2'] == 0
                and all(n not in remaining for n in recipe['closed_nets'])
                and len(after['unconnected_items']) == recipe['after_unconnected'])
    result = {**metrics(after), **geo, 'accepted': accepted,
              'kicad_version': after['kicad_version'],
              'closed_nets': recipe['closed_nets'], 'regressed_nets': regressed_nets(before, after),
              'diagnostic_parity_findings': len(parity.get('schematic_parity', [])),
              'pcb_sha256': digest(board), 'routing_completed': False, 'fabrication_release': False}
    if accepted:
        if recipe.get('expected_pcb_sha256') and digest(board) != recipe['expected_pcb_sha256']:
            raise ValueError('Verified replay PCB differs from the bound candidate hash')
        archive = args.output_dir/'candidate.zip'
        staging_archive = args.output_dir/'candidate.staging.zip'
        reproducible_zip(args.output_dir, staging_archive)
        if recipe.get('expected_archive_sha256') and digest(staging_archive) != recipe['expected_archive_sha256']:
            staging_archive.unlink()
            raise ValueError('Verified replay archive differs from the bound candidate hash')
        staging_archive.replace(archive)
        result['archive_sha256'] = digest(archive)
    else:
        board.unlink()
    (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

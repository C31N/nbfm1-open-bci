#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed, read-only search for fully restored Block-2 routing proposals.

Uses the SHA-pinned, unadopted joint-137 PCB (including S0/P25 preparation).
Hypothetical neighbor removals and route additions occur IN MEMORY ONLY.
No PCB, fabrication files, or accepted=true state are written.
A found path is NOT native DRC, SI, replay, or connectivity qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path

FIXTURE_SHA256 = 'a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041'
PCB_SHA256 = 'cac02064d9926676f6368536c4c104cb36295961333de6074e65fa1fa60a814c'
PCB_NAME = 'eeg128-tdm.kicad_pcb'
BLOCK2_OPEN = ('CH020_N_MUX', 'CH020_P_MUX', 'CH024_N_MUX', 'CH024_P_MUX',
               'CH028_N_MUX', 'CH029_N_MUX', 'CH030_N_MUX')
TRIALS = (
    ('ch024p-ch018', ('CH022_N_ELECTRODE', 'CH018_N_MUX'), ('CH024_P_MUX',)),
    ('ch024p-ch019', ('CH022_N_ELECTRODE', 'CH019_P_MUX'), ('CH024_P_MUX',)),
    ('shared-ch031', ('CH031_N_MUX',),
     ('CH020_P_MUX', 'CH028_N_MUX', 'CH029_N_MUX', 'CH030_N_MUX')),
)
POWER_EXCLUSION_MM = .505
EDGE_CLEARANCE_MM = .25
LAYERS = ('F.Cu', 'B.Cu', 'In2.Cu')
REGION_MM = (12, .5, 59, 69)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_fixture(path: Path) -> bytes:
    """Reject modified or unexpectedly packaged project data, before pcbnew."""
    if sha256(path.read_bytes()) != FIXTURE_SHA256:
        raise ValueError('Wrong or modified 137 preparatory archive')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not all('/' not in n and '\\' not in n for n in names):
            raise ValueError('Unexpected archive member paths')
        if PCB_NAME not in names:
            raise ValueError('Missing pinned PCB member')
        content = archive.read(PCB_NAME)
    if sha256(content) != PCB_SHA256:
        raise ValueError('Wrong diagnostic 137 PCB checksum')
    return content


def pad_pair(board, net_name, xy):
    pads = [(footprint.GetReference(), pad) for footprint in board.GetFootprints()
            for pad in footprint.Pads() if pad.GetNetname() == net_name]
    if len(pads) != 2:
        raise ValueError(f'{net_name}: exactly two pads required, got {len(pads)}')
    # Deliberately use native F.Cu pads; no inferred or invented via escapes.
    if any(not pad.IsOnLayer(__import__('pcbnew').F_Cu) for _, pad in pads):
        raise ValueError(f'{net_name}: endpoint requires a non-F.Cu pad')
    source = next(((ref, pad) for ref, pad in pads if ref.startswith('R') and pad.GetNumber() == '1'), None)
    target = next(((ref, pad) for ref, pad in pads if ref.startswith('U')), None)
    if source and target:
        pads = [source, target]
    return [(ref + '.' + pad.GetNumber(), xy(pad.GetPosition()), pad.GetNetCode())
            for ref, pad in pads]


def route_order(targets, neighbors):
    """Try target-first and restitution-first; never rely on a lone freed target."""
    yield tuple(neighbors) + tuple(targets)
    if len(targets) == 1:
        yield tuple(targets) + tuple(neighbors)


def prepare_board(board, removals):
    import pcbnew
    removed = [t for t in board.GetTracks() if t.GetNetname() in removals]
    if set(t.GetNetname() for t in removed) != set(removals):
        raise ValueError('Missing required closed neighbor copper')
    for track in removed:
        board.Remove(track)
    return len(removed)


def probe(archive: Path, cases: tuple[str, ...], include_mesh: bool) -> dict:
    import pcbnew
    from shapely.geometry import box
    from analyze_139_escape_blockers import protected_power, windows
    from route_targeted_closure import xy
    from escape_mesh_505 import mesh_route, add_mesh_path

    fixture = validate_fixture(archive)
    region = box(*REGION_MM)
    report = {
        'model_only': True, 'accepted': False, 'routing_completed': False,
        'fabrication_release': False, 'pcb_written': False,
        'manufacturing_artifacts_created': False,
        'native_drc_verified': False, 'independent_byteidentical_replay_verified': False,
        'baseline_archive_sha256': FIXTURE_SHA256,
        'baseline_pcb_sha256': PCB_SHA256,
        'L3_power_exclusion_mm': POWER_EXCLUSION_MM,
        'edge_clearance_mm': EDGE_CLEARANCE_MM,
        'searched_layers': list(LAYERS), 'trials': [],
    }
    with tempfile.TemporaryDirectory(prefix='block2-model-only-') as directory:
        source = Path(directory) / PCB_NAME
        source.write_bytes(fixture)
        for name, neighbors, targets in TRIALS:
            if name not in cases:
                continue
            for order in route_order(targets, neighbors):
                board = pcbnew.LoadBoard(str(source))
                power = protected_power(board)
                removed = prepare_board(board, neighbors)
                trial = {
                    'name': name, 'routing_order': list(order), 'removed_neighbor_copper': removed,
                    'all_neighbors_restituted': False, 'accepted': False,
                    'model_only': True, 'successfully_proposed_nets': [],
                    'windows': {}, 'proposed_paths': {}, 'failed_net': None,
                }
                for net_name in targets:
                    pts = pad_pair(board, net_name, xy)
                    code = pts[0][2]
                    trial['windows'][net_name] = {
                        label: windows(board, code, point, region, power)[1]
                        for label, (_, point, _) in zip(('source', 'target'), pts)
                    }
                if include_mesh:
                    for net_name in order:
                        try:
                            pts = pad_pair(board, net_name, xy)
                            if pts[0][2] != pts[1][2]:
                                raise ValueError('Net-code mismatch')
                            proposal = mesh_route(
                                board, pts[0][1], pts[1][1], pts[0][2],
                                (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu),
                                power, region)
                            if not proposal:
                                trial['failed_net'] = net_name
                                break
                            if any(not all(math.isfinite(p) for p in n[1:]) for n in proposal):
                                raise ValueError('Non-finite path output')
                            trial['proposed_paths'][net_name] = proposal
                            # Add in memory so later nets see the newly occupied copper.
                            add_mesh_path(board, proposal, pts[0][2],
                                          (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu))
                            trial['successfully_proposed_nets'].append(net_name)
                        except (ValueError, RuntimeError) as error:
                            trial['failed_net'] = net_name
                            trial['search_error'] = str(error)
                            break
                if set(neighbors).issubset(trial['successfully_proposed_nets']):
                    trial['all_neighbors_geometrically_proposed'] = True
                else:
                    trial['all_neighbors_geometrically_proposed'] = False
                # Even a geometrically complete plan is unverified without native
                # refill, DRC, power-difference, connectivity and independent replay.
                report['trials'].append(trial)
    if sha256(archive.read_bytes()) != FIXTURE_SHA256:
        raise ValueError('Pinned source archive changed during modeling')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True,
                        help='SHA-pinned joint-unadopted137.zip containing S0+CH025-P preparation')
    parser.add_argument('--output', type=Path, required=True, help='Diagnostic JSON only')
    parser.add_argument('--case', choices=[t[0] for t in TRIALS], action='append')
    parser.add_argument('--skip-mesh', action='store_true',
                        help='Run only source/target window mapping')
    args = parser.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Must create a fresh .json diagnostic output')
    if not args.output.parent.is_dir():
        raise ValueError('Output directory does not exist')
    # Reject any output inside the repository's immutable diagnostic bundle.
    if args.output.resolve() == args.archive.resolve():
        raise ValueError('Cannot overwrite pinned input')
    result = probe(args.archive, tuple(args.case or [t[0] for t in TRIALS]),
                   not args.skip_mesh)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'trials': len(result['trials']), 'accepted': False,
                      'model_only': True, 'output': str(args.output)}))


if __name__ == '__main__':
    main()

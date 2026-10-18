#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Try local copper-segment replacement, preserving all untouched neighbor escapes.

SHA-pinned joint-137+S0/P25 input. No baseline writes or manufacturing exports.
A geometrical proposal is not an accepted or qualified 136 checkpoint.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any
import zipfile

PCB = 'eeg128-tdm.kicad_pcb'
ZIP_SHA = 'a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041'
PCB_SHA = 'cac02064d9926676f6368536c4c104cb36295961333de6074e65fa1fa60a814c'
LAYER_NAMES = ('F.Cu', 'B.Cu', 'In2.Cu')
ROOT = Path(__file__).resolve().parent
GUIDES = ROOT / 'engineering/block2_ch024p_selective_guides.json'
OUTPUT_FLAGS = {'model_only': True, 'accepted': False, 'routing_completed': False,
                'fabrication_release': False, 'native_drc_qualified': False,
                'replay_qualified': False, 'manufacturing_exports': False}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen_archive(archive: Path) -> dict[str, bytes]:
    if digest(archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Wrong diagnostic archive checksum')
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        expected = {'eeg128-tdm' + ext for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru')}
        if len(names) != 3 or set(names) != expected:
            raise ValueError('Unexpected baseline archive members')
        data = {name: bundle.read(name) for name in sorted(expected)}
    if digest(data[PCB]) != PCB_SHA:
        raise ValueError('Wrong diagnostic PCB checksum')
    return data


def guide_geometry(data: dict[str, Any], neighbor: str) -> dict[int, Any]:
    from shapely.geometry import LineString
    routes = data['routes'][neighbor]
    result: dict[int, list[Any]] = defaultdict(list)
    for a, b in zip(routes, routes[1:]):
        if a[0] == b[0] and math.dist(a[1:], b[1:]) > 1e-6:
            result[a[0]].append(LineString([a[1:], b[1:]]))
    return result


def tracks_selected(board: Any, guide: dict[int, Any], neighbor: str,
                    limit: int, pad_guard: float = 1.0) -> list[Any]:
    """Select intersecting objects only; never cut a via or pad-adjacent escape."""
    import pcbnew
    from shapely.geometry import Point, LineString
    from shapely.ops import unary_union
    from route_targeted_closure import xy
    wanted = {'CH022_N_ELECTRODE': 0, neighbor: 2}
    pads = defaultdict(list)
    vias = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in wanted:
                pads[pad.GetNetname()].append(Point(xy(pad.GetPosition())))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in wanted:
            vias[t.GetNetname()].append(Point(xy(t.GetPosition())))
    lanes = {layer: unary_union(lines).buffer(.31) for layer, lines in guide.items() if lines}
    selected = []
    for t in board.GetTracks():
        if isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
            continue
        name = t.GetNetname()
        if name not in wanted or t.GetLayer() != (pcbnew.F_Cu if wanted[name] == 0 else pcbnew.In2_Cu):
            continue
        lane = lanes.get(wanted[name])
        if lane is None:
            continue
        line = LineString([xy(t.GetStart()), xy(t.GetEnd())])
        # A retained segment touching a pad or via is not sacrificed to a
        # global reroute. Especially preserve the J2.23 and U3/U4 escapes.
        if any(line.distance(p) < pad_guard for p in pads[name]):
            continue
        if any(line.distance(v) < .65 for v in vias[name]):
            continue
        score = line.intersection(lane).length
        if score > 0.00001:
            selected.append((score, t.m_Uuid.AsString(), t))
    selected.sort(key=lambda row: (-row[0], row[1]))
    # Limit applies independently to each displaced net.
    kept: dict[str, int] = defaultdict(int)
    result = []
    for _, _, track in selected:
        net_name = track.GetNetname()
        if kept[net_name] >= limit:
            continue
        result.append(track)
        kept[net_name] += 1
    return result


def track_record(track: Any) -> dict[str, Any]:
    import pcbnew
    from route_targeted_closure import xy
    return {'net': track.GetNetname(), 'uuid': track.m_Uuid.AsString(),
            'start': xy(track.GetStart()), 'end': xy(track.GetEnd()),
            'layer_id': int(track.GetLayer()),
            'width_mm': pcbnew.ToMM(track.GetWidth())}


def restored_each(selected: list[Any], names: tuple[str, str]) -> bool:
    counts = {n: 0 for n in names}
    for t in selected:
        if t.GetNetname() in counts:
            counts[t.GetNetname()] += 1
    return all(counts.values())


def run_trial(board_file: Path, guide_data: dict[str, Any], neighbor: str,
              limit: int, output: Path, order: str) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import box
    from analyze_139_escape_blockers import protected_power
    from route_targeted_closure import xy, native_fresh
    from escape_mesh_505 import mesh_route, add_mesh_path
    from probe_block2_joint136 import pad_pair
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import power_copper, outlines

    trial: dict[str, Any] = {'neighbor': neighbor, 'max_cuts_per_net': limit, 'order': order,
                             'selected': [], 'status': 'not_tested', **OUTPUT_FLAGS}
    board = pcbnew.LoadBoard(str(board_file))
    original_board = pcbnew.LoadBoard(str(board_file))
    power = protected_power(board)
    selected = tracks_selected(board, guide_geometry(guide_data, neighbor), neighbor, limit)
    trial['selected'] = [track_record(t) for t in selected]
    if not restored_each(selected, ('CH022_N_ELECTRODE', neighbor)):
        trial['status'] = 'no_selective_interference_pair'
        return trial
    # Keep Python ownership of all removed SWIG objects until trial completion.
    for t in selected:
        board.Remove(t)
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    region = box(12, .5, 59, 69)
    try:
        pads = pad_pair(board, 'CH024_P_MUX', xy)
        if [name for name, _, _ in pads] != ['R49.1', 'U3.23', 'R305.2']:
            raise ValueError('CH024 three terminal identities differ from frozen review')
        from shapely.geometry import Point
        from shapely.ops import unary_union
        route_lanes = guide_geometry(guide_data, neighbor)

        def connect_target() -> bool:
            for name, dest, _ in pads[1:]:
                path = mesh_route(board, pads[0][1], dest, pads[0][2], layers, power, region)
                if path is None:
                    trial['status'] = 'target_unreachable'
                    trial['failed_pad'] = name
                    return False
                add_mesh_path(board, path, pads[0][2], layers)
            trial['target_three_pads_proposed'] = True
            return True

        def reconnect_segments() -> bool:
            for t in selected:
                net = t.GetNetCode()
                layer = 0 if t.GetLayer() == pcbnew.F_Cu else 2
                start_point, end_point = xy(t.GetStart()), xy(t.GetEnd())
                restrictions = None
                if order == 'neighbors-first-reserved':
                    restrictions = []
                    for lane_index in range(len(layers)):
                        guides = route_lanes.get(lane_index)
                        if not guides:
                            restrictions.append(Point(0, 0).buffer(0))
                            continue
                        restricted = unary_union(guides).buffer(.34)
                        # The segment endpoints must remain reachable. This
                        # local exemption never modifies the baseline copper.
                        restricted = restricted.difference(Point(start_point).buffer(.55))
                        restricted = restricted.difference(Point(end_point).buffer(.55))
                        restrictions.append(restricted)
                path = mesh_route(board, start_point, end_point, net,
                                  layers, power, region, start_layer=layer,
                                  goal_layer=layer, extra_obstacles=restrictions)
                if path is None:
                    trial['status'] = 'neighbor_segment_unrestored'
                    trial['failed_uuid'] = t.m_Uuid.AsString()
                    return False
                add_mesh_path(board, path, net, layers)
            trial['neighbors_geometrically_proposed'] = True
            return True

        tasks = (connect_target, reconnect_segments) if order == 'target-first' else (
            reconnect_segments, connect_target)
        for task in tasks:
            if not task():
                return trial
        trial['all_selective_segments_geometrically_proposed'] = True
        # Temporary trial only; never copy or commit to engineering source.
        pcbnew.SaveBoard(str(board_file), board)
        report = native_fresh(board_file, output.with_suffix('.drc.json'))
        trial['drc_version'] = report.get('kicad_version')
        trial['drc_errors'] = len(report.get('violations', []))
        trial['unconnected'] = len(report.get('unconnected_items', []))
        trial['drc_warnings'] = sum(
            x.get('severity') == 'warning'
            for x in report.get('violations', []) + report.get('unconnected_items', []))
        before = native_fresh(output.parent / 'reference' / PCB, output.with_suffix('.before.json'))
        trial['regressed_nets'] = regressed_nets(before, report)
        after_board = pcbnew.LoadBoard(str(board_file))
        old_power, new_power = power_copper(original_board), power_copper(after_board)
        trial['L3_loss_mm2'] = old_power.difference(new_power).area
        trial['L3_gain_mm2'] = new_power.difference(old_power).area
        trial['zone_outlines_unchanged'] = outlines(original_board) == outlines(after_board)
        # Never promote based on an in-memory or first-pass native candidate.
        trial['status'] = 'native_trial_audit_only'
        return trial
    finally:
        # Removed SWIG tracks remain owned until the trial is complete.
        for track in selected:
            board.Add(track)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--neighbor', choices=('CH018_N_MUX', 'CH019_P_MUX'),
                   action='append')
    p.add_argument('--budget', type=int, choices=(2, 4, 8), action='append')
    p.add_argument('--order', choices=('target-first', 'neighbors-first-reserved'),
                   default='target-first')
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Use a new diagnostic JSON file')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('No generated artifacts in repository')
    content = frozen_archive(args.archive)
    guides = json.loads(GUIDES.read_text())
    if guides['input_pcb_sha256'] != PCB_SHA or guides['baseline_archive_sha256'] != ZIP_SHA:
        raise ValueError('Wrong reviewed guide provenance')
    summary: dict[str, Any] = {**OUTPUT_FLAGS, 'baseline_archive_sha256': ZIP_SHA,
                               'trials': []}
    with tempfile.TemporaryDirectory(prefix='block2-selective-') as temp:
        directory = Path(temp)
        for neighbor in (args.neighbor or ['CH018_N_MUX', 'CH019_P_MUX']):
            for budget in (args.budget or [2, 4, 8]):
                work = directory / (neighbor + '-' + str(budget))
                work.mkdir()
                for name, buf in content.items():
                    (work / name).write_bytes(buf)
                reference = work / 'reference'
                reference.mkdir()
                for name, buf in content.items():
                    (reference / name).write_bytes(buf)
                try:
                    trial = run_trial(work / PCB, guides, neighbor, budget,
                                      work / 'selective-result.json', args.order)
                except (ValueError, RuntimeError) as exc:
                    trial = {'neighbor': neighbor, 'max_cuts_per_net': budget,
                             'status': 'model_failed', 'reason': str(exc), 'order': args.order,
                             **OUTPUT_FLAGS}
                summary['trials'].append(trial)
                args.output.write_text(json.dumps(summary, indent=2) + '\n')
                print(neighbor, budget, trial['status'], flush=True)
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Archive mutated during search')


if __name__ == '__main__':
    main()

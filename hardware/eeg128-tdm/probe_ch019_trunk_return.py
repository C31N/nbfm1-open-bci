#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only CH019_P_MUX return-path models around a pinned In2.Cu bottleneck.

Try endpoint bridging vs. pad-driven F.Cu/B.Cu alternate access, testing
small subsets of obstructing copper. Run only in a temporary directory;
never set accepted=true and never write a board to the repository.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import tempfile
from typing import Any

SOURCE = Path(__file__).resolve().parent
PCB = 'eeg128-tdm.kicad_pcb'
TRUNK = (
    '752f59d7-57f9-46ee-b7cc-b45beae0a553',
    '8023115a-ecd5-48bc-ae2f-f4659fbd6c27',
    'ecd35e32-892c-474a-a7b1-86b7edb96787',
)
ELECTRODE = (
    'a0a692e9-e4d4-4be1-b224-b0aa00b02815',
    'e81c7523-9205-40fe-bcd4-374c112022ef',
)
FLAGS = {'model_only': True, 'accepted': False, 'routing_completed': False,
         'fabrication_release': False, 'independent_replay_verified': False,
         'native_qualification': False, 'manufacturing_files': False}
COMBINATIONS = {
    'isolated': (TRUNK[0],),
    'adjacent': (TRUNK[0], TRUNK[1]),
    'entire_trunk': TRUNK,
}


def protected_selection(board: Any, case: str) -> list[Any]:
    """Exact UUID + net + layer scope; never remove CH018-N or other copper."""
    import pcbnew
    wanted = set(ELECTRODE + COMBINATIONS[case])
    found = {t.m_Uuid.AsString(): t for t in board.GetTracks()
             if t.m_Uuid.AsString() in wanted}
    if set(found) != wanted:
        raise ValueError('Pinned selective copper UUID set is incomplete')
    for uid, track in found.items():
        if uid in ELECTRODE:
            expected_net, layer = 'CH022_N_ELECTRODE', pcbnew.F_Cu
        else:
            expected_net, layer = 'CH019_P_MUX', pcbnew.In2_Cu
        if track.GetNetname() != expected_net or track.GetLayer() != layer:
            raise ValueError('Unexpected protected segment identity/layer')
        if isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
            raise ValueError('Selective removal of arc or via is prohibited')
    return [found[uid] for uid in (*ELECTRODE, *COMBINATIONS[case])]


def pads(board: Any, net: str) -> list[tuple[str, tuple[float, float], int]]:
    from route_targeted_closure import xy
    points = [(f.GetReference() + '.' + p.GetNumber(), xy(p.GetPosition()),
               p.GetNetCode(), p.IsOnLayer(__import__('pcbnew').F_Cu))
              for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    if len(points) < 2 or not all(p[3] for p in points) or len({p[2] for p in points}) != 1:
        raise ValueError(net + ': inconsistent or non-frontside pad endpoints')
    return [(name, coord, code) for name, coord, code, _ in sorted(points)]


def via_windows(board: Any, point: tuple[float, float],
                net_code: int, power: Any) -> dict[str, Any]:
    """Measure legal via center regions; exploratory Shapely, NOT native DRC."""
    import pcbnew
    from shapely.geometry import Point
    from route_targeted_closure import obstacles, routing_domain
    domain = routing_domain(board, .30, .25)
    region = Point(point).buffer(3.5).intersection(domain)
    shape, via = obstacles(board, net_code, .15, .15, region, .60,
                           (pcbnew.F_Cu, pcbnew.B_Cu))
    del shape
    legal = region.difference(via.union(power.buffer(.505)))
    anchor = Point(point)
    proposals = []
    for radius in (.5, 1.0, 2.0, 3.5):
        local = legal.intersection(anchor.buffer(radius))
        if local.area > 1e-7:
            pt = local.representative_point()
            proposals.append({'radius_mm': radius, 'area_mm2': round(local.area, 8),
                              'sample_xy': [round(pt.x, 6), round(pt.y, 6)]})
    return {
        'anchor': [float(v) for v in point],
        'anchor_inside_power_guard': bool(power.buffer(.505).covers(anchor)),
        'nearest_legal_via_distance_mm': (round(anchor.distance(legal), 6)
                                          if not legal.is_empty else None),
        'samples': proposals,
    }


def explore(case: str, strategy: str, input_board: Path,
            report_file: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from analyze_139_escape_blockers import protected_power
    from route_targeted_closure import routing_domain, xy, native_fresh
    from escape_mesh_505 import add_mesh_path, mesh_route
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import outlines, power_copper

    board = pcbnew.LoadBoard(str(input_board))
    unchanged = pcbnew.LoadBoard(str(input_board))
    chosen = protected_selection(board, case)
    result: dict[str, Any] = {**FLAGS, 'case': case, 'strategy': strategy,
                              'status': 'not_started',
                              'selected_uuids': [t.m_Uuid.AsString() for t in chosen]}
    region = routing_domain(board, .30, .25)
    power = protected_power(board)
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    old_pad_set = pads(board, 'CH019_P_MUX')
    result['ch019_pad_names'] = [p[0] for p in old_pad_set]
    anchors = [(xy(t.GetStart()), xy(t.GetEnd()), t.GetNetCode())
               for t in chosen if t.GetNetname() == 'CH019_P_MUX']
    result['endpoint_windows_before'] = [via_windows(board, x, code, power)
                                         for start, end, code in anchors
                                         for x in (start, end)]
    # Keep SWIG track handles alive until mutation is rolled back.
    for t in chosen:
        board.Remove(t)
    try:
        result['endpoint_windows_after_removal'] = [via_windows(board, x, code, power)
                                                    for start, end, code in anchors
                                                    for x in (start, end)]
        def route_between(net: str, points: list[tuple[str, tuple[float, float], int]],
                          start_layer: int = 0, goal_layer: int = 0) -> bool:
            for label, point, code in points[1:]:
                proposal = mesh_route(board, points[0][1], point, code,
                                      layers, power, region,
                                      start_layer=start_layer, goal_layer=goal_layer)
                if proposal is None:
                    result['blocked_at'] = net + ':' + label
                    return False
                add_mesh_path(board, proposal, code, layers)
            return True

        target = pads(board, 'CH024_P_MUX')
        if {name for name, _, _ in target} != {'R49.1', 'U3.23', 'R305.2'}:
            raise ValueError('Required three-pad CH024 target set has changed')
        source = next(p for p in target if p[0] == 'R49.1')
        target = [source] + [p for p in target if p is not source]
        if not route_between('CH024_P_MUX', target):
            result['status'] = 'ch024_target_blocked'
            return result
        result['ch024_all_three_geometrically_proposed'] = True
        # The old endpoint-pair strategy is included as a control. The new
        # strategy connects existing F.Cu pad components instead of forcing
        # through-vias exactly onto former In2.Cu segment endpoints.
        if strategy == 'old_endpoints':
            for start, end, code in anchors:
                path = mesh_route(board, start, end, code, layers, power,
                                  region, start_layer=2, goal_layer=2)
                if path is None:
                    result['status'] = 'endpoint_pair_blocked'
                    result['blocked_endpoints'] = [start, end]
                    return result
                add_mesh_path(board, path, code, layers)
        else:
            ch019 = pads(board, 'CH019_P_MUX')
            if not route_between('CH019_P_MUX', ch019):
                result['status'] = 'ch019_pad_to_pad_blocked'
                return result
        result['ch019_geometrically_proposed'] = True
        ch022 = pads(board, 'CH022_N_ELECTRODE')
        if not route_between('CH022_N_ELECTRODE', ch022):
            result['status'] = 'ch022_electrode_blocked'
            return result
        result['ch022_geometrically_proposed'] = True
        # Never accept model success without full native parity, zero-regression
        # connectivity, exact zero power difference and independent replay.
        pcbnew.SaveBoard(str(input_board), board)
        drc_after = native_fresh(input_board, report_file.with_suffix('.after.json'))
        drc_before = native_fresh(report_file.parent / 'baseline' / PCB,
                                  report_file.with_suffix('.before.json'))
        result['drc_version'] = drc_after.get('kicad_version')
        result['violations'] = len(drc_after.get('violations', []))
        result['unconnected'] = len(drc_after.get('unconnected_items', []))
        result['warnings'] = sum(x.get('severity') == 'warning'
                                 for x in drc_after.get('violations', [])
                                 + drc_after.get('unconnected_items', []))
        result['regressed_nets'] = regressed_nets(drc_before, drc_after)
        result['all_required_nets_closed_natively'] = all(
            net not in json.dumps(drc_after.get('unconnected_items', []))
            for net in ('CH024_P_MUX', 'CH019_P_MUX', 'CH022_N_ELECTRODE'))
        observed = pcbnew.LoadBoard(str(input_board))
        before_power, after_power = power_copper(unchanged), power_copper(observed)
        result['L3_loss_mm2'] = before_power.difference(after_power).area
        result['L3_gain_mm2'] = after_power.difference(before_power).area
        result['zone_outlines_unchanged'] = outlines(unchanged) == outlines(observed)
        result['status'] = 'native_audit_unaccepted'
        return result
    finally:
        for track in chosen:
            board.Add(track)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=tuple(COMBINATIONS), default='entire_trunk')
    parser.add_argument('--strategy', choices=('old_endpoints', 'pads'), default='pads')
    args = parser.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Create a fresh JSON diagnostic output')
    if args.output.resolve().is_relative_to(SOURCE):
        raise ValueError('Writing a report within repository is prohibited')
    from probe_block2_selective import frozen_archive, digest, ZIP_SHA
    data = frozen_archive(args.archive)
    result: dict[str, Any] = {**FLAGS, 'case': args.case,
                              'strategy': args.strategy, 'status': 'unstarted'}
    with tempfile.TemporaryDirectory(prefix='ch019-return-') as temp:
        work = Path(temp)
        for name, contents in data.items():
            (work / name).write_bytes(contents)
        baseline = work / 'baseline'
        baseline.mkdir()
        for name, contents in data.items():
            (baseline / name).write_bytes(contents)
        try:
            result = explore(args.case, args.strategy, work / PCB, work / 'ch019.json')
        except (RuntimeError, ValueError) as exc:
            result = {**FLAGS, 'case': args.case, 'strategy': args.strategy,
                      'status': 'model_exception', 'reason': str(exc)}
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Frozen archive changed during diagnostic')
    print(args.case, args.strategy, result['status'], flush=True)


if __name__ == '__main__':
    main()

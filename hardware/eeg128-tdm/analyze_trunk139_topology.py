#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only B.Cu/In2.Cu component diagnostics on pinned 139-neighbor fixtures.

This is a conservative, bounded centreline model, not a native routing proof.
Trial removals are hypothetical and never save a PCB or promote a checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pcbnew
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from analyze_139_escape_blockers import protected_power
from escape_mesh import polygons
from route_targeted_closure import obstacles

Report = dict[str, Any]
LAYERS = (pcbnew.B_Cu, pcbnew.In2_Cu)
REGION = box(.5, .5, 95, 130)
CASES = {
    'p': {
        'sha256': 'ce2f8888ddc307fb59b3d6088a4bf14b8fdc7955b6fa8e6b8c5f7c507102c522',
        'net': 'CH018_P_MUX',
        'anchors': [(46.841954, 34.399999), (32.2625, 35.646231),
                    (32.930481, 29.903291), (31.5525, 27.275981),
                    (33.003947, 22.037563), (33.637364, 19.491039), (28.4875, 34.7)],
    },
    'n': {
        'sha256': '72fd1886f0ee24b9032dc6e286abea34fd164d283c114c61fd161ccc5e6a22d0',
        'net': 'CH021_N_ELECTRODE',
        'anchors': [(52.707002, 7.486252), (33.637364, 19.491039), (35.6, 17.275)],
    },
}
NEIGHBORS = ('CH017_N_ELECTRODE', 'CH017_N_MUX', 'CH018_N_MUX',
             'CH019_P_MUX', 'CH020_N_ELECTRODE', 'CH023_N_ELECTRODE',
             'CH025_P_ELECTRODE')


def topology(board: pcbnew.BOARD, net: int, power: BaseGeometry,
             anchors: list[tuple[float, float]]) -> Report:
    """Connect free polygons only through positive-area legal through-via patches."""
    blocked, via = obstacles(board, net, .15, .15, REGION, .60, LAYERS)
    blocked[1] = unary_union([blocked[1], power.buffer(.280)])
    free = [polygons(REGION.difference(s).buffer(-.000005)) for s in blocked]
    viafree = REGION.difference(unary_union([via, power.buffer(.505)])).buffer(-.000005)
    trees = [STRtree(parts) for parts in free]
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {
        (layer, index): set() for layer in range(2) for index in range(len(free[layer]))}
    bridges = []
    for patch in polygons(viafree):
        if patch.area < 1e-10:
            continue
        point = patch.representative_point()
        ids = [next((int(i) for i in trees[layer].query(point)
                     if free[layer][int(i)].covers(point)), None) for layer in range(2)]
        if any(index is None for index in ids):
            continue
        a, b = (0, ids[0]), (1, ids[1])
        adjacency[a].add(b)
        adjacency[b].add(a)
        bridges.append({'components': [list(a), list(b)], 'area_mm2': patch.area,
                        'point': list(point.coords[0])})
    memberships = [[(layer, int(i)) for layer in range(2)
                    for i in trees[layer].query(Point(point))
                    if free[layer][int(i)].covers(Point(point))] for point in anchors]
    if not viafree.covers(Point(anchors[0])):
        raise ValueError('Target via anchor is outside the conservative legal window')
    # The target is a proposed through-via: either layer is a valid starting side.
    queue = list(memberships[0])
    reached: set[tuple[int, int]] = set()
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(adjacency[current] - reached)
    return {
        'component_counts': [len(parts) for parts in free],
        'legal_via_patches': bridges,
        'target_reachable_components': [
            {'layer': board.GetLayerName(LAYERS[layer]), 'id': index,
             'area_mm2': free[layer][index].area, 'bounds': list(free[layer][index].bounds)}
            for layer, index in sorted(reached)],
        'anchors': [{'point': list(point), 'components': [list(n) for n in members],
                     'new_via_legal_in_fixture': viafree.covers(Point(point)),
                     'b_reachable': any(layer == 0 and (layer, index) in reached
                                        for layer, index in members),
                     'either_layer_reachable': bool(set(members) & reached)}
                    for point, members in zip(anchors, memberships)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=sorted(CASES), required=True)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    case = CASES[args.case]
    content = args.board.read_bytes()
    if hashlib.sha256(content).hexdigest() != case['sha256']:
        raise ValueError('Wrong qualified 139-neighbor fixture')
    board = pcbnew.LoadBoard(str(args.board))
    net = board.FindNet(case['net']).GetNetCode()
    if any(isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == net for t in board.GetTracks()):
        raise ValueError('Existing same-net via reuse needs a separate model')
    power = protected_power(board)
    result = {
        'model_only': True, 'accepted': False, 'routing_completed': False,
        'fabrication_release': False, 'fixture_pcb_sha256': case['sha256'],
        'net': case['net'], 'region_mm': list(REGION.bounds),
        'width_mm': .15, 'signal_clearance_mm': .15,
        'via_diameter_mm': .60, 'via_drill_mm': .30,
        'power_trace_exclusion_mm': .280, 'power_via_exclusion_mm': .505,
        'inward_rounding_guard_mm': .000005,
        'baseline': topology(board, net, power, case['anchors']), 'trials': [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for neighbor in NEIGHBORS:
        for layer in LAYERS:
            removed = [t for t in board.GetTracks() if t.GetNetname() == neighbor
                       and not isinstance(t, pcbnew.PCB_VIA) and t.GetLayer() == layer]
            if not removed:
                continue
            for track in removed:
                board.Remove(track)
            try:
                trial = topology(board, net, power, case['anchors'])
            finally:
                for track in removed:
                    board.Add(track)
            result['trials'].append({
                'removed_net': neighbor, 'removed_layer': board.GetLayerName(layer),
                'removed_uuids': sorted(t.m_Uuid.AsString() for t in removed),
                'neighbor_restored': False, 'accepted': False, **trial})
            print(neighbor, board.GetLayerName(layer),
                  [a['b_reachable'] for a in trial['anchors']], flush=True)
            args.output.write_text(json.dumps(result, indent=2) + '\n')
    if args.board.read_bytes() != content:
        raise ValueError('Read-only source fixture changed')


if __name__ == '__main__':
    main()

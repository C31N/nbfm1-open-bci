#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only escape inventory and explicitly hypothetical removals on diagnostic 137."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pcbnew
from shapely.geometry import LineString, Point, box

from analyze_139_escape_blockers import protected_power, windows
from route_targeted_closure import xy

PCB_SHA256 = '8d25968ffff8564334a4ba21c45c25b58dece7b27e2ca77be6118eb28817b187'
NETS = ('CH020_N_MUX', 'CH020_P_MUX', 'CH024_N_MUX', 'CH024_P_MUX',
        'CH028_N_MUX', 'CH029_N_MUX', 'CH030_N_MUX')
REGION = box(12, .5, 59, 69)


def analyze(board: pcbnew.BOARD, name: str) -> dict[str, Any]:
    pads = [(f.GetReference(), p) for f in board.GetFootprints() for p in f.Pads()
            if p.GetNetname() == name]
    source = [(ref, p) for ref, p in pads if ref.startswith('R') and p.GetNumber() == '1']
    target = [(ref, p) for ref, p in pads if ref.startswith('U')]
    if len(source) != 1 or len(target) != 1:
        raise ValueError('Ambiguous RC/MUX terminal')
    power = protected_power(board)
    result = {}
    for label, (ref, pad) in [('source', source[0]), ('target', target[0])]:
        point = xy(pad.GetPosition())
        component, window = windows(board, pad.GetNetCode(), point, REGION, power)
        neighbors: dict[str, list[dict[str, Any]]] = {}
        for track in board.GetTracks():
            if track.GetNetCode() == pad.GetNetCode():
                continue
            via = isinstance(track, pcbnew.PCB_VIA)
            if not via and track.GetLayer() != pcbnew.F_Cu:
                continue
            shape = (Point(xy(track.GetPosition())) if via else
                     LineString([xy(track.GetStart()), xy(track.GetEnd())]))
            distance = shape.distance(component) - pcbnew.ToMM(track.GetWidth()) / 2
            if distance >= .4:
                continue
            neighbors.setdefault(track.GetNetname(), []).append({
                'uuid': track.m_Uuid.AsString(), 'via': via,
                'layer': board.GetLayerName(track.GetLayer()),
                'start': xy(track.GetStart()), 'end': xy(track.GetEnd()),
                'distance_to_component_mm': distance})
        result[label] = {'pad': ref + '.' + pad.GetNumber(), 'point': point,
                         'window': window, 'boundary_copper': neighbors}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--net', choices=NETS, action='append')
    parser.add_argument('--remove-net', action='append', default=[])
    args = parser.parse_args()
    original = args.board.read_bytes()
    if hashlib.sha256(original).hexdigest() != PCB_SHA256:
        raise ValueError('Wrong pinned diagnostic 137 PCB')
    board = pcbnew.LoadBoard(str(args.board))
    # Keep removed SWIG objects alive; never re-add objects across model trials.
    removed = [t for t in board.GetTracks() if t.GetNetname() in args.remove_net]
    if set(args.remove_net) & set(args.net or NETS):
        raise ValueError('Cannot remove the net being analyzed')
    if any(not any(t.GetNetname() == n for t in removed) for n in args.remove_net):
        raise ValueError('Unknown or empty hypothetical neighbor')
    for track in removed:
        board.Remove(track)
    result = {'model_only': True, 'accepted': False, 'routing_completed': False,
              'fabrication_release': False, 'baseline_pcb_sha256': PCB_SHA256,
              'region_mm': list(REGION.bounds), 'edge_clearance_mm': .25,
              'new_via_power_exclusion_mm': .505, 'new_In2_power_exclusion_mm': .505,
              'removed_nets': args.remove_net,
              'removed_uuids': sorted(t.m_Uuid.AsString() for t in removed),
              'neighbors_restored': not bool(removed),
              'results': {name: analyze(board, name) for name in args.net or NETS}}
    if args.board.read_bytes() != original:
        raise ValueError('Read-only source changed')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()

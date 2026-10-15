#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Find complete L1/L4 escapes without writing partial vias or changing rules."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import pcbnew
from shapely.geometry import Point
from shapely.ops import unary_union
from audit_block1_corridor_geometry import power_copper
from route_targeted_closure import search, xy


def pad_anchors(board: pcbnew.BOARD, name: str) -> tuple[tuple[float, float], tuple[float, float]]:
    pads = [(f.GetReference(), p) for f in board.GetFootprints()
            for p in f.Pads() if p.GetNetname() == name]
    sources = [p for ref, p in pads if ref.startswith('R')]
    targets = [p for ref, p in pads if ref.startswith('U' if name.endswith('_MUX') else 'J')]
    if not sources or len(targets) != 1:
        raise ValueError(f'Unresolved pad anchors for {name}')
    goal = xy(targets[0].GetPosition())
    source = min(sources, key=lambda p: math.dist(xy(p.GetPosition()), goal))
    return xy(source.GetPosition()), goal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--net', action='append', required=True)
    parser.add_argument('--mode', choices=('escapes', 'direct', 'trunks'), default='escapes')
    parser.add_argument('--escapes', type=Path)
    parser.add_argument('--count', type=int, default=4)
    parser.add_argument('--step', type=float, default=.025)
    parser.add_argument('--margin', type=float, default=6)
    parser.add_argument('--seconds', type=float, default=12)
    parser.add_argument('--secondary-layer', choices=('B.Cu', 'In2.Cu'), default='B.Cu')
    args = parser.parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    plane = power_copper(board)
    data: dict[str, Any] = {'baseline_sha256': hashlib.sha256(args.board.read_bytes()).hexdigest(),
                            'mode': args.mode, 'step_mm': args.step, 'margin_mm': args.margin,
                            'search_seconds': args.seconds, 'via_diameter_mm': .60,
                            'new_copper_layers': ['F.Cu', args.secondary_layer], 'nets': {},
                            'copper_written': False, 'routing_completed': False,
                            'fabrication_release': False}
    source_escapes = json.loads(args.escapes.read_text()) if args.escapes else None
    for name in args.net:
        start, goal = pad_anchors(board, name)
        net = next(p.GetNetCode() for f in board.GetFootprints() for p in f.Pads()
                   if p.GetNetname() == name)
        record: dict[str, Any] = {'start_mm': start, 'goal_mm': goal, 'results': {}}
        if args.mode == 'escapes':
            for label, point in (('source', start), ('target', goal)):
                found = []
                for _ in range(args.count):
                    # The planner uses only F.Cu for the neck. Reserve L3 power
                    # for through-via antipads, without restricting L4 trunks.
                    forbidden = unary_union([plane.buffer(.05)] +
                                            [Point(path[-1][1:]) for path in found])
                    path = search(board, point, point, net, .15, .15, False, args.margin,
                                  step=args.step, max_nodes=350000,
                                  deadline=time.monotonic()+args.seconds,
                                  layers=(pcbnew.F_Cu, pcbnew.B_Cu), via_diameter=.60,
                                  reserved_bottom=forbidden, escape_via_only=True)
                    if path is None:
                        break
                    found.append(path)
                record['results'][label] = found
        elif args.mode == 'direct':
            for reverse in (False, True):
                a, b = (goal, start) if reverse else (start, goal)
                path = search(board, a, b, net, .15, .15, True, args.margin,
                              step=args.step, max_nodes=600000,
                              deadline=time.monotonic()+args.seconds,
                              layers=(pcbnew.F_Cu, pcbnew.B_Cu if args.secondary_layer == 'B.Cu' else pcbnew.In2_Cu),
                              via_diameter=.60, via_keepout=plane.buffer(.505),
                              reserved_bottom=plane.buffer(.05) if args.secondary_layer == 'In2.Cu' else None)
                record['results']['reverse' if reverse else 'forward'] = path
        else:
            if source_escapes is None:
                raise ValueError('--escapes is required for trunk planning')
            routes = source_escapes['nets'][name]['results']
            attempts = []
            for head in routes['source']:
                for tail in routes['target']:
                    a, b = tuple(head[-1][1:]), tuple(tail[-1][1:])
                    path = search(board, a, b, net, .15, .15, True, args.margin,
                                  step=args.step, max_nodes=600000,
                                  deadline=time.monotonic()+args.seconds,
                                  layers=(pcbnew.B_Cu, pcbnew.F_Cu), via_diameter=.60,
                                  via_keepout=unary_union([plane.buffer(.505),
                                                         Point(a).buffer(.56), Point(b).buffer(.56)]))
                    attempts.append({'source_via_mm': a, 'target_via_mm': b,
                                     'found': path is not None, 'path': path,
                                     'head': head if path else None,
                                     'tail': tail if path else None})
                    if path:
                        break
                if attempts and attempts[-1]['found']:
                    break
            record['results']['trunks'] = attempts
        data['nets'][name] = record
        args.output.write_text(json.dumps(data, indent=2)+'\n')
        summary = ({key: len(value) for key, value in record['results'].items()}
                   if args.mode == 'escapes' else
                   {'trunk_attempts': len(record['results']['trunks']),
                    'found': any(x['found'] for x in record['results']['trunks'])}
                   if args.mode == 'trunks' else
                   {key: value is not None for key, value in record['results'].items()})
        print(json.dumps({'net': name, 'mode': args.mode, 'summary': summary}), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only KiCad-native geometry survey of CH019-P retained-via corridor.

This script identifies exact B.Cu/F.Cu blocking tracks and safe-to-study
interior segments by UUID. It never writes a PCB, authorizes a reroute,
generates manufacturing files, or promotes a diagnostic checkpoint.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import tempfile

PCB = 'eeg128-tdm.kicad_pcb'
A = (39.915, 45.15)
B = (32.7, 23.4)
FLAGS = {
    'model_only': True, 'accepted': False,
    'routing_completed': False, 'fabrication_release': False,
    'drc_qualified': False, 'replay_qualified': False,
    'manufacturing_files': False,
}
FROZEN_INPUT_SHA = 'cac02064d9926676f6368536c4c104cb36295961333de6074e65fa1fa60a814c'
SCRIPT_DIR = Path(__file__).resolve().parent


def analyze(board):
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from route_targeted_closure import xy, routing_domain, obstacles

    endpoint = LineString([A, B])
    center = endpoint.buffer(2.0, cap_style=2).union(
        Point(A).buffer(3.0)).union(Point(B).buffer(3.0))
    region = routing_domain(board, .30, .25).intersection(
        box(27.5, 18.5, 48.5, 49.5))
    net = next(p.GetNetCode() for fp in board.GetFootprints()
               for p in fp.Pads() if p.GetNetname() == 'CH019_P_MUX')
    if net <= 0:
        raise ValueError('CH019-P missing from native pad netlist')

    all_pads = defaultdict(list)
    vias = defaultdict(list)
    pad_obstacles = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pad_point = Point(xy(pad.GetPosition()))
            all_pads[pad.GetNetname()].append(pad_point)
            if pad.GetNetCode() != net and pad_point.distance(center) <= 1.6:
                pad_obstacles.append({
                    'ref': footprint.GetReference() + '.' + pad.GetNumber(),
                    'net': pad.GetNetname(), 'position': list(pad_point.coords[0]),
                    'distance_to_direct_mm': round(endpoint.distance(pad_point), 6),
                    'has_BCu': bool(pad.IsOnLayer(pcbnew.B_Cu)),
                })
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            vias[track.GetNetname()].append(Point(xy(track.GetPosition())))

    def free_metrics():
        block, _ = obstacles(board, net, .15, .15, region, .60,
                             (pcbnew.F_Cu, pcbnew.B_Cu))
        summary = {}
        for idx, name in enumerate(('F.Cu', 'B.Cu')):
            free = region.difference(block[idx]).buffer(-.000005)
            endpoints = [free.covers(Point(p)) for p in (A, B)]
            parts = [g for g in getattr(free, 'geoms', [free])
                     if g.geom_type == 'Polygon' and g.area > 1e-7]
            components = [
                next((i for i, part in enumerate(parts)
                      if part.covers(Point(p))), None) for p in (A, B)
            ]
            comp_distance = (parts[components[0]].distance(parts[components[1]])
                             if all(x is not None for x in components) else None)
            summary[name] = {
                'a_legal': endpoints[0], 'b_legal': endpoints[1],
                'same_free_component': components[0] is not None
                    and components[0] == components[1],
                'component_distance_mm': comp_distance,
                'direct_segment_legal': free.covers(endpoint),
                'free_area_mm2': round(free.area, 7),
                'component_areas_mm2': [
                    round(parts[i].area, 7) if i is not None else None
                    for i in components],
            }
        return summary

    initial = free_metrics()
    candidate = []
    hard = []
    for track in board.GetTracks():
        if track.GetNetCode() == net:
            continue
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition()))
            kind = 'via'
        elif isinstance(track, pcbnew.PCB_ARC):
            bb = track.GetBoundingBox()
            shape = box(pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                        pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            kind = 'arc'
        else:
            shape = LineString([xy(track.GetStart()), xy(track.GetEnd())])
            kind = 'segment'
        layer_names = (['F.Cu', 'B.Cu'] if kind == 'via'
                       else [board.GetLayerName(track.GetLayer())])
        if not any(layer in ('F.Cu', 'B.Cu') for layer in layer_names):
            continue
        if not shape.intersects(center):
            continue
        name = track.GetNetname()
        pad_dist = min((shape.distance(p) for p in all_pads[name]), default=1000.0)
        via_dist = min((shape.distance(p) for p in vias[name]), default=1000.0)
        can_select = (kind == 'segment'
                      and name not in {'CH018_N_MUX', 'CH022_N_ELECTRODE'}
                      and pad_dist >= 1.00 and via_dist >= .65)
        crossing = shape.intersection(endpoint.buffer(.36)).length
        item = {
            'net': name, 'uuid': track.m_Uuid.AsString(),
            'type': kind, 'layers': layer_names,
            'start': list(xy(track.GetStart())),
            'end': list(xy(track.GetEnd())),
            'width_mm': pcbnew.ToMM(track.GetWidth()),
            'distance_direct_mm': round(shape.distance(endpoint), 6),
            'intersection_length_mm': round(crossing, 6),
            'distance_to_nearest_own_pad_mm': round(pad_dist, 6),
            'distance_to_nearest_own_via_mm': round(via_dist, 6),
            'selectable_without_escapes': can_select,
        }
        (candidate if can_select else hard).append(item)

    candidates = sorted(candidate, key=lambda z: (
        'B.Cu' not in z['layers'], -z['intersection_length_mm'],
        z['distance_direct_mm'], z['net'], z['uuid']))
    hard.sort(key=lambda z: (z['distance_direct_mm'], z['net'], z['uuid']))
    grouped = defaultdict(lambda: {'count': 0, 'interference_length_mm': 0.0,
                                   'uuids': [], 'layers': set()})
    for track in candidates:
        g = grouped[track['net']]
        g['count'] += 1
        g['interference_length_mm'] += track['intersection_length_mm']
        g['uuids'].append(track['uuid'])
        g['layers'].update(track['layers'])

    # Read-only "single copper segment removed" geometric sensitivity.
    # The track object stays alive until it is added back in a finally block.
    trials = []
    for item in candidates[:16]:
        track = next(t for t in board.GetTracks()
                     if t.m_Uuid.AsString() == item['uuid'])
        board.Remove(track)
        try:
            post = free_metrics()
            trials.append({
                'uuid': item['uuid'], 'net': item['net'], 'layers': item['layers'],
                'BCu_component_distance_mm': post['B.Cu']['component_distance_mm'],
                'BCu_same_component': post['B.Cu']['same_free_component'],
                'BCu_delta_free_area_mm2': round(
                    post['B.Cu']['free_area_mm2'] - initial['B.Cu']['free_area_mm2'], 7),
            })
        finally:
            board.Add(track)

    return {
        **FLAGS,
        'source_pcb_sha256': FROZEN_INPUT_SHA,
        'retained_net': 'CH019_P_MUX',
        'endpoints_existing_vias_mm': [list(A), list(B)],
        'keepouts': {'L3_outline_mm': .505, 'edge_A2_mm': .25},
        'baseline_free_space': initial,
        'selectable_segments': candidates[:80],
        'nonselectable_obstacles': hard[:65],
        'pads_near_corridor': pad_obstacles,
        'neighbor_grouping': {
            name: {**v, 'layers': sorted(v['layers']),
                   'interference_length_mm': round(v['interference_length_mm'], 6)}
            for name, v in sorted(grouped.items())},
        'single_segment_sensitivity': trials,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Fresh JSON output required')
    if args.output.resolve().is_relative_to(SCRIPT_DIR):
        raise ValueError('Refusing to write in source tree')
    from probe_block2_selective import frozen_archive, digest, ZIP_SHA
    content = frozen_archive(args.archive)
    if digest(content[PCB]) != FROZEN_INPUT_SHA:
        raise ValueError('Baseline geometry mismatch')
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='ch019-bcu-blockers-') as temp:
        file = Path(temp) / PCB
        file.write_bytes(content[PCB])
        board = pcbnew.LoadBoard(str(file))
        obj = analyze(board)
        if digest(file.read_bytes()) != FROZEN_INPUT_SHA:
            raise ValueError('Baseline PCB changed unexpectedly')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Archive changed during run')
    args.output.write_text(json.dumps(obj, indent=2) + '\n')
    print('readonly-obstacle-diagnostics', len(obj['selectable_segments']),
          len(obj['neighbor_grouping']), flush=True)


if __name__ == '__main__':
    main()

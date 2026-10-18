#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native read-only pad and copper-window survey for Block-2 CH022/CH024.

Never edits primary PCB, exports manufacturing files, or authorizes release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive, digest, ZIP_SHA
from probe_ch019_trunk_return import PCB, ELECTRODE, pads, via_windows
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA

ROOT = Path(__file__).resolve().parent
FLAGS = dict(model_only=True, accepted=False, routing_completed=False,
             fabrication_release=False, independent_replay_verified=False,
             manufacturing_files=False)


def inventory(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, LineString
    from route_targeted_closure import xy
    from analyze_139_escape_blockers import protected_power

    names = ('CH022_N_ELECTRODE', 'CH024_P_MUX', 'CH019_P_MUX')
    found_pads = {}
    for net in names:
        found_pads[net] = pads(board, net)
    lookup = {name: coord for ps in found_pads.values() for name, coord, _ in ps}
    needed = ('J2.23', 'R302.1', 'U3.23', 'R49.1', 'R305.2')
    missing = set(needed) - set(lookup)
    if missing:
        raise ValueError('Critical pad identity missing: ' + ','.join(sorted(missing)))
    power = protected_power(board)
    tracks = list(board.GetTracks())
    result: dict[str, Any] = {
        **FLAGS,
        'source_pcb_sha256': FROZEN_INPUT_SHA,
        'pads': {},
        'electrode_segment_guard': [],
        'critical_pad_coordinates': {p: lookup[p] for p in needed},
    }
    for net in names:
        result['pads'][net] = []
        for label, coord, code in found_pads[net]:
            nearby = []
            for t in tracks:
                if t.GetNetName() == net:
                    continue
                if isinstance(t, pcbnew.PCB_VIA):
                    shape = Point(xy(t.GetPosition()))
                    layer = 'THROUGH'
                elif isinstance(t, pcbnew.PCB_ARC):
                    continue
                else:
                    shape = LineString([xy(t.GetStart()), xy(t.GetEnd())])
                    layer = board.GetLayerName(t.GetLayer())
                d = shape.distance(Point(coord))
                if d <= 2.5:
                    nearby.append({'net': t.GetNetname(), 'uuid': t.m_Uuid.AsString(),
                                   'layer': layer, 'distance_mm': round(d, 5)})
            nearby.sort(key=lambda x: (x['distance_mm'], x['uuid']))
            window = via_windows(board, coord, code, power)
            result['pads'][net].append({
                'pad': label, 'coordinate_mm': coord, 'via_window': window,
                'nearest_other_copper': nearby[:15],
            })
    for track in tracks:
        uid = track.m_Uuid.AsString()
        if uid not in ELECTRODE:
            continue
        if track.GetNetname() != 'CH022_N_ELECTRODE' or track.GetLayer() != pcbnew.F_Cu:
            raise ValueError('Electrode reference segment identity/layer changed')
        line = LineString([xy(track.GetStart()), xy(track.GetEnd())])
        result['electrode_segment_guard'].append({
            'uuid': uid, 'start': xy(track.GetStart()), 'end': xy(track.GetEnd()),
            'distance_J2_23_mm': round(line.distance(Point(lookup['J2.23'])), 6),
            'distance_R302_1_mm': round(line.distance(Point(lookup['R302.1'])), 6),
        })
    if {x['uuid'] for x in result['electrode_segment_guard']} != set(ELECTRODE):
        raise ValueError('Missing protected CH022 reference copper')
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Fresh JSON output required')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Generated files forbidden in repository')
    data = frozen_archive(args.archive)
    if digest(data[PCB]) != FROZEN_INPUT_SHA:
        raise ValueError('Pinned native board does not match')
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='block2-joint-pad-survey-') as td:
        path = Path(td) / PCB
        path.write_bytes(data[PCB])
        board = pcbnew.LoadBoard(str(path))
        report = inventory(board)
        if digest(path.read_bytes()) != FROZEN_INPUT_SHA:
            raise ValueError('Read-only source changed')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Pinned diagnostic ZIP changed')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Pad survey complete', len(report['electrode_segment_guard']), flush=True)


if __name__ == '__main__':
    main()

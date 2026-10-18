#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only native KiCad map of CH019-P pad escapes on SHA-locked diagnostics.

Produces no PCB edits, no manufacturing data, and no route acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_ch019_trunk_return import (ELECTRODE, TRUNK, FLAGS, PCB, pads)
from probe_block2_selective import frozen_archive, digest, ZIP_SHA


def snapshot(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box
    from analyze_139_escape_blockers import protected_power, windows
    from route_targeted_closure import routing_domain, xy

    region = routing_domain(board, .30, .25).intersection(box(12, .5, 59, 69))
    power = protected_power(board)
    points = pads(board, 'CH019_P_MUX')
    result: dict[str, Any] = {'pads': {}, 'same_net_vias': []}
    result['same_net_vias'] = [
        {'position': list(xy(track.GetPosition())),
         'uuid': track.m_Uuid.AsString(),
         'drill_mm': pcbnew.ToMM(track.GetDrillValue())}
        for track in board.GetTracks()
        if isinstance(track, pcbnew.PCB_VIA) and track.GetNetname() == 'CH019_P_MUX']
    for label, coord, net in points:
        free_component, detail = windows(board, net, coord, region, power)
        known_vias = [v['position'] for v in result['same_net_vias']]
        nearest_via = (min(Point(coord).distance(Point(p)) for p in known_vias)
                       if known_vias else None)
        result['pads'][label] = {
            'xy': list(coord), 'fcu_component_area_mm2': free_component.area,
            'legal_new_via_area_mm2': detail['legal_via_area_mm2'],
            'nearest_existing_via_mm': nearest_via,
            'top_legal_windows': detail['windows'][:8],
            'fcu_component_bounds': list(free_component.bounds),
        }
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Output must be a fresh diagnostic JSON')
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parent):
        raise ValueError('Never write generated file into engineering tree')
    content = frozen_archive(args.archive)
    import pcbnew
    report: dict[str, Any] = {**FLAGS, 'reference_archive_sha256': ZIP_SHA,
                              'scope': 'CH019_P_MUX_PAD_ACCESS', 'states': {}}
    with tempfile.TemporaryDirectory(prefix='ch019-pad-escapes-') as temp:
        path = Path(temp) / PCB
        path.write_bytes(content[PCB])
        board = pcbnew.LoadBoard(str(path))
        report['states']['baseline'] = snapshot(board)
        wanted = set(TRUNK + ELECTRODE)
        picked = {t.m_Uuid.AsString(): t for t in board.GetTracks()
                  if t.m_Uuid.AsString() in wanted}
        if set(picked) != wanted:
            raise ValueError('Pinned five selective segments not found')
        for t in picked.values():
            if (t.GetNetname(), t.GetLayer()) not in (
                    ('CH019_P_MUX', pcbnew.In2_Cu),
                    ('CH022_N_ELECTRODE', pcbnew.F_Cu)):
                raise ValueError('Unexpected copper net/layer in pinned selection')
        tracks = list(picked.values())
        for t in tracks:
            board.Remove(t)
        try:
            report['states']['five_segments_selectively_removed'] = snapshot(board)
        finally:
            for t in tracks:
                board.Add(t)
        if digest(path.read_bytes()) != digest(content[PCB]):
            raise ValueError('Source PCB mutated during read-only analysis')
    if digest(args.archive.read_bytes()) != ZIP_SHA:
        raise ValueError('Input fixture changed')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('CH019-P pad-window survey completed, unaccepted', flush=True)


if __name__ == '__main__':
    main()

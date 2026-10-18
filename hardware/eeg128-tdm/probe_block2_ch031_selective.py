#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Explore local CH031-N F.Cu replacements without reclaiming the U3.5 via corridor.

All board mutations are in memory, on a SHA-pinned *unadopted* 137 diagnostic.
No candidate is accepted. No Gerber/drill/placement/bill-of-material exports.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import (PCB, OUTPUT_FLAGS, frozen_archive,
                                     digest)

ROOT = Path(__file__).resolve().parent
PATCHES = ((48.1259, 33.8786), (46.3236, 27.4653))


def eligible_segments(board: Any, target: tuple[float, float],
                      limit: int) -> list[Any]:
    import pcbnew
    from shapely.geometry import Point, LineString
    from route_targeted_closure import xy
    pads = [Point(xy(p.GetPosition())) for fp in board.GetFootprints()
            for p in fp.Pads() if p.GetNetname() == 'CH031_N_MUX']
    vias = [Point(xy(t.GetPosition())) for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)
            and t.GetNetname() == 'CH031_N_MUX']
    centers = [Point(pt) for pt in (*PATCHES, target)]
    candidates = []
    for t in board.GetTracks():
        if t.GetNetname() != 'CH031_N_MUX' or isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
            continue
        if t.GetLayer() != pcbnew.F_Cu:
            continue
        line = LineString([xy(t.GetStart()), xy(t.GetEnd())])
        if any(line.distance(p) < .85 for p in pads):
            continue
        if any(line.distance(p) < .65 for p in vias):
            continue
        nearest = min(line.distance(p) for p in centers)
        if nearest < 1.2:
            candidates.append((nearest, t.m_Uuid.AsString(), t))
    candidates.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in candidates[:limit]]


def local_copper_inventory(board: Any, target: tuple[float, float]) -> dict[str, Any]:
    """Report all nearby CH031 copper, including protected pad/via escapes."""
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import xy
    pads = [Point(xy(p.GetPosition())) for f in board.GetFootprints()
            for p in f.Pads() if p.GetNetname() == 'CH031_N_MUX']
    vias = [Point(xy(t.GetPosition())) for t in board.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA)
            and t.GetNetname() == 'CH031_N_MUX']
    target_pt = Point(target)
    windows = [Point(p) for p in PATCHES]
    rows: list[dict[str, Any]] = []
    for t in board.GetTracks():
        if t.GetNetname() != 'CH031_N_MUX':
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            shape = Point(xy(t.GetPosition()))
            kind = 'via'
        elif isinstance(t, pcbnew.PCB_ARC):
            continue
        else:
            shape = LineString([xy(t.GetStart()), xy(t.GetEnd())])
            kind = 'segment'
        rows.append({
            'uuid': t.m_Uuid.AsString(), 'layer': int(t.GetLayer()),
            'type': kind, 'distance_U3_5_mm': shape.distance(target_pt),
            'distance_patch_mm': min(shape.distance(w) for w in windows),
            'nearest_CH031_pad_mm': min((shape.distance(v) for v in pads), default=None),
            'nearest_CH031_via_mm': min((shape.distance(v) for v in vias), default=None),
        })
    rows.sort(key=lambda r: (r['distance_U3_5_mm'], r['uuid']))
    return {'target_U3_5': list(target), 'ch031_copper_objects': len(rows),
            'nearest': rows[:30]}


def analyze(board_file: Path, limit: int) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, box
    from shapely.ops import unary_union
    from analyze_139_escape_blockers import protected_power
    from escape_mesh_505 import add_mesh_path, mesh_route
    from route_targeted_closure import xy
    from probe_block2_joint136 import pad_pair

    result: dict[str, Any] = {**OUTPUT_FLAGS, 'limit': limit,
                              'status': 'not_started', 'selected': []}
    board = pcbnew.LoadBoard(str(board_file))
    target_pads = pad_pair(board, 'CH020_P_MUX', xy)
    target = next((xy(p.GetPosition()) for f in board.GetFootprints()
                   for p in f.Pads()
                   if f.GetReference() == 'U3' and p.GetNumber() == '5'
                   and p.GetNetname() == 'CH020_P_MUX'), None)
    if target is None:
        raise ValueError('Missing named CH020-P target U3.5')
    result['local_inventory'] = local_copper_inventory(board, target)
    chosen = eligible_segments(board, target, limit)
    result['selected'] = [{'uuid': t.m_Uuid.AsString(),
                           'start': xy(t.GetStart()), 'end': xy(t.GetEnd())}
                          for t in chosen]
    if not chosen:
        result['status'] = 'no_local_ch031_segments'
        return result
    for t in chosen:
        board.Remove(t)
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    power = protected_power(board)
    region = box(12, .5, 59, 69)
    # Block a generously padded U3.5 corridor, preserving both diagnosed
    # via windows; a CH031-N detour cannot exploit their reserved copper.
    exclusion = unary_union([Point(p).buffer(.75) for p in (*PATCHES, target)])
    try:
        for t in chosen:
            start, end = xy(t.GetStart()), xy(t.GetEnd())
            avoid = exclusion.difference(Point(start).buffer(.55)).difference(
                Point(end).buffer(.55))
            path = mesh_route(board, start, end, t.GetNetCode(),
                              layers, power, region,
                              extra_obstacles=[avoid, avoid, avoid])
            if not path:
                result['status'] = 'ch031_segment_unrestored'
                result['failed_uuid'] = t.m_Uuid.AsString()
                return result
            add_mesh_path(board, path, t.GetNetCode(), layers)
        result['ch031_geom_proposed'] = True
        for name, point, _ in target_pads[1:]:
            path = mesh_route(board, target_pads[0][1], point,
                              target_pads[0][2], layers, power, region)
            if not path:
                result['status'] = 'ch020p_target_unreachable'
                result['failed_pad'] = name
                return result
            add_mesh_path(board, path, target_pads[0][2], layers)
        result['ch020p_geom_proposed'] = True
        result['status'] = 'all_geometry_proposed_native_validation_required'
        return result
    finally:
        for t in chosen:
            board.Add(t)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--limit', type=int, choices=(2, 4, 8), default=4)
    args = p.parse_args()
    if args.output.suffix != '.json' or args.output.exists():
        raise ValueError('Require new diagnostic JSON output')
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('No generated reports in repository')
    content = frozen_archive(args.archive)
    with tempfile.TemporaryDirectory(prefix='block2-ch031-selective-') as temp:
        board_file = Path(temp) / PCB
        board_file.write_bytes(content[PCB])
        try:
            result = analyze(board_file, args.limit)
        except (RuntimeError, ValueError) as exc:
            result = {**OUTPUT_FLAGS, 'status': 'model_failed', 'reason': str(exc)}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    if digest(args.archive.read_bytes()) != (
            'a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041'):
        raise ValueError('Frozen input changed')
    print(result['status'])


if __name__ == '__main__':
    main()

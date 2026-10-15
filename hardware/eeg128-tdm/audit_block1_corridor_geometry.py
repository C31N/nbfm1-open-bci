#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Check new Block-1 L3 copper against the filled, unmodified baseline planes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pcbnew
from shapely.geometry import LineString, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from merge_native_closure import copper
from route_targeted_closure import xy
from verify_hardware_identity import balanced_blocks


def power_copper(board: pcbnew.BOARD) -> BaseGeometry:
    shapes = []
    for zone in board.Zones():
        if not zone.IsOnLayer(pcbnew.In2_Cu):
            continue
        polygons = zone.GetFilledPolysList(pcbnew.In2_Cu)
        for index in range(polygons.OutlineCount()):
            outer = polygons.Outline(index)
            holes = []
            for number in range(polygons.HoleCount(index)):
                hole = polygons.Hole(index, number)
                holes.append([xy(hole.CPoint(i)) for i in range(hole.PointCount())])
            shapes.append(Polygon([xy(outer.CPoint(i)) for i in range(outer.PointCount())],
                                  holes).buffer(0))
    return unary_union(shapes)


def outlines(board: pcbnew.BOARD) -> dict[str, dict[str, Any]]:
    result = {}
    def points(chain: pcbnew.SHAPE_LINE_CHAIN) -> list[tuple[float, float]]:
        return [xy(chain.CPoint(i)) for i in range(chain.PointCount())]
    for zone in board.Zones():
        polygons = zone.Outline()
        result[zone.m_Uuid.AsString()] = {
            'net': zone.GetNetname(), 'layers': list(zone.GetLayerSet().Seq()),
            'outlines': [points(polygons.Outline(j))
                         for j in range(polygons.OutlineCount())],
            'holes': [[points(polygons.Hole(j, h))
                       for h in range(polygons.HoleCount(j))]
                      for j in range(polygons.OutlineCount())],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-block2', action='store_true')
    parser.add_argument('--include-block3', action='store_true')
    parser.add_argument('--max-power-loss-mm2', type=float,
                        help='Explicit local engineering change budget; default forbids cuts into prior power copper')
    args = parser.parse_args()
    baseline = pcbnew.LoadBoard(str(args.baseline))
    board = pcbnew.LoadBoard(str(args.board))
    original = copper(args.baseline.read_text())
    current = copper(args.board.read_text())
    names = {int(code): name for code, name in re.findall(
        r'\(net\s+(\d+)\s+"([^"]+)"\)', args.baseline.read_text())}
    normalize = lambda block: re.sub(r'\s+', '', block)
    adc = lambda items: {uid: normalize(block) for uid, block in items.items()
                         if names[int(re.search(r'\(net\s+(\d+)\)', block)[1])]
                         in {'ADC6_P', 'ADC6_N', 'ADC7_P', 'ADC7_N'}}
    adc_unchanged = adc(original) == adc(current)
    footprints_unchanged = sorted(map(normalize, balanced_blocks(args.baseline.read_text(), 'footprint'))) == sorted(
        map(normalize, balanced_blocks(args.board.read_text(), 'footprint')))
    zone_outlines_unchanged = outlines(baseline) == outlines(board)
    rules_unchanged = all(args.baseline.with_suffix(ext).read_bytes() == args.board.with_suffix(ext).read_bytes()
                          for ext in ('.kicad_pro', '.kicad_dru'))
    old_power = power_copper(baseline)
    new_power = power_copper(board)
    power_loss = old_power.difference(new_power)
    scope = box(5,5,86 if args.include_block3 else 63 if args.include_block2 else 40,65)
    outside_loss = power_loss.difference(scope)
    if args.max_power_loss_mm2 is not None:
        if not math.isfinite(args.max_power_loss_mm2) or args.max_power_loss_mm2 < 0:
            raise ValueError('Power-loss budget must be finite and nonnegative')
        if power_loss.area > args.max_power_loss_mm2 or outside_loss.area > .00001:
            raise ValueError('Refilled power loss exceeds the reviewed budget or local scope')
    nets = defaultdict(lambda: {'length_mm': 0.0, 'minimum_baseline_power_clearance_mm': None,
                               'minimum_refilled_power_clearance_mm': None,
                               'new_L3_segments': 0})
    for track in board.GetTracks():
        if (isinstance(track, pcbnew.PCB_VIA) or track.GetLayer() != pcbnew.In2_Cu
                or track.m_Uuid.AsString() in original):
            continue
        name = track.GetNetname()
        pattern = (r'CH(?:00\d|01\d|02\d|03\d|04[0-7])_[PN]_(?:MUX|ELECTRODE)' if args.include_block3
                   else r'CH(?:00\d|01\d|02\d|03[01])_[PN]_(?:MUX|ELECTRODE)' if args.include_block2
                   else r'CH(?:00\d|01[0-5])_[PN]_(?:MUX|ELECTRODE)')
        if not re.fullmatch(pattern, name):
            raise ValueError('New L3 track outside the Block-1 analog scope')
        line = LineString([xy(track.GetStart()), xy(track.GetEnd())])
        # Measure actual signal-copper edge against the previously filled plane.
        spacing = line.buffer(pcbnew.ToMM(track.GetWidth()) / 2).distance(old_power)
        if args.max_power_loss_mm2 is None and spacing < .20 - .000002:
            raise ValueError('New L3 signal invades a previously filled power corridor')
        data = nets[name]
        data['length_mm'] += pcbnew.ToMM(track.GetLength())
        data['new_L3_segments'] += 1
        minimum = data['minimum_baseline_power_clearance_mm']
        data['minimum_baseline_power_clearance_mm'] = spacing if minimum is None else min(minimum, spacing)
        spacing = line.buffer(pcbnew.ToMM(track.GetWidth()) / 2).distance(new_power)
        minimum = data['minimum_refilled_power_clearance_mm']
        data['minimum_refilled_power_clearance_mm'] = spacing if minimum is None else min(minimum,spacing)
    if not all((adc_unchanged, footprints_unchanged, zone_outlines_unchanged, rules_unchanged)):
        raise ValueError('Protected ADC, footprint, zone-outline or rule geometry changed')
    result = {
        'native_kicad_version': pcbnew.GetBuildVersion(), 'engineering_only': True,
        'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'pcb_sha256': hashlib.sha256(args.board.read_bytes()).hexdigest(),
        'ADC6_ADC7_copper_unchanged': adc_unchanged, 'footprints_unchanged': footprints_unchanged,
        'zone_outlines_unchanged': zone_outlines_unchanged, 'project_rules_unchanged': rules_unchanged,
        'new_L3_signal_geometry': dict(nets), 'required_baseline_power_clearance_mm': .20,
        'L3_power_cut_for_signal_routing': power_loss.area > .00001,
        'filled_power_before_area_mm2': old_power.area,
        'filled_power_after_area_mm2': new_power.area,
        'local_power_loss_area_mm2': power_loss.area,
        'local_power_recovered_area_mm2': new_power.difference(old_power).area,
        'outside_scope_rounding_loss_mm2': outside_loss.area,
        'outside_scope_rounding_tolerance_mm2': .00001,
        'power_loss_budget_mm2': args.max_power_loss_mm2,
        'audit_scope_bounds_mm': list(scope.bounds),
        'note': 'Signal geometry against prior filled copper; through-via antipads still require local return-path review.',
        'pair_coupling_qualified': False, 'return_current_qualified': False,
        'guard_ring_qualified': False, 'independent_lvs_signoff': False,
        'routing_completed': False, 'fabrication_release': False,
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

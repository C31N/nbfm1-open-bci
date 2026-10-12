#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Measure analog pair geometry and prioritize native routing deficits."""
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
from native_connectivity import airwire_counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', required=True, type=Path)
    parser.add_argument('--drc', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    report = json.loads(args.drc.read_text())
    if report['violations']:
        raise ValueError('Prioritize only a geometrically clean native checkpoint')
    counts = airwire_counts(report)
    geometry: dict[str, dict[str, Any]] = {}
    for _, net in board.GetNetsByNetcode().items():
        name = net.GetNetname()
        geometry[name] = {'open_airwires': counts[name], 'length_mm': {},
                          'via_count': 0, 'widths_mm': set()}
    for track in board.GetTracks():
        data = geometry[track.GetNetname()]
        if isinstance(track, pcbnew.PCB_VIA):
            data['via_count'] += 1
        else:
            layer = board.GetLayerName(track.GetLayer())
            data['length_mm'][layer] = data['length_mm'].get(layer, 0.) + pcbnew.ToMM(track.GetLength())
            data['widths_mm'].add(round(pcbnew.ToMM(track.GetWidth()), 6))
    for data in geometry.values():
        data['length_mm'] = {layer: round(length, 6) for layer, length in data['length_mm'].items()}
        data['total_copper_length_mm'] = round(sum(data['length_mm'].values()), 6)
        data['widths_mm'] = sorted(data['widths_mm'])
    deficits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for airwire in report['unconnected_items']:
        match = re.search(r'\[([^]]+)\]', airwire['items'][0]['description'])
        if not match:
            raise ValueError('Missing native airwire net')
        a, b = [item['pos'] for item in airwire['items']]
        deficits[match[1]].append({'native_items': airwire['items'],
                                 'endpoint_distance_mm': round(math.hypot(a['x']-b['x'], a['y']-b['y']), 6)})
    pairs: dict[str, dict[str, str]] = defaultdict(dict)
    for name in geometry:
        match = re.fullmatch(r'(CH\d{3}|BANK\d+|ADC\d+)_([PN])(.*)', name)
        if match:
            pairs[match[1]+match[3]][match[2]] = name
    rows = []
    for pair, names in pairs.items():
        if set(names) != {'P', 'N'}:
            raise ValueError(f'Missing logical P/N counterpart: {pair}')
        p, n = (geometry[names[polarity]] for polarity in ('P', 'N'))
        opened = p['open_airwires'] + n['open_airwires']
        priority = (1 if pair.startswith('ADC') else 2 if pair.startswith('BANK')
                    else 3 if pair.endswith('_MUX') else 4)
        rows.append({'pair': pair, 'priority': priority, 'open_airwires': opened,
                     'P': {'net': names['P'], **p}, 'N': {'net': names['N'], **n},
                     'partial_copper_length_difference_mm': round(abs(p['total_copper_length_mm']-n['total_copper_length_mm']), 6),
                     'via_count_difference': abs(p['via_count']-n['via_count']),
                     'pair_geometry_qualified': False,
                     'length_note': 'Total network copper, including branches; incomplete pairs are not length matched.',
                     'native_deficits': {names[s]: deficits[names[s]] for s in ('P', 'N') if counts[names[s]]}})
    rows.sort(key=lambda row: (row['priority'], not bool(row['open_airwires']), row['pair']))
    references = {name: geometry[name] for name in ('VCM', 'VCM_RAW', 'ADC_REFIN', 'ADS_CAP', 'DRL', 'CMS1', 'CMS2')}
    plane_rows = []
    for zone in board.Zones():
        if zone.GetNetname() == 'AGND' and zone.IsOnLayer(pcbnew.In1_Cu):
            plane_rows.append({'layer': 'In1.Cu', 'filled_islands': zone.GetFilledPolysList(pcbnew.In1_Cu).OutlineCount()})
    result = {'schema_version': 1, 'engineering_only': True,
              'pcb_sha256': hashlib.sha256(args.board.read_bytes()).hexdigest(),
              'native_kicad_version': report['kicad_version'], 'native_date': report['date'],
              'unconnected_items': len(report['unconnected_items']), 'distinct_open_nets': len(counts),
              'analog_references': references, 'analog_pairs': rows, 'AGND_L2_zones': plane_rows,
              'next_critical_open_pairs': [row['pair'] for row in rows if row['open_airwires']],
              'symmetry_limits_specified': False, 'shielding_or_driven_guard_signoff': False,
              'schematic_origin': 'Repository schematic generated from PCB pad/net assignments; not an independent circuit authority.',
              'routing_completed': False, 'fabrication_release': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'open_airwires': result['unconnected_items'],
                      'critical_open_pairs': result['next_critical_open_pairs'][:12],
                      'references_open': sum(data['open_airwires'] for data in references.values()),
                      'ADC_open': sum(row['open_airwires'] for row in rows if row['pair'].startswith('ADC')),
                      'pair_geometry_qualified': False}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Classify real native airwires, preserving endpoint/pin evidence."""
import argparse
from collections import Counter, defaultdict
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re


def analyze(report, project):
    patterns = project['net_settings']['netclass_patterns']
    classes, groups, clusters = Counter(), Counter(), Counter()
    pins = defaultdict(Counter)
    rows = []
    for index, airwire in enumerate(report['unconnected_items']):
        nets = {re.search(r'\[([^]]+)\]', item['description']).group(1)
                for item in airwire['items'] if '[' in item['description']}
        if len(nets) != 1:
            raise ValueError(f'Ambiguous airwire {index}: {nets}')
        net = next(iter(nets))
        nc = next((p['netclass'] for p in patterns if fnmatchcase(net, p['pattern'])), 'Default')
        group = ('AGND' if net == 'AGND' else nc if nc != 'Default'
                 else 'MUX_CONTROL' if net.startswith('MUX_') else 'OTHER')
        classes[nc] += 1
        groups[group] += 1
        touched = set()
        for item in airwire['items']:
            match = re.search(r'Pad (\S+) \[[^]]+\] of (\w+) on', item['description'])
            if match:
                pin, ref = match.groups()
                pins[ref][pin] += 1
                cluster = ('RP2040_U23' if ref == 'U23' else 'ADS131M08_U21' if ref == 'U21'
                           else 'MUX_U1_U16' if ref in {f'U{i}' for i in range(1, 17)}
                           else 'BUFFER_U17_U20' if ref in {f'U{i}' for i in range(17, 21)}
                           else 'CONNECTOR' if ref.startswith('J') else 'PASSIVES_OTHER')
                touched.add(cluster)
        for cluster in touched:
            clusters[cluster] += 1
        rows.append({'index': index, 'net': net, 'netclass': nc, 'group': group,
                     'clusters': sorted(touched), 'endpoints': airwire['items']})
    return {'kicad_version': report['kicad_version'], 'native_date': report['date'],
            'unconnected': len(rows), 'exclusive_groups': dict(groups),
            'exclusive_netclasses': dict(classes), 'overlapping_cluster_airwires': dict(clusters),
            'pin_endpoint_occurrences': {ref: dict(count) for ref, count in sorted(pins.items())},
            'airwires': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--drc', type=Path, required=True)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = analyze(json.loads(a.drc.read_text()), json.loads(a.project.read_text()))
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('airwires', 'pin_endpoint_occurrences')}, indent=2))


if __name__ == '__main__':
    main()

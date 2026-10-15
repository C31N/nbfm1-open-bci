#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact-scope copper and whole-board filled-power audit for a MUX pair."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import pcbnew
from shapely.geometry import LineString
from audit_block1_corridor_geometry import outlines, power_copper
from merge_native_closure import copper
from route_targeted_closure import xy
from verify_hardware_identity import balanced_blocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'board', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--channel', required=True, type=int)
    args = parser.parse_args()
    old_text, new_text = args.baseline.read_text(), args.board.read_text()
    old, new = copper(old_text), copper(new_text)
    normalize = lambda s: re.sub(r'\s+', '', s)
    existing = all(uid in new and normalize(block) == normalize(new[uid]) for uid, block in old.items())
    names = {int(code): name for code, name in re.findall(r'\(net\s+(\d+)\s+"([^"]+)"\)', new_text)}
    permitted = {f'CH{args.channel:03d}_{p}_MUX' for p in 'PN'}
    added = {uid: block for uid, block in new.items() if uid not in old}
    assert existing and added
    assert all(names[int(re.search(r'\(net\s+(\d+)\)', block)[1])] in permitted for block in added.values())
    footprints = lambda t: sorted(normalize(x) for x in balanced_blocks(t, 'footprint'))
    b0, b1 = pcbnew.LoadBoard(str(args.baseline)), pcbnew.LoadBoard(str(args.board))
    assert footprints(old_text) == footprints(new_text)
    assert outlines(b0) == outlines(b1)
    assert all(args.baseline.with_suffix(ext).read_bytes() == args.board.with_suffix(ext).read_bytes()
               for ext in ('.kicad_pro', '.kicad_dru'))
    power0, power1 = power_copper(b0), power_copper(b1)
    loss = power0.difference(power1).area
    assert loss == 0, f'L3 power loss: {loss}'
    nets = {name: {'length_mm': 0., 'L3_length_mm': 0., 'vias': 0,
                   'minimum_L3_baseline_power_clearance_mm': None} for name in permitted}
    for track in b1.GetTracks():
        if track.m_Uuid.AsString() not in added:
            continue
        data = nets[track.GetNetname()]
        if isinstance(track, pcbnew.PCB_VIA):
            data['vias'] += 1
            continue
        length = pcbnew.ToMM(track.GetLength())
        data['length_mm'] += length
        if track.GetLayer() == pcbnew.In2_Cu:
            data['L3_length_mm'] += length
            spacing = LineString([xy(track.GetStart()), xy(track.GetEnd())]).buffer(pcbnew.ToMM(track.GetWidth())/2).distance(power0)
            assert spacing >= .20-2e-6
            old_min = data['minimum_L3_baseline_power_clearance_mm']
            data['minimum_L3_baseline_power_clearance_mm'] = spacing if old_min is None else min(old_min, spacing)
    result = {'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
              'pcb_sha256': hashlib.sha256(args.board.read_bytes()).hexdigest(),
              'permitted_new_nets': sorted(permitted), 'added_copper_objects': len(added),
              'existing_copper_unchanged': True, 'footprints_unchanged': True,
              'zone_outlines_unchanged': True, 'project_rules_unchanged': True,
              'L3_power_loss_mm2': loss, 'L3_power_gain_mm2': power1.difference(power0).area,
              'new_signal_geometry': nets, 'pair_skew_qualified': False,
              'return_current_qualified': False, 'independent_lvs_signoff': False,
              'routing_completed': False, 'fabrication_release': False}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

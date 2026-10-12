#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Create a separate, fail-closed PCB/generated-schematic parity diagnostic.

This is consistency with PCB-derived connectivity, not independent circuit LVS.
The primary PCB, schematic, BOM and fabrication artifacts are never written.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from generate_schematic import deterministic_uuid, normalized_pads, parse_bom, parse_components
from native_connectivity import regressed_nets
from run_native_closure import verify

NC_PINS = {'J9': {'A8', 'B8'}, 'U21': {'22', '27'}, 'U24': {'4'}, 'U25': {'4'},
           'U23': {'2','3','9','17','18','24','25','26','27','28','29','30','31','32',
                   '34','35','36','37','38','39','40','41'}}


def mutate(board: Path, output: Path) -> None:
    import pcbnew
    from route_targeted_closure import vector
    b = pcbnew.LoadBoard(str(board))
    bom = parse_bom()
    values, nc, shield = [], [], []
    for f in b.GetFootprints():
        ref = f.GetReference()
        target = bom[ref][0]
        if f.GetValue() != target:
            values.append({'reference': ref, 'before': f.GetValue(), 'after': target})
            f.SetValue(target)
        for pad in f.Pads():
            pin = pad.GetNumber()
            if pad.GetNetCode() or not pin:
                continue
            if ref == 'J9' and pin == 'S1':
                pad.SetNet(b.FindNet('SHIELD'))
                shield.append(pad.m_Uuid.AsString())
                continue
            if pin not in NC_PINS.get(ref, set()):
                raise ValueError(f'Unreviewed no-net pad: {ref}.{pin}')
            name = f'unconnected-({ref}-Pin_{pin}-Pad{pin})'
            net = pcbnew.NETINFO_ITEM(b, name)
            b.Add(net)
            pad.SetNet(net)
            nc.append({'reference': ref, 'pin': pin, 'net': name,
                       'uuid': pad.m_Uuid.AsString()})
    if len(nc) != 28 or len(shield) != 3:
        raise ValueError('Use the pre-correction checkpoint; do not apply twice')
    if {(item['reference'], item['pin']) for item in nc} != {
            (ref, pin) for ref, pins in NC_PINS.items() for pin in pins}:
        raise ValueError('No-connect pin set differs from the reviewed set')
    nc_codes = {b.FindNet(item['net']).GetNetCode() for item in nc}
    if any(t.GetNetCode() in nc_codes for t in b.GetTracks()) or any(
            z.GetNetCode() in nc_codes for z in b.Zones()):
        raise ValueError('An explicit NC net has routing or a copper plane')
    copper_uuids = {}
    for a, z in [((181.87,72.68),(186.05,72.68)),
                 ((186.05,72.68),(186.05,81.32)),
                 ((186.05,81.32),(181.87,81.32))]:
        track = pcbnew.PCB_TRACK(b)
        track.SetStart(vector(a)); track.SetEnd(vector(z))
        track.SetWidth(pcbnew.FromMM(.2)); track.SetLayer(pcbnew.B_Cu)
        track.SetNetCode(b.FindNet('SHIELD').GetNetCode())
        copper_uuids[track.m_Uuid.AsString()] = deterministic_uuid(f'parity-shield:{a}:{z}')
        b.Add(track)
    pcbnew.SaveBoard(str(board), b)
    text = board.read_text()
    for old, new in copper_uuids.items():
        marker = f'(uuid "{old}")'
        if text.count(marker) != 1:
            raise ValueError('SHIELD copper UUID is not unique')
        text = text.replace(marker, f'(uuid "{new}")', 1)
    board.write_text(text)
    (output/'parity-mutations.json').write_text(json.dumps(
        {'BOM_value_changes': values, 'isolated_NC_pads': nc,
         'SHIELD_tabs': shield, 'unnumbered_pads_unchanged': True}, indent=2)+'\n')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    board = root/'eeg128-tdm.kicad_pcb'
    source = args.board.resolve()
    hashes = {}
    for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
        hashes[ext] = hashlib.sha256(source.with_suffix(ext).read_bytes()).hexdigest()
        shutil.copy2(source.with_suffix(ext), board.with_suffix(ext))
    before = verify(board, root/'drc-before.json')
    project_bytes = board.with_suffix('.kicad_pro').read_bytes()
    module = Path(__file__).resolve().parent
    child = (f'import sys;sys.path.insert(0,{str(module)!r});from pathlib import Path;'
             'from prepare_native_parity import mutate;'
             f'mutate(Path({str(board)!r}),Path({str(root)!r}))')
    with (root/'mutation.log').open('w') as log:
        subprocess.run([sys.executable,'-c',child],check=True,stdout=log,stderr=subprocess.STDOUT)
    # SaveBoard can write a default project: preserve the actual net classes.
    board.with_suffix('.kicad_pro').write_bytes(project_bytes)
    subprocess.run([sys.executable,str(module/'generate_schematic.py'),
                    '--pcb',str(board),'--output',str(board.with_suffix('.kicad_sch'))],check=True)
    after = verify(board, root/'drc-final.json')
    if regressed_nets(before, after) or len(after['unconnected_items']) != len(before['unconnected_items']):
        raise ValueError('Parity correction changed routing completeness')
    subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all',
                    '--all-track-errors','--schematic-parity','--output',
                    str(root/'drc-parity.json'),str(board)],check=True)
    report = json.loads((root/'drc-parity.json').read_text())
    if report['violations'] or report['schematic_parity']:
        raise ValueError('Native PCB/generated-schematic parity did not pass')
    subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                    '--output',str(root/'netlist.xml'),str(board.with_suffix('.kicad_sch'))],check=True)
    expected = {(c.ref,pin):net for c in parse_components(board)
                for pin,net in normalized_pads(c)}
    tree = ET.parse(root/'netlist.xml')
    actual = {(node.attrib['ref'],node.attrib['pin']):net.attrib['name']
              for net in tree.findall('./nets/net') for node in net.findall('node')}
    if actual != expected:
        raise ValueError('Full native XML pin/net map differs from PCB')
    result = {'native_kicad_version':report['kicad_version'],'baseline_sha256':hashes,
              'pcb_violations':0,'pcb_warnings':0,'schematic_parity_items':0,
              'unconnected':len(report['unconnected_items']),'pin_net_assignments_verified':len(expected),
              'generated_connectivity_parity_pass':True,'independent_lvs_signoff':False,
              'routing_completed':False,'fabrication_release':False}
    (root/'parity-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()

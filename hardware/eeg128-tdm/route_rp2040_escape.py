#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Atomic RP2040 EP grid and QSPI corridor reconstruction, native KiCad 8 gate.

A 3x3 0.60/0.30 mm through-via grid, 0.90 mm pitch, retains primary
fabrication rules. All other-net copper touching the reserved L4 corridor
must be QSPI; otherwise refuse the operation. Partial reroutes are retained
as diagnostics only and never promoted to accepted.kicad_pcb.
"""
import argparse, itertools, json, math, shutil, time
from pathlib import Path
import route_targeted_closure as r
from verify_hardware_identity import balanced_blocks
import re

QSPI = {'QSPI_CLK','QSPI_SS',*(f'QSPI_SD{i}' for i in range(4))}

def remove_uuid(text, uuid):
    text=re.sub(r'\((segment|via|arc)(?=\s)',r'(\1 ',text)
    for token in ('segment','via','arc'):
        for block in balanced_blocks(text,token):
            if uuid in block: return text.replace(block,'',1)
    raise RuntimeError('Missing native item UUID: '+uuid)

def cleanup_qspi_stubs(working, report, directory):
    """Remove obsolete reroute stubs only with a fresh native regression gate."""
    for _ in range(12):
        changed=False
        for warning in report['violations']:
            if warning['type'] not in ('track_dangling','via_dangling'): continue
            if not all(any('['+net+']' in i['description'] for net in QSPI) for i in warning['items']): continue
            trial=directory/'cleanup.kicad_pcb'; text=working.read_text()
            for item in warning['items']: text=remove_uuid(text,item['uuid'])
            trial.write_text(text)
            for ext in ('.kicad_pro','.kicad_dru'): shutil.copy2(working.with_suffix(ext),trial.with_suffix(ext))
            candidate=r.native(trial,directory/'drc-cleanup.json')
            good=(not any(v['severity']=='error' for v in candidate['violations'])
                  and len(candidate['violations'])<len(report['violations'])
                  and len(candidate['unconnected_items'])<=len(report['unconnected_items']))
            if good:
                shutil.copy2(trial,working); report=candidate; changed=True; break
        if not changed: break
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--board',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--seconds',type=int,default=900)
    a=ap.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
    working=a.output_dir/'eeg128-tdm.kicad_pcb'
    for ext in ('.kicad_pcb','.kicad_pro','.kicad_dru'):
        shutil.copy2(a.board.with_suffix(ext),working.with_suffix(ext))
    baseline=r.native(working,a.output_dir/'drc-initial.json')
    if r.metrics(baseline)['violations'] or r.metrics(baseline)['warnings']:
        raise RuntimeError('Baseline must have zero native violations and warnings')
    accepted=a.output_dir/'accepted.kicad_pcb'; shutil.copy2(working,accepted)
    b=r.pcbnew.LoadBoard(str(working))
    fp=next(f for f in b.GetFootprints() if f.GetReference()=='U23')
    ep=next(p for p in fp.Pads() if p.GetNumber()=='57')
    center=r.xy(ep.GetPosition()); code=ep.GetNetCode()
    corridor=r.box(center[0]-1.6,center[1]-1.6,center[0]+1.6,center[1]+1.6)
    removed=[]; replaced_ground_vias=[]; other_obstructions=[]
    for t in list(b.GetTracks()):
        if isinstance(t,r.pcbnew.PCB_VIA) and t.GetNetCode()==code and corridor.contains(r.Point(r.xy(t.GetPosition()))):
            replaced_ground_vias.append({'uuid':t.m_Uuid.AsString(),'position':r.xy(t.GetPosition())})
        if isinstance(t,r.pcbnew.PCB_VIA) or t.GetLayer()!=r.pcbnew.B_Cu: continue
        geometry=r.LineString([r.xy(t.GetStart()),r.xy(t.GetEnd())]).buffer(r.pcbnew.ToMM(t.GetWidth())/2+.155)
        if geometry.intersects(corridor) and t.GetNetCode()!=code:
            if t.GetNetname() not in QSPI:
                other_obstructions.append({'net':t.GetNetname(),'uuid':t.m_Uuid.AsString()})
                continue
            removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'start':r.xy(t.GetStart()),'end':r.xy(t.GetEnd())})
    if other_obstructions:
        shutil.copy2(a.output_dir/'drc-initial.json',a.output_dir/'drc-final.json')
        result={'grid_promoted':False,'reason':'Reserved L4 corridor contains non-QSPI copper; retained baseline.',
                'other_obstructions':other_obstructions,'routing_completed':False,'fabrication_release':False,
                'native_kicad_version':baseline['kicad_version'],**r.metrics(baseline)}
        (a.output_dir/'escape-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True);return
    # Serialize removals by UUID. KiCad 8 SWIG Remove ownership can invalidate
    # Python wrappers; parsing retained native S-expressions avoids that hazard.
    text=working.read_text()
    text=re.sub(r'\((segment|via|arc)(?=\s)',r'(\1 ',text)
    for entry in removed+replaced_ground_vias: text=remove_uuid(text,entry['uuid'])
    working.write_text(text)
    b=r.pcbnew.LoadBoard(str(working))
    grid=[]
    for dx,dy in itertools.product((-.9,0,.9),repeat=2):
        point=(center[0]+dx,center[1]+dy); r.make_via(b,point,code,.60); grid.append(point)
    r.pcbnew.SaveBoard(str(working),b)
    report=r.native(working,a.output_dir/'drc-grid.json')
    history=[]; deadline=time.monotonic()+a.seconds
    # Top-only first, then local L1/L4 transitions around (never through) EP.
    for iteration in range(30):
        opens=[i for i in report['unconnected_items'] if r.net_of(i) in QSPI]
        # Start with SD0's narrow escape before neighboring bus lanes consume
        # its available transition sites.
        order={name:index for index,name in enumerate(('QSPI_SD0','QSPI_SD1','QSPI_CLK','QSPI_SS','QSPI_SD2','QSPI_SD3'))}
        opens.sort(key=lambda i:order[r.net_of(i)])
        if not opens or time.monotonic()>=deadline: break
        lookup=r.objects(b); progress=False
        for air in opens:
            ends=[lookup[i['uuid']] for i in air['items']]
            pairs=sorted(itertools.product(r.connected_anchors(b,ends[0]),r.connected_anchors(b,ends[1])),
                         key=lambda pair:math.dist(pair[0][1:],pair[1][1:]))[:24]
            net=r.net_of(air); nc=ends[0].GetNetCode()
            for both in (False,True):
                for anchor_start,anchor_goal in pairs:
                    if time.monotonic()>=deadline: break
                    start,goal=anchor_start[1:],anchor_goal[1:]; layers=[anchor_start[0],anchor_goal[0]]
                    if not both and layers!=[0,0]: continue
                    path=r.search(b,start,goal,nc,.20,.15,both,8.,step=.10,
                                  deadline=min(deadline,time.monotonic()+5),start_layer=layers[0],goal_layer=layers[1],reserved_bottom=corridor)
                    if not path: continue
                    candidate=r.pcbnew.LoadBoard(str(working)); r.add_path(candidate,path,nc,.20)
                    trial=a.output_dir/'trial.kicad_pcb'
                    # Sidecar basename matters for custom rules.
                    for ext in ('.kicad_pro','.kicad_dru'): shutil.copy2(working.with_suffix(ext),trial.with_suffix(ext))
                    r.pcbnew.SaveBoard(str(trial),candidate)
                    test=r.native(trial,a.output_dir/'drc-trial.json')
                    errors=[v for v in test['violations'] if v['severity']=='error']
                    remaining=sum(r.net_of(i) in QSPI for i in test['unconnected_items'])
                    good=not errors and remaining<len(opens)
                    event={'net':net,'both_layers':both,'accepted_partial':good,'qspi_open':remaining,**r.metrics(test)}
                    history.append(event); print(json.dumps(event),flush=True)
                    if good:
                        shutil.copy2(trial,working); b=r.pcbnew.LoadBoard(str(working)); report=test; progress=True
                        break
                if progress: break
            if progress: break
        if not progress: break
    candidate_report=r.native(working,a.output_dir/'drc-candidate.json')
    if not any(r.net_of(i) in QSPI for i in candidate_report['unconnected_items']):
        candidate_report=cleanup_qspi_stubs(working,candidate_report,a.output_dir)
        candidate_report=r.native(working,a.output_dir/'drc-candidate.json')
    m=r.metrics(candidate_report)
    closed_qspi=not any(r.net_of(i) in QSPI for i in candidate_report['unconnected_items'])
    closed_ep=not any(any('Pad 57 ' in j['description'] and 'U23 ' in j['description'] for j in i['items']) for i in candidate_report['unconnected_items'])
    promote=closed_qspi and closed_ep and not m['violations'] and not m['warnings'] and m['unconnected']<len(baseline['unconnected_items'])
    if promote: shutil.copy2(working,accepted)
    else: shutil.copy2(working,a.output_dir/'rejected-grid.kicad_pcb'); shutil.copy2(accepted,working)
    final=r.native(working,a.output_dir/'drc-final.json')
    result={'native_kicad_version':final['kicad_version'],'grid_diameter_mm':.60,'grid_drill_mm':.30,'grid_pitch_mm':.90,
            'grid_layer_span':['F.Cu','B.Cu'],'ground_plane':'In1.Cu','grid_coordinates_mm':grid,'removed_qspi_segments':removed,
            'replaced_ground_vias':replaced_ground_vias,
            'grid_promoted':promote,'candidate_metrics':m,'qspi_closed':closed_qspi,'ep_closed':closed_ep,
            'routing_completed':False,'fabrication_release':False,**r.metrics(final),'history':history}
    (a.output_dir/'escape-result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result),flush=True)

if __name__=='__main__': main()

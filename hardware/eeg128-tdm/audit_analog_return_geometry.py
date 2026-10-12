#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Measure projected reference copper and P/N distances; no electrical signoff."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
import pcbnew
from shapely.geometry import MultiLineString, Point
from route_targeted_closure import xy, vector


def percentile(values, fraction):
    if not values:return None
    ordered=sorted(values);index=(len(ordered)-1)*fraction;a=int(index);b=min(a+1,len(ordered)-1)
    return ordered[a]+(ordered[b]-ordered[a])*(index-a)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--net', action='append', default=[],
                   help='Audit these P/N nets; repeat for both members of a channel pair')
    args=p.parse_args();board=pcbnew.LoadBoard(str(args.board));zones=list(board.Zones());tracks=defaultdict(lambda:defaultdict(list))
    requested=set(args.net or ['ADC6_P','ADC6_N','ADC7_P','ADC7_N'])
    for name in requested:
        if board.FindNet(name) is None:raise ValueError(f'Unknown audit net: {name}')
    for t in board.GetTracks():
        if not isinstance(t,pcbnew.PCB_VIA) and t.GetNetname() in requested:
            tracks[t.GetNetname()][t.GetLayer()].append(t)
    ground=[z for z in zones if z.GetNetname()=='AGND' and z.IsOnLayer(pcbnew.In1_Cu)]
    power=[z for z in zones if z.IsOnLayer(pcbnew.In2_Cu)]
    coverage=[];coupling=[]
    for name,bylayer in tracks.items():
        for layer,items in bylayer.items():
            total=0.;center=0.;corridor=0.;l3=defaultdict(float);gaps=[]
            other=re.sub(r'_(P|N)(?=_|$)',lambda m:'_N' if m[1]=='P' else '_P',name)
            opposite=[(xy(t.GetStart()),xy(t.GetEnd())) for t in tracks.get(other,{}).get(layer,[])]
            shape=MultiLineString(opposite) if opposite else None;distances=[]
            for t in items:
                a,b=xy(t.GetStart()),xy(t.GetEnd());length=math.dist(a,b)
                if not length:continue
                count=max(1,math.ceil(length/.05));weight=length/count;nx=-(b[1]-a[1])/length;ny=(b[0]-a[0])/length
                run=0.;max_run=0.
                for i in range(count):
                    f=(i+.5)/count;point=(a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]));total+=weight
                    inside=any(z.HitTestFilledArea(pcbnew.In1_Cu,vector(point)) for z in ground)
                    if inside:center+=weight;run=0.
                    else:run+=weight;max_run=max(max_run,run)
                    samples=[point,(point[0]+.30*nx,point[1]+.30*ny),(point[0]-.30*nx,point[1]-.30*ny)]
                    if all(any(z.HitTestFilledArea(pcbnew.In1_Cu,vector(v)) for z in ground) for v in samples):corridor+=weight
                    if layer==pcbnew.B_Cu:
                        hits=[z.GetNetname() for z in power if z.HitTestFilledArea(pcbnew.In2_Cu,vector(point))]
                        for net in hits:l3[net]+=weight
                        if not hits:l3['no_filled_L3_zone']+=weight
                    if shape is not None:distances.append(Point(point).distance(shape))
                if max_run:gaps.append({'track_uuid':t.m_Uuid.AsString(),'longest_sampled_uncovered_run_mm':max_run})
            coverage.append({'net':name,'signal_layer':board.GetLayerName(layer),'sampled_length_mm':total,
                             'sample_step_max_mm':.05,'L2_AGND_centerline_coverage_percent':100*center/total,
                             'L2_AGND_center_plus_minus_0_30_mm_coverage_percent':100*corridor/total,
                             'L3_projection_length_mm':dict(l3),'uncovered_runs':gaps,
                             'note':'Filled-copper projection only. Signal-via anti-pads are legitimate gaps; no 3D return-current model.'})
            coupling.append({'net':name,'layer':board.GetLayerName(layer),'opposite_net':other,'samples':len(distances),
                             'track_centerline_to_opposite_track_distance_mm':{'minimum':min(distances) if distances else None,
                              'median':percentile(distances,.5),'p95':percentile(distances,.95),'maximum':max(distances) if distances else None},
                             'note':'Excludes pads/vias; distances are geometric, not an impedance/coupling measurement.'})
    result={'schema_version':1,'engineering_only':True,'native_kicad_version':pcbnew.GetBuildVersion(),
            'audited_nets':sorted(requested),
            'pcb_sha256':hashlib.sha256(args.board.read_bytes()).hexdigest(),
            'L2_AGND_filled_islands':sum(z.GetFilledPolysList(pcbnew.In1_Cu).OutlineCount() for z in ground),
            'reference_projection':coverage,'pair_distance_samples':coupling,
            'return_current_qualified':False,'pair_coupling_qualified':False,'ADC_guard_ring_qualified':False,
            'qualification_limits_specified':False,'independent_lvs_signoff':False,
            'routing_completed':False,'fabrication_release':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'L2_AGND_islands':result['L2_AGND_filled_islands'],'projection':[
        {k:r[k] for k in ('net','signal_layer','L2_AGND_centerline_coverage_percent','L3_projection_length_mm')} for r in coverage],
        'coupling':coupling,'qualified':False}))

if __name__=='__main__':main()

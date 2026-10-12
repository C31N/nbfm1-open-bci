#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Analytical ADC6/ADC7 copper/via measurements without a fabricated signoff."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import pcbnew


def point(p):
    return (round(pcbnew.ToMM(p.x),6),round(pcbnew.ToMM(p.y),6))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();board=pcbnew.LoadBoard(str(args.board));pairs=[]
    for index in (6,7):
        sides={}
        for side in ('P','N'):
            name=f'ADC{index}_{side}';length=defaultdict(float);vias=[];widths=set();degree=Counter();edges=0
            adjacency=defaultdict(set)
            for t in board.GetTracks():
                if t.GetNetname()!=name:continue
                if isinstance(t,pcbnew.PCB_VIA):
                    vias.append({'position_mm':point(t.GetPosition()),'diameter_mm':round(pcbnew.ToMM(t.GetWidth()),6),
                                 'drill_mm':round(pcbnew.ToMM(t.GetDrillValue()),6),'layer_pair':['F.Cu','B.Cu']})
                else:
                    length[board.GetLayerName(t.GetLayer())]+=pcbnew.ToMM(t.GetLength())
                    # Merge nanometre serialization offsets at the same junction.
                    # This is an analytical graph; native copper DRC is authoritative.
                    a,z=(tuple(round(v,3) for v in point(pos)) for pos in (t.GetStart(),t.GetEnd()))
                    widths.add(round(pcbnew.ToMM(t.GetWidth()),6));degree.update([a,z]);edges+=1
                    adjacency[a].add(z);adjacency[z].add(a)
            pending=set(adjacency);components=0
            while pending:
                components+=1;stack=[pending.pop()]
                while stack:
                    for node in adjacency[stack.pop()]:
                        if node in pending:pending.remove(node);stack.append(node)
            sides[side]={'net':name,'copper_length_by_layer_mm':dict(length),'total_copper_length_mm':sum(length.values()),
                         'widths_mm':sorted(widths),'vias':sorted(vias,key=lambda v:v['position_mm'][1]),
                         'track_endpoint_degrees':dict(Counter(degree.values())),
                         'endpoint_graph_cycle_rank_if_connected':edges-len(degree)+1,
                         'endpoint_graph_snap_mm':.001,'endpoint_graph_components':components,
                         'branchless_endpoint_graph':components==1 and all(v<=2 for v in degree.values()) and sum(v==1 for v in degree.values())==2}
        a,z=sides['P'],sides['N'];matched=[]
        if len(a['vias'])==len(z['vias']):
            for v,w in zip(a['vias'],z['vias']):
                matched.append({'P_mm':v['position_mm'],'N_mm':w['position_mm'],
                                'delta_x_mm':round(abs(v['position_mm'][0]-w['position_mm'][0]),6),
                                'delta_y_mm':round(abs(v['position_mm'][1]-w['position_mm'][1]),6),
                                'same_drill_and_diameter':(v['diameter_mm'],v['drill_mm'])==(w['diameter_mm'],w['drill_mm'])})
        pairs.append({'pair':f'ADC{index}',**sides,
                      'total_copper_length_difference_mm':abs(a['total_copper_length_mm']-z['total_copper_length_mm']),
                      'via_transition_comparison':matched,'pair_geometry_qualified':False,
                      'length_tolerance_mm':None,'coupling_spacing_tolerance_mm':None,
                      'note':'Copper centerline geometry only; no delay/impedance/bench measurement or SI signoff.'})
    result={'schema_version':1,'engineering_only':True,'pcb_sha256':hashlib.sha256(args.board.read_bytes()).hexdigest(),
            'native_kicad_version':pcbnew.GetBuildVersion(),'pairs':pairs,'symmetry_limits_specified':False,
            'routing_completed':False,'fabrication_release':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{'pair':p['pair'],'length_delta_mm':p['total_copper_length_difference_mm'],
                       'vias':{s:len(p[s]['vias']) for s in ('P','N')},'transitions':p['via_transition_comparison']} for p in pairs]))

if __name__=='__main__':main()

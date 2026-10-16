#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded 139-baseline proposals. Never promote a model or export fabrication data.

Each invocation is a separate KiCad process. Use Shapely 2.1.2 in an isolated
Python environment with the native KiCad 8.0.9 pcbnew module available.
"""
import argparse
import hashlib
import itertools
import json
import shutil
import subprocess
from pathlib import Path
import pcbnew
from shapely.geometry import box
from route_targeted_closure import xy, make_via
from analyze_139_escape_blockers import BASE_SHA, protected_power
from escape_mesh import mesh_route, add_mesh_path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--mode',choices=['electrode','local-electrode','reserved-electrode','mux'],required=True)
    p.add_argument('--case',type=int,required=True)
    a=p.parse_args()
    if hashlib.sha256(a.board.read_bytes()).hexdigest()!=BASE_SHA:
        raise ValueError('Wrong immutable 139 PCB')
    if subprocess.check_output(['kicad-cli','version'],text=True).strip()!='8.0.9' or not pcbnew.GetBuildVersion().startswith('8.0.9'):
        raise ValueError('Native KiCad 8.0.9 required')
    a.output_dir.mkdir(parents=True,exist_ok=False)
    b=pcbnew.LoadBoard(str(a.board));power=protected_power(b)
    mainnet='CH021_N_ELECTRODE';src='CH027_P_ELECTRODE';tgt='CH023_N_ELECTRODE'
    other=pcbnew.B_Cu if a.case%2 else pcbnew.In2_Cu
    removed=[];requests=[];head=None
    region=box(26,.5,55,34)
    if a.mode=='electrode':
        cases=[(s,t,o,l) for s,t in itertools.product(
            ['CH027_P_ELECTRODE','CH026_P_ELECTRODE'],
            ['CH023_N_ELECTRODE','CH022_N_ELECTRODE','CH019_N_ELECTRODE'])
            for o in [(mainnet,s,t),(s,mainnet,t),(t,mainnet,s)]
            for l in [pcbnew.In2_Cu,pcbnew.B_Cu]]
        src,tgt,order,other=cases[a.case]
        removed=[t for t in b.GetTracks() if t.GetNetname() in (src,tgt)]
        for name in order:
            pads=[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()==name]
            requests.append((name,xy(pads[0].GetPosition()),xy(pads[1].GetPosition()),0,0,
                             pcbnew.In2_Cu if name==mainnet else other))
    elif a.mode in ('local-electrode','reserved-electrode'):
        if a.mode=='reserved-electrode' and not 0<=a.case<6:raise ValueError('Case must be 0..5')
        kept27={(38.75,21.779999),(36.55,6.279999),(36.55,10.379999)}
        for t in b.GetTracks():
            x,y=xy(t.GetStart()),xy(t.GetEnd());remove=False
            if t.GetNetname()==src:
                if isinstance(t,pcbnew.PCB_VIA):remove=x not in kept27
                elif t.GetLayer()==pcbnew.B_Cu:remove=x!=(36.55,6.279999)
                else:remove=not ((x[0]>=38.75 and y[0]>=38.75 and x[1]>=20.7 and y[1]>=20.7) or max(x[1],y[1])<10.38)
            elif t.GetNetname()==tgt:
                if isinstance(t,pcbnew.PCB_VIA):remove=x!=(36.55,11.979999)
                elif t.GetLayer()==pcbnew.In2_Cu:remove=True
                else:remove=min(x[0],y[0])>40
            if remove:removed.append(t)
        if a.mode=='reserved-electrode':
            head=(50.4762,8.808369)
            order=[mainnet,src,tgt] if a.case<2 or a.case==5 else [mainnet,tgt,src]
        else:order=list(itertools.permutations((mainnet,src,tgt)))[a.case//2]
        for name in order:
            if name==mainnet:req=(name,(43.25,7.6),(36.15,18.2),0,0,pcbnew.In2_Cu)
            elif name==src:req=(name,(36.55,10.379999),(38.75,21.779999),1,1,other)
            else:req=(name,(36.55,11.979999),head or (44.25,7.6),1,1 if head else 0,other)
            if a.mode=='reserved-electrode' and a.case>=4 and name!=mainnet:
                req=(*req[:3],0,0,(pcbnew.B_Cu,pcbnew.In2_Cu))
            requests.append(req)
    else:
        mainnet='CH018_P_MUX';region=box(.5,10,64,84)
        s0={'61a3f472-7173-4f80-b4c4-31c19b8c04ba','5a7bb702-d689-4e89-8e14-ebd863a014c8','cf5fe3a2-9c1f-400c-8633-97934484b133','df2eae63-8e0b-4527-b7ce-1c3d38ff4dd8','ff9f490d-9f0d-4dc1-96a8-089ed3689134','8a8a90ef-22d5-4e06-96d9-93c2d001cb17','0fdbc79e-9453-4361-9b09-409cdd7db6a8'}
        s1={'2ac3aecb-9a62-4bc7-846a-75a782ad0474','2be13bbb-5c8b-457a-8d56-1fd7975b5586','7feef6a7-ad8c-4e99-b6f1-4a863b9d9f6e','8f5e8f5d-4ea6-4308-b438-632b4dd2387a','ddef0ce1-ae67-4b9f-9111-1086bd532429'}
        removed=[t for t in b.GetTracks() if t.m_Uuid.AsString() in s0|s1]
        if len(removed)!=len(s0|s1):raise ValueError('Reviewed local copper differs')
        order=list(itertools.permutations((mainnet,'MUX_S0','MUX_S1')))[a.case]
        for name in order:
            if name==mainnet:req=(name,(32.75,26),(41.135,45.15),0,0,pcbnew.B_Cu)
            elif name=='MUX_S0':req=(name,(21.945,47),(44.945,45.15),0,0,pcbnew.B_Cu)
            else:req=(name,(22.515,43.55),(46.115,43.55),1,1,pcbnew.B_Cu)
            requests.append(req)
    for t in removed:b.Remove(t)
    result={'mode':a.mode,'case':a.case,'baseline_pcb_sha256':BASE_SHA,
            'removed':[t.m_Uuid.AsString() for t in removed], 'paths':[],
            'accepted':False,'model_only':True,'routing_completed':False,'fabrication_release':False}
    def run(name,start,goal,sl,gl,layer,allow=True):
        net=next(p.GetNetCode() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()==name)
        layers=layer if isinstance(layer,tuple) else (pcbnew.F_Cu,layer)
        path=mesh_route(b,start,goal,net,layers,power,region,start_layer=sl,goal_layer=gl,allow_vias=allow)
        result['paths'].append({'net':name,'layers':[b.GetLayerName(l) for l in layers],'path':path})
        print(name,'found',path is not None,flush=True)
        if path:add_mesh_path(b,path,net,layers)
        return path
    ready=True
    if head:
        ready=bool(run(tgt,(44.25,7.6),head,0,0,other,False))
        if ready:
            net=next(p.GetNetCode() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()==tgt)
            make_via(b,head,net,.60)
    if ready:
        for req in requests:
            if not run(*req):break
    result['complete']=len(result['paths'])==len(requests)+(1 if head else 0) and all(r['path'] for r in result['paths'])
    if result['complete']:
        target=a.output_dir/a.board.name
        pcbnew.SaveBoard(str(target),b)
        for ext in ('.kicad_pro','.kicad_dru'):shutil.copy2(a.board.with_suffix(ext),target.with_suffix(ext))
        result['unqualified_pcb_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (a.output_dir/'plan.json').write_text(json.dumps(result,indent=2)+'\n')
    assert hashlib.sha256(a.board.read_bytes()).hexdigest()==BASE_SHA

if __name__=='__main__':main()

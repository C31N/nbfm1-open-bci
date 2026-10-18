#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Joint CH022 access and CH026 electrode copper restoration, fail-closed.

All trial boards are ephemeral. A model route is never a PCB acceptance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive,digest,ZIP_SHA
from probe_ch019_trunk_return import PCB,pads
from probe_ch026p_r302_restitution import local_via_window,FLAGS,R302,J223
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA

ROOT=Path(__file__).resolve().parent
PINNED={
    'long':'e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa',
    'diagonal':'9dd73183-097f-4e10-a5b8-8875dab1c044',
}

def trial(board_path: Path, report_path: Path, scope: str, layers_mode: str
          ) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point,LineString,box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles
    from analyze_139_escape_blockers import component
    from route_targeted_closure import xy,routing_domain,native_fresh
    from analyze_139_escape_blockers import protected_power
    from escape_mesh_505 import mesh_route,add_mesh_path,polygons
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import power_copper,outlines

    board=pcbnew.LoadBoard(str(board_path))
    baseline=pcbnew.LoadBoard(str(board_path))
    region=routing_domain(board,.30,.25).intersection(box(12,.5,59,69))
    power=protected_power(board)
    layers=(pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu)
    originals={t.m_Uuid.AsString():t for t in board.GetTracks()}
    selection=[PINNED['long']] if scope=='one' else list(PINNED.values())
    chosen=[originals[uid] for uid in selection]
    for t in chosen:
        if t.GetNetname()!='CH026_P_ELECTRODE' or t.GetLayer()!=pcbnew.F_Cu:
            raise ValueError('Incorrect CH026 electrode UUID/layer')
    a=(35.4508,16.0524) if scope=='pair' else (36.2984,16.9)
    b=(39.85,16.9)
    if xy(chosen[0].GetEnd())!=b or (scope=='one' and xy(chosen[0].GetStart())!=a):
        raise ValueError('Selected track endpoint shifted')
    ch022={name:(pt,code) for name,pt,code in pads(board,'CH022_N_ELECTRODE')}
    if set(ch022)!={'J2.23','R302.1'} or ch022['R302.1'][0]!=R302 or ch022['J2.23'][0]!=J223:
        raise ValueError('Protected CH022 geometry invalid')
    frozen={}
    for t in board.GetTracks():
        uid=t.m_Uuid.AsString()
        if t.GetNetname() in ('CH018_N_MUX','VCM') or (
            t.GetNetname()=='CH022_N_ELECTRODE' and
            LineString([xy(t.GetStart()),xy(t.GetEnd())]).distance(Point(J223))<.75):
            frozen[uid]=(t.GetNetname(),t.GetLayer(),xy(t.GetStart()),xy(t.GetEnd()))
    original_ch022_vias=[xy(t.GetPosition()) for t in board.GetTracks()
        if isinstance(t,pcbnew.PCB_VIA) and t.GetNetname()=='CH022_N_ELECTRODE']
    result: dict[str,Any]={**FLAGS,'status':'not_started','scope':scope,
       'layers_mode':layers_mode,'selected_UUIDs':selection,
       'J2_preserved_count':sum(x[0]=='CH022_N_ELECTRODE' for x in frozen.values()),
       'original_CH022_vias':original_ch022_vias}
    for t in chosen: board.Remove(t)
    try:
        legal=local_via_window(board,power,region)
        patches=polygons(legal)
        result['window_after_CH026_cut_mm2']=round(legal.area,8)
        if not patches:
            result['status']='no_via_window_after_selection'
            return result
        pt=max(patches,key=lambda x:x.area).representative_point()
        via=(round(pt.x,6),round(pt.y,6))
        result['planned_new_CH022_via']=via
        nc=ch022['R302.1'][1]
        trace=mesh_route(board,R302,via,nc,layers,power,region,
                         start_layer=0,goal_layer=0,allow_vias=False)
        if trace is None or len(trace)<2:
            result['status']='CH022_FCu_R302_to_new_via_blocked'
            return result
        add_mesh_path(board,trace,nc,layers)
        result['CH022_R302_FCu_escape_proposed']=True
        # New CH022 via is only placed at native-mapped legal via center
        # outside the strict full L3-power polygon buffer.
        add_mesh_path(board,[(0,*via),(1,*via)],nc,layers)
        result['new_via_proposed']=True
        # CH022_N_ELECTRODE has zero native vias in the pinned baseline:
        # introduce a SECOND legal via in the untouched J2.23 F.Cu
        # component, rather than assuming an existing return via.
        blocked, via_obstacle = obstacles(board,nc,.15,.15,region,.60,
                                          (pcbnew.F_Cu,pcbnew.B_Cu))
        fcu = component(region.difference(blocked[0]).buffer(-.000005),J223)
        jlegal = (fcu.difference(unary_union([via_obstacle,power.buffer(.505)]))
                  .intersection(Point(J223).buffer(3.5)).buffer(-.000005))
        result['J2_local_legal_via_mm2'] = round(jlegal.area,8)
        jpatches = [p for p in polygons(jlegal) if p.area>1e-8]
        if not jpatches:
            result['status']='J2_FCu_component_no_legal_second_via'
            return result
        jpoint=max(jpatches,key=lambda v:v.area).representative_point()
        jvia=(round(jpoint.x,6),round(jpoint.y,6))
        result['planned_J2_new_via']=jvia
        if Point(via).distance(Point(jvia))<=1.0:
            raise ValueError('Both via coordinates unexpectedly identical')
        jtrace=mesh_route(board,J223,jvia,nc,layers,power,region,
                          start_layer=0,goal_layer=0,allow_vias=False)
        if jtrace is None or len(jtrace)<2:
            result['status']='J2_to_second_FCu_via_blocked'
            return result
        add_mesh_path(board,jtrace,nc,layers)
        add_mesh_path(board,[(0,*jvia),(1,*jvia)],nc,layers)
        result['J2_FCu_to_new_via_proposed']=True
        bridge=mesh_route(board,via,jvia,nc,layers,power,region,
                          start_layer=1,goal_layer=1)
        if bridge is None or len(bridge)<2:
            result['status']='CH022_two_new_vias_BCu_bridge_blocked'
            return result
        add_mesh_path(board,bridge,nc,layers)
        result['CH022_connected_by_two_new_vias_proposed']=True
        result['CH022_BCu_path']=bridge
        code=chosen[0].GetNetCode()
        back=mesh_route(board,a,b,code,layers,power,region,
                        allow_vias=layers_mode=='3layer')
        if back is None or len(back)<2:
            result['status']='CH026_restitution_blocked_after_CH022_via'
            return result
        add_mesh_path(board,back,code,layers)
        result['CH026_restitution_path']=back
        now={t.m_Uuid.AsString():(t.GetNetname(),t.GetLayer(),
              xy(t.GetStart()),xy(t.GetEnd())) for t in board.GetTracks()
              if t.m_Uuid.AsString() in frozen}
        if now!=frozen: raise RuntimeError('J2/VCM/CH018 copper changed')
        pcbnew.SaveBoard(str(board_path),board)
        before=native_fresh(report_path.parent/'baseline'/PCB,
                            report_path.with_suffix('.before.json'))
        after=native_fresh(board_path,report_path.with_suffix('.after.json'))
        current=pcbnew.LoadBoard(str(board_path))
        p0,p1=power_copper(baseline),power_copper(current)
        result.update({
            'DRC_violations':len(after.get('violations',[])),
            'DRC_warning_count':sum(v.get('severity')=='warning' for v in after.get('violations',[])),
            'DRC_unconnected':len(after.get('unconnected_items',[])),
            'net_regressions':regressed_nets(before,after),
            'power_loss_mm2':p0.difference(p1).area,
            'power_gain_mm2':p1.difference(p0).area,
            'power_outline_unchanged':outlines(baseline)==outlines(current),
        })
        result['status']='native_audit_unaccepted'
        return result
    finally:
        for t in chosen: board.Add(t)

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--scope',choices=('one','pair'),required=True)
    ap.add_argument('--layers',choices=('FCu','3layer'),required=True)
    args=ap.parse_args()
    if args.output.exists() or args.output.suffix!='.json' or args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Report must be a fresh external JSON')
    contents=frozen_archive(args.archive)
    if digest(contents[PCB])!=FROZEN_INPUT_SHA:
        raise ValueError('Input PCB mismatch')
    with tempfile.TemporaryDirectory(prefix='ch026-and-ch022-joint-') as td:
        d=Path(td)
        for name,content in contents.items(): (d/name).write_bytes(content)
        (d/'baseline').mkdir()
        for name,content in contents.items(): (d/'baseline'/name).write_bytes(content)
        try:
            r=trial(d/PCB,d/'joint.json',args.scope,args.layers)
        except Exception as exc:
            r={**FLAGS,'status':'diagnostic_exception','error_type':type(exc).__name__,
               'reason':str(exc),'scope':args.scope,'layers_mode':args.layers}
    if digest(args.archive.read_bytes())!=ZIP_SHA: raise ValueError('Archive changed')
    args.output.write_text(json.dumps(r,indent=2)+'\n')
    print(args.scope,args.layers,r['status'],flush=True)

if __name__=='__main__':
    main()

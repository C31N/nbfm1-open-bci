#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Joint three-net Block 2 closure attempt with CH026 electrode unlock.

Fail closed, pinned KiCad board, no release, no manufacturing outputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive,digest,ZIP_SHA
from probe_ch019_trunk_return import PCB,pads,protected_selection
from probe_block2_r302_joint import CASES
from probe_ch019_existing_via_bridge import VIA_ENDS
from probe_ch026p_r302_restitution import local_via_window,FLAGS,R302,J223
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA
from probe_ch026_ch022_joint import PINNED

ROOT=Path(__file__).resolve().parent

def model(board_file: Path, report_file: Path, order: str,
          scope: str) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point,LineString,box
    from shapely.ops import unary_union
    from route_targeted_closure import xy,obstacles,routing_domain,native_fresh
    from analyze_139_escape_blockers import protected_power,component
    from escape_mesh_505 import mesh_route,add_mesh_path,polygons
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import power_copper,outlines

    board=pcbnew.LoadBoard(str(board_file))
    unchanged=pcbnew.LoadBoard(str(board_file))
    region=routing_domain(board,.30,.25).intersection(box(12,.5,59,69))
    power=protected_power(board)
    layers=(pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu)
    old_tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    chosen=protected_selection(board,'entire_trunk')
    for name,uuids in CASES['exact-eleven-conflicts'].items():
        for uid in uuids:
            t=old_tracks[uid]
            lay=pcbnew.B_Cu if name in ('CH019_N_MUX','BANK1_P_MUX_OUT') else pcbnew.F_Cu
            if t.GetNetname()!=name or t.GetLayer()!=lay:
                raise ValueError('Unexpected other-neighbor geometry: '+uid)
            chosen.append(t)
    chosen.append(old_tracks[PINNED['long']])
    if scope=='pair':
        chosen.append(old_tracks[PINNED['diagonal']])
    if len(chosen)!=len({t.m_Uuid.AsString() for t in chosen}):
        raise ValueError('Duplicate selected track')
    if any(t.GetNetname() in ('CH018_N_MUX','VCM') for t in chosen):
        raise ValueError('Protected analog net in removal set')
    # Original J2, VCM and CH018 copper preserved exactly.
    freeze={}
    for t in board.GetTracks():
        uid=t.m_Uuid.AsString()
        if t.GetNetname() in ('CH018_N_MUX','VCM') or (
            t.GetNetname()=='CH022_N_ELECTRODE' and
            LineString([xy(t.GetStart()),xy(t.GetEnd())]).distance(Point(J223))<.75):
            freeze[uid]=(t.GetNetname(),t.GetLayer(),xy(t.GetStart()),xy(t.GetEnd()))
    if any(t.m_Uuid.AsString() in freeze for t in chosen):
        raise ValueError('Would disturb protected J2.23 or analog copper')
    result:dict[str,Any]={**FLAGS,'status':'not_started','order':order,
       'scope':scope,'removed_UUIDs':[t.m_Uuid.AsString() for t in chosen],
       'J2_preserved_count':sum(z[0]=='CH022_N_ELECTRODE' for z in freeze.values())}
    for t in chosen: board.Remove(t)
    try:
        def route(net:str,a:tuple[float,float],b:tuple[float,float],
                  sl:int=0,gl:int=0,only_same_layer:bool=False) -> bool:
            code=next(x[2] for x in pads(board,net))
            path=mesh_route(board,a,b,code,layers,power,region,
               start_layer=sl,goal_layer=gl,allow_vias=not only_same_layer)
            if path is None or len(path)<2: return False
            add_mesh_path(board,path,code,layers)
            return True
        def do_ch022() -> bool:
            electrodes={name:(pt,code) for name,pt,code in pads(board,'CH022_N_ELECTRODE')}
            if set(electrodes)!={'J2.23','R302.1'} or electrodes['J2.23'][0]!=J223:
                raise ValueError('J2/CH022 identity mismatch')
            rlegal=local_via_window(board,power,region)
            patches=[g for g in polygons(rlegal) if g.area>1e-8]
            result['R302_local_via_window_mm2']=round(rlegal.area,8)
            if not patches:
                result['status']='R302_window_absent_after_all_neighbor_cuts'
                return False
            rv=patches[0].representative_point()
            rvia=(round(rv.x,6),round(rv.y,6))
            result['R302_via']=rvia
            if not route('CH022_N_ELECTRODE',R302,rvia,0,0,True):
                result['status']='CH022_R302_FCu_still_blocked';return False
            code=electrodes['R302.1'][1]
            add_mesh_path(board,[(0,*rvia),(1,*rvia)],code,layers)

            ob,viaob=obstacles(board,code,.15,.15,region,.60,(pcbnew.F_Cu,pcbnew.B_Cu))
            jcomponent=component(region.difference(ob[0]).buffer(-.000005),J223)
            jlegal=(jcomponent.difference(unary_union([viaob,power.buffer(.505)]))
                .intersection(Point(J223).buffer(3.5)).buffer(-.000005))
            result['J2_local_via_window_mm2']=round(jlegal.area,8)
            jpatch=[g for g in polygons(jlegal) if g.area>1e-8]
            if not jpatch:
                result['status']='J2_second_via_window_blocked';return False
            jpt=max(jpatch,key=lambda q:q.area).representative_point()
            jvia=(round(jpt.x,6),round(jpt.y,6))
            result['J2_via']=jvia
            if not route('CH022_N_ELECTRODE',J223,jvia,0,0,True):
                result['status']='CH022_J2_FCu_via_approach_blocked';return False
            # Landing is F.Cu-connected to J2; no redundant J2 through via.
            # The prior extra via gave a native via_dangling warning.
            if not route('CH022_N_ELECTRODE',rvia,jvia,1,0):
                result['status']='CH022_BCu_two_via_bridge_blocked';return False
            result['CH022_geometrically_closed']=True
            return True
        def do_ch024_ch019() -> bool:
            ch024={n:x for n,x,_ in pads(board,'CH024_P_MUX')}
            if set(ch024)!={'R49.1','R305.2','U3.23'}:
                raise ValueError('Three-pad CH024 net changed')
            # Route U3.23 first, as in the native-qualified diagnostic
            # full CH024-P three-pad proposal; add 0.5-mm R305 branch later.
            if not route('CH024_P_MUX',ch024['R49.1'],ch024['U3.23']):
                result['status']='CH024_U3_23_trunk_blocked';return False
            if not route('CH024_P_MUX',ch024['R49.1'],ch024['R305.2']):
                result['status']='CH024_half_mm_branch_blocked';return False
            result['CH024_three_pad_geometry_proposed']=True
            va,vb=VIA_ENDS['direct']
            if not route('CH019_P_MUX',va,vb,1,1):
                result['status']='CH019_existing_BCu_bridge_blocked';return False
            result['CH019_existing_via_bridge_proposed']=True
            return True
        ordered=(do_ch022,do_ch024_ch019) if order=='ch022-first' else (do_ch024_ch019,do_ch022)
        for fn in ordered:
            if not fn():return result

        # First restore CH026 P_ELECTRODE with the two new CH022 vias
        # physically blocking the former straight segment.
        start=(35.4508,16.0524) if scope=='pair' else (36.2984,16.9)
        target=(39.85,16.9)
        if not route('CH026_P_ELECTRODE',start,target):
            result['status']='CH026_neighbor_restitution_blocked';return result
        result['CH026_neighbor_geometry_restored']=True

        for t in chosen:
            if t.GetNetname() in ('CH022_N_ELECTRODE','CH019_P_MUX',
                                  'CH026_P_ELECTRODE'):
                continue
            a,b=xy(t.GetStart()),xy(t.GetEnd())
            if not route(t.GetNetname(),a,b,
                         layers.index(t.GetLayer()),layers.index(t.GetLayer())):
                result['status']='other_neighbor_restitution_blocked'
                result['failed_neighbor']=t.GetNetname()
                result['failed_UUID']=t.m_Uuid.AsString()
                return result
        result['all_removed_neighbor_endpoints_reconnected']=True
        present={t.m_Uuid.AsString():(t.GetNetname(),t.GetLayer(),
                 xy(t.GetStart()),xy(t.GetEnd())) for t in board.GetTracks()
                 if t.m_Uuid.AsString() in freeze}
        if freeze!=present:
            raise RuntimeError('Protected J2/VCM/CH018 copper regression')
        pcbnew.SaveBoard(str(board_file),board)
        a=native_fresh(report_file.parent/'baseline'/PCB,
                       report_file.with_suffix('.before.json'))
        b=native_fresh(board_file,report_file.with_suffix('.after.json'))
        obs=pcbnew.LoadBoard(str(board_file))
        p0,p1=power_copper(unchanged),power_copper(obs)
        result.update({
            'DRC_violations':b.get('violations',[]),
            'DRC_unconnected':len(b.get('unconnected_items',[])),
            'DRC_target_unconnected': [
                x for x in b.get('unconnected_items',[])
                if any(n in str(x) for n in ('CH022_N_ELECTRODE','CH024_P_MUX',
                                             'CH019_P_MUX','CH026_P_ELECTRODE'))],
            'net_regressions':regressed_nets(a,b),
            'L3_power_loss_mm2':p0.difference(p1).area,
            'L3_power_gain_mm2':p1.difference(p0).area,
            'power_outlines_unchanged':outlines(unchanged)==outlines(obs),
            'status':'native_audit_only_unaccepted'})
        return result
    finally:
        for t in chosen: board.Add(t)

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--scope',choices=('one','pair'),required=True)
    ap.add_argument('--order',choices=('ch022-first','ch024-first'),required=True)
    args=ap.parse_args()
    if args.output.exists() or args.output.suffix!='.json' or args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Fresh external JSON required')
    fixture=frozen_archive(args.archive)
    if digest(fixture[PCB])!=FROZEN_INPUT_SHA:
        raise ValueError('Pinned PCB SHA mismatch')
    with tempfile.TemporaryDirectory(prefix='block2-three-net-R302-') as td:
        work=Path(td)
        for name,bytes_ in fixture.items(): (work/name).write_bytes(bytes_)
        (work/'baseline').mkdir()
        for name,bytes_ in fixture.items(): (work/'baseline'/name).write_bytes(bytes_)
        try:r=model(work/PCB,work/'joint.json',args.order,args.scope)
        except Exception as exc:r={**FLAGS,'status':'diagnostic_exception',
            'error_type':type(exc).__name__,'detail':str(exc)}
    if digest(args.archive.read_bytes())!=ZIP_SHA:
        raise ValueError('Reference archive altered')
    args.output.write_text(json.dumps(r,indent=2)+'\n')
    print(args.order,args.scope,r['status'],flush=True)

if __name__=='__main__':
    main()

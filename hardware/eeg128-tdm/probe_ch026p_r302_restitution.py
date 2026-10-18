#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Selectively re-route a single CH026-P electrode segment, preserve R302 via.

Temporary KiCad-8 models only; all acceptance and fabrication flags remain false.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_ch019_trunk_return import PCB, pads
from probe_block2_selective import ZIP_SHA, frozen_archive, digest
from analyze_ch019_bcu_blockers import FROZEN_INPUT_SHA

SOURCE=Path(__file__).resolve().parent
UUID='e3c4e6fe-fce1-48bf-a3e0-bef9b53a8faa'
R302=(36.15,15.6)
J223=(43.75,7.6)
FLAGS={'model_only': True, 'accepted': False,
       'routing_completed': False,'fabrication_release': False,
       'native_qualification': False,
       'independent_replay_verified': False,'manufacturing_files': False}


def local_via_window(board: Any, power: Any, region: Any) -> Any:
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles
    from analyze_139_escape_blockers import component
    pad = {name:(pt,code) for name,pt,code in pads(board,'CH022_N_ELECTRODE')}
    if pad['R302.1'][0] != R302:
        raise ValueError('R302.1 moved')
    blocked, via=obstacles(board,pad['R302.1'][1],.15,.15,region,.60,
                           (pcbnew.F_Cu,pcbnew.B_Cu))
    comp=component(region.difference(blocked[0]).buffer(-.000005),R302)
    return (comp.difference(unary_union([via,power.buffer(.505)]))
            .intersection(Point(R302).buffer(3.5)).buffer(-.000005))


def trial(board_path: Path, diag_path: Path, layers_choice: str,
          clearance_radius: float) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point,LineString,box
    from analyze_139_escape_blockers import protected_power
    from route_targeted_closure import xy,routing_domain,native_fresh
    from escape_mesh_505 import mesh_route,add_mesh_path,polygons
    from native_connectivity import regressed_nets
    from audit_block1_corridor_geometry import power_copper,outlines

    board=pcbnew.LoadBoard(str(board_path))
    baseline=pcbnew.LoadBoard(str(board_path))
    power=protected_power(board)
    region=routing_domain(board,.30,.25).intersection(box(12,.5,59,69))
    before_area=local_via_window(board,power,region).area
    net_pads={name:pt for name,pt,_ in pads(board,'CH022_N_ELECTRODE')}
    if net_pads != {'J2.23':J223,'R302.1':R302}:
        raise ValueError('CH022 pad identity mismatch')
    protected={}
    for t in board.GetTracks():
        uid=t.m_Uuid.AsString()
        if t.GetNetname() in ('CH018_N_MUX','VCM') or (
            t.GetNetname()=='CH022_N_ELECTRODE' and
            LineString([xy(t.GetStart()),xy(t.GetEnd())]).distance(Point(J223))<.75):
            protected[uid]=(t.GetNetname(),t.GetLayer(),xy(t.GetStart()),xy(t.GetEnd()))
    ref=next((t for t in board.GetTracks() if t.m_Uuid.AsString()==UUID),None)
    if ref is None or ref.GetNetname()!='CH026_P_ELECTRODE' or ref.GetLayer()!=pcbnew.F_Cu:
        raise ValueError('Wrong CH026-P source UUID/net/layer')
    a=xy(ref.GetStart());b=xy(ref.GetEnd());net=ref.GetNetCode()
    baseline_count=len(list(board.GetTracks()))
    result={**FLAGS,'scope':'CH026_P_ELECTRODE_R302_SELECTIVE',
            'candidate_uuid':UUID,'layers_choice':layers_choice,
            'radius':clearance_radius,'baseline_via_area_mm2':round(before_area,8),
            'status':'not_started','source_endpoints':[a,b]}
    board.Remove(ref)
    try:
        win=local_via_window(board,power,region)
        result['unblocked_via_area_mm2']=round(win.area,8)
        ps=polygons(win)
        if not ps:
            result['status']='window_not_open'
            return result
        candidate=max(ps,key=lambda x:x.area).representative_point()
        target=(round(candidate.x,6),round(candidate.y,6))
        result['reserved_R302_via_xy']=target
        layers=(pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu)
        keepouts=[Point(target).buffer(clearance_radius),
                  Point(0,0).buffer(0),
                  Point(0,0).buffer(0)]
        # Even when three layers are allowed, new In2 and vias respect full
        # L3 outline buffer .505 and board-edge margin .25 inside mesh_route.
        path=mesh_route(board,a,b,net,layers,power,region,
                        allow_vias=layers_choice=='3layer',
                        extra_obstacles=keepouts)
        if path is None:
            result['status']='CH026_P_ELECTRODE_alternate_route_blocked'
            return result
        if len(path)<2:
            result['status']='degenerate_CH026_route'
            return result
        add_mesh_path(board,path,net,layers)
        result['restituted_route']=path
        result['CH026_P_ELECTRODE_geometry_restituted']=True
        final_win=local_via_window(board,power,region)
        result['legal_via_after_restitution_mm2']=round(final_win.area,8)
        result['reserved_center_legal']=final_win.covers(Point(target))
        current={t.m_Uuid.AsString():
                 (t.GetNetname(),t.GetLayer(),xy(t.GetStart()),xy(t.GetEnd()))
                 for t in board.GetTracks() if t.m_Uuid.AsString() in protected}
        if protected!=current:
            raise RuntimeError('Protected J2/CH018/VCM copper changed')
        if not result['reserved_center_legal']:
            result['status']='new_CH026_route_reblocks_via'
            return result
        pcbnew.SaveBoard(str(board_path),board)
        pre=native_fresh(diag_path.parent/'baseline'/PCB,diag_path.with_suffix('.before.json'))
        after=native_fresh(board_path,diag_path.with_suffix('.after.json'))
        observed=pcbnew.LoadBoard(str(board_path))
        p0,p1=power_copper(baseline),power_copper(observed)
        result['DRC_violation_count']=len(after.get('violations',[]))
        result['DRC_warning_count']=sum(z.get('severity')=='warning' for z in after.get('violations',[]))
        result['DRC_unconnected_count']=len(after.get('unconnected_items',[]))
        result['net_regressions']=regressed_nets(pre,after)
        result['power_loss_mm2']=p0.difference(p1).area
        result['power_gain_mm2']=p1.difference(p0).area
        result['zone_outlines_unchanged']=outlines(baseline)==outlines(observed)
        result['baseline_tracks']=baseline_count
        result['status']='native_audited_not_adopted'
        return result
    finally:
        board.Add(ref)


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layers',choices=('FCu','3layer'),required=True)
    p.add_argument('--radius',type=float,choices=(.55,.70),required=True)
    args=p.parse_args()
    if args.output.exists() or args.output.suffix!='.json':
        raise ValueError('Unique JSON output required')
    if args.output.resolve().is_relative_to(SOURCE):
        raise ValueError('Never output to source tree')
    data=frozen_archive(args.archive)
    if digest(data[PCB])!=FROZEN_INPUT_SHA:
        raise ValueError('Pinned baseline differs')
    with tempfile.TemporaryDirectory(prefix='ch026-p-restitution-') as td:
        work=Path(td)
        for name,content in data.items():
            (work/name).write_bytes(content)
        (work/'baseline').mkdir()
        for name,content in data.items():
            (work/'baseline'/name).write_bytes(content)
        try:
            output=trial(work/PCB,work/'result.json',args.layers,args.radius)
        except Exception as exc:
            output={**FLAGS,'status':'diagnostic_exception','reason':str(exc),
                    'error_type':type(exc).__name__,'layers':args.layers,'radius':args.radius}
    if digest(args.archive.read_bytes())!=ZIP_SHA:
        raise ValueError('Source zip changed')
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(output['status'],flush=True)


if __name__=='__main__':
    main()

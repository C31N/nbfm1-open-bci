#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only native inventory of CH026_P_ELECTRODE obstacles near R302.1.

Does not remove copper. All results are model-only and fail closed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from probe_block2_selective import frozen_archive, digest, PCB, PCB_SHA
from probe_ch019_trunk_return import pads
from analyze_139_escape_blockers import protected_power, windows
from route_targeted_closure import xy

FLAGS = {'model_only': True, 'accepted': False, 'routing_completed': False,
         'fabrication_release': False, 'manufacturing_exports': False}


def inspect(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point, LineString, box
    from shapely.ops import unary_union
    center = (36.15, 15.60)
    region = box(29, 8, 44, 23)
    protected = protected_power(board)
    target = [p for p in pads(board, 'CH022_N_ELECTRODE') if p[0]=='R302.1']
    if len(target)!=1 or tuple(target[0][1]) != center:
        raise ValueError('R302.1 moved; abort')
    netcode=target[0][2]
    def measure() -> dict[str, Any]:
        comp, metrics=windows(board,netcode,center,region,protected)
        from route_targeted_closure import obstacles
        _, blocked=obstacles(board,netcode,.15,.15,region,.60,(pcbnew.F_Cu,pcbnew.B_Cu))
        local=comp.difference(unary_union([blocked,protected.buffer(.505)])).intersection(Point(center).buffer(3.5))
        return {'via_area_3p5_mm2':round(local.area,8),'connected_FCu_area_mm2':round(comp.area,8)}
    original=measure()
    candidates=[]
    for t in list(board.GetTracks()):
        if t.GetNetname()!='CH026_P_ELECTRODE' or t.GetLayer()!=pcbnew.F_Cu or isinstance(t,(pcbnew.PCB_VIA,pcbnew.PCB_ARC)):
            continue
        line=LineString([xy(t.GetStart()),xy(t.GetEnd())])
        d=line.distance(Point(center))
        if d>4.0:continue
        uid=t.m_Uuid.AsString()
        # Protected existing via and pad contacts are never selected.
        netpads=[Point(p[1]) for p in pads(board,'CH026_P_ELECTRODE')]
        vias=[Point(xy(v.GetPosition())) for v in board.GetTracks() if isinstance(v,pcbnew.PCB_VIA) and v.GetNetname()=='CH026_P_ELECTRODE']
        guarded=any(line.distance(p)<1.0 for p in netpads) or any(line.distance(v)<.65 for v in vias)
        trial={'uuid':uid,'distance_R302_mm':round(d,6),'start':xy(t.GetStart()),
               'end':xy(t.GetEnd()),'protected_pad_or_via':guarded}
        if not guarded:
            board.Remove(t)
            try: trial['hypothetical_after_removal']=measure()
            finally: board.Add(t)
        candidates.append(trial)
    candidates.sort(key=lambda c:(c['protected_pad_or_via'],c['distance_R302_mm'],c['uuid']))
    return {**FLAGS,'source_pcb_sha256':PCB_SHA,'pad':'R302.1',
            'original':original,'CH026_P_ELECTRODE_segments':candidates,
            'note':'Single-segment removal is a diagnostic only; CH026_P restitution is not proven.'}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.suffix!='.json':
        raise ValueError('Fresh JSON output required')
    archive=frozen_archive(args.archive)
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='ch026-r302-readonly-') as td:
        path=Path(td)/PCB
        path.write_bytes(archive[PCB])
        board=pcbnew.LoadBoard(str(path))
        report=inspect(board)
        if digest(path.read_bytes())!=PCB_SHA:
            raise ValueError('Original PCB mutated')
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('CH026 near R302: ',len(report['CH026_P_ELECTRODE_segments']),flush=True)


if __name__=='__main__':
    main()

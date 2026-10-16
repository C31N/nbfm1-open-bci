#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only single-neighbor removal models; no candidate PCB or release promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from shapely.geometry.base import BaseGeometry

import pcbnew
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union
from route_targeted_closure import obstacles, xy, Point2

BASE_SHA = 'f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea'

def protected_power(board: pcbnew.BOARD) -> BaseGeometry:
    # Reserve complete L3 zone outlines, including existing fill voids. A via
    # must not exploit a pre-existing hole as permission to enter the plane.
    shapes=[]
    for z in board.Zones():
        if not z.IsOnLayer(pcbnew.In2_Cu): continue
        poly=z.Outline()
        for i in range(poly.OutlineCount()):
            c=poly.Outline(i)
            shapes.append(Polygon([xy(c.CPoint(j)) for j in range(c.PointCount())]))
    return unary_union(shapes)

def component(free: BaseGeometry, point: Point2) -> BaseGeometry:
    parts = list(free.geoms) if hasattr(free, 'geoms') else [free]
    return next((g for g in parts if g.distance(Point(point)) < 1e-7), Point(point).buffer(0))

def windows(board: pcbnew.BOARD, net: int, point: Point2, region: BaseGeometry,
            power: BaseGeometry) -> tuple[BaseGeometry, dict[str, Any]]:
    shapes, via = obstacles(board, net, .15, .15, region, .60,
                            (pcbnew.F_Cu, pcbnew.B_Cu))
    comp = component(region.difference(shapes[0]), point)
    legal = comp.difference(via.union(power.buffer(.505)))
    parts = list(legal.geoms) if hasattr(legal, 'geoms') else [legal]
    return comp, {'bounds': list(comp.bounds), 'component_area_mm2': comp.area,
                 'legal_via_area_mm2': legal.area,
                 'windows': [{'point': list(g.representative_point().coords[0]), 'area_mm2':g.area}
                             for g in sorted(parts, key=lambda g:-g.area) if g.area > 1e-8]}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    assert hashlib.sha256(a.board.read_bytes()).hexdigest()==BASE_SHA
    b=pcbnew.LoadBoard(str(a.board)); power=protected_power(b)
    tasks=[('CH018P-target','CH018_P_MUX',(41.135,45.15),box(14,18,54,65)),
           ('CH021-source','CH021_N_ELECTRODE',(36.15,18.2),box(29,12,46,24)),
           ('CH021-target','CH021_N_ELECTRODE',(43.25,7.6),box(33,.5,51,16))]
    result={'baseline_pcb_sha256':BASE_SHA,'model_only':True,'accepted':False,
            'routing_completed':False,'fabrication_release':False,'results':{}}
    for label,name,pt,region in tasks:
        net=next(p.GetNetCode() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()==name)
        comp,initial=windows(b,net,pt,region,power)
        neighbors={}
        for t in b.GetTracks():
            if t.GetNetCode()==net: continue
            if not isinstance(t,pcbnew.PCB_VIA) and t.GetLayer()!=pcbnew.F_Cu: continue
            shape=(Point(xy(t.GetPosition())) if isinstance(t,pcbnew.PCB_VIA) else LineString([xy(t.GetStart()),xy(t.GetEnd())]))
            distance=shape.distance(comp)-pcbnew.ToMM(t.GetWidth())/2
            if distance < .55:
                neighbors.setdefault(t.GetNetname(),[]).append({'uuid':t.m_Uuid.AsString(),
                    'layer':b.GetLayerName(t.GetLayer()),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),
                    'distance_to_component_mm':distance})
        trials=[]
        for neighbor in sorted(neighbors):
            removed=[t for t in b.GetTracks() if t.GetNetname()==neighbor]
            for t in removed:b.Remove(t)
            _,after=windows(b,net,pt,region,power)
            for t in removed:b.Add(t)
            event={'removed_net':neighbor,'removed_copper_objects':len(removed),**after,
                   'accepted':False,'requires_complete_neighbor_replacement':True}
            trials.append(event)
            print(label,neighbor,after['legal_via_area_mm2'],flush=True)
        result['results'][label]={'net':name,'anchor':pt,'window':list(region.bounds),
                                'baseline':initial,'neighbor_copper':neighbors,'single_net_removal_models':trials}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    assert hashlib.sha256(a.board.read_bytes()).hexdigest()==BASE_SHA

if __name__=='__main__':main()

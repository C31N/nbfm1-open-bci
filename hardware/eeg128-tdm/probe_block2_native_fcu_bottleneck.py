#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only KiCad 8/9 F.Cu bottleneck measurement.

Native pcbnew.SHAPE_POLY_SET is the source for pad/track/via/filled-zone
polygon vertices. Shapely provides segment-to-segment nearest points.
Any failed native polygonization is recorded, never silently called exact.
The method tests LOCAL copper gaps, not global three-net routability.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any

from shapely.geometry import Polygon, box
from shapely.ops import nearest_points, unary_union

TRACK_MM=.150
CLEARANCE_MM=.150
HOTSPOT=(48.145,35.750)


@dataclass(frozen=True)
class NativeObject:
    uid:str
    kind:str
    name:str
    net:str
    geometry:Any
    polygonization:str

    def describe(self)->dict[str,Any]:
        return {
            "uuid":self.uid,"kind":self.kind,"name":self.name,
            "net":self.net,"polygonization":self.polygonization,
            "bbox_mm":[round(v,6) for v in self.geometry.bounds],
        }


def _chain_xy(chain:Any,pcbnew:Any)->list[tuple[float,float]]:
    return [
        (pcbnew.ToMM(chain.CPoint(i).x),
         pcbnew.ToMM(chain.CPoint(i).y))
        for i in range(chain.PointCount())
    ]


def _shapely_native_polygons(poly:Any,pcbnew:Any)->Any:
    polygons=[]
    for idx in range(poly.OutlineCount()):
        outer=_chain_xy(poly.Outline(idx),pcbnew)
        holes=[]
        if hasattr(poly,"HoleCount") and hasattr(poly,"Hole"):
            for j in range(poly.HoleCount(idx)):
                holes.append(_chain_xy(poly.Hole(idx,j),pcbnew))
        if len(outer)<3:
            raise ValueError("Native polygon has fewer than 3 points")
        geom=Polygon(outer,holes)
        if geom.is_empty or not geom.is_valid or geom.area<=0:
            raise ValueError("Native SHAPE_POLY_SET invalid")
        polygons.append(geom)
    if not polygons:
        raise ValueError("No native F.Cu polygon outlines")
    return unary_union(polygons)


def _native_shape(item:Any,kind:str,pcbnew:Any)->tuple[Any,str]:
    native=pcbnew.SHAPE_POLY_SET()
    if kind=="ZONE":
        # A zone outline is NOT its copper fill. Only use real filled
        # F.Cu polygons or mark this source unqualified.
        filled=item.GetFilledPolysList(pcbnew.F_Cu)
        if filled is None or filled.OutlineCount()==0:
            raise RuntimeError("F.Cu zone lacks native filled polys")
        native=pcbnew.SHAPE_POLY_SET(filled)
    elif kind=="PAD":
        item.TransformShapeToPolygon(
            native,pcbnew.F_Cu,0,pcbnew.FromMM(.0001))
    else:
        # KiCad 8/9 tracks, vias and arcs require the five-argument
        # BOARD_ITEM polygon transform. The SWIG SHAPE returned by
        # GetEffectiveShape does not expose ConvertToPolygon on KiCad 8.
        item.TransformShapeToPolygon(
            native,pcbnew.F_Cu,0,pcbnew.FromMM(.0001),
            pcbnew.ERROR_INSIDE)
    return _shapely_native_polygons(native,pcbnew),"SHAPE_POLY_SET_native_0.0001mm"


def _copper(item:Any,kind:str,pcbnew:Any)->tuple[Any,str]:
    try:
        return _native_shape(item,kind,pcbnew)
    except (RuntimeError,TypeError,ValueError,AttributeError,
            NotImplementedError) as error:
        from shapely.geometry import LineString, Point
        # When the KiCad 8 SWIG conversion overload is unavailable, use
        # the real native physical segment / via centre and width rather
        # than a false, overlapping bounding box. A circular buffer with
        # 64 segments/quadrant is a measurable approximation and CANNOT
        # authorize native geometric feasibility or fabrication.
        if kind in ("TRACK","VIA"):
            radius=pcbnew.ToMM(item.GetWidth())/2.
            xy=lambda pt:(pcbnew.ToMM(pt.x),pcbnew.ToMM(pt.y))
            base=(Point(xy(item.GetPosition()))
                  if kind=="VIA"
                  else LineString((xy(item.GetStart()),xy(item.GetEnd()))))
            geometry=base.buffer(radius,quad_segs=64)
            return geometry,(
                "native_segment_circle_analytic_approximation:"+
                type(error).__name__)
        bb=item.GetBoundingBox()
        geom=box(pcbnew.ToMM(bb.GetX()),pcbnew.ToMM(bb.GetY()),
                 pcbnew.ToMM(bb.GetRight()),pcbnew.ToMM(bb.GetBottom()))
        return geom,"conservative_bbox_fallback:"+type(error).__name__


def collect(board:Any,center:tuple[float,float],window:float,
            pcbnew:Any)->tuple[list[NativeObject],list[dict[str,Any]]]:
    roi=box(center[0]-window,center[1]-window,
            center[0]+window,center[1]+window)
    items=[]
    warnings=[]
    def add(item:Any,kind:str,name:str)->None:
        bb=item.GetBoundingBox()
        bounds=box(pcbnew.ToMM(bb.GetX()),pcbnew.ToMM(bb.GetY()),
                   pcbnew.ToMM(bb.GetRight()),pcbnew.ToMM(bb.GetBottom()))
        if not roi.intersects(bounds):
            return
        shape,grade=_copper(item,kind,pcbnew)
        if not shape.intersects(roi):
            return
        uid=item.m_Uuid.AsString()
        net=item.GetNetname() or ""
        items.append(NativeObject(uid,kind,name,net,shape,grade))
        if grade!="SHAPE_POLY_SET_native_0.0001mm":
            warnings.append({"uuid":uid,"kind":kind,"why":grade})
    for foot in board.GetFootprints():
        for pad in foot.Pads():
            if pad.IsOnLayer(pcbnew.F_Cu):
                add(pad,"PAD",foot.GetReference()+"/"+pad.GetNumber())
    for track in board.GetTracks():
        if isinstance(track,pcbnew.PCB_VIA):
            if track.IsOnLayer(pcbnew.F_Cu):
                add(track,"VIA","VIA")
        elif track.GetLayer()==pcbnew.F_Cu:
            add(track,"ARC" if isinstance(track,pcbnew.PCB_ARC)
                else "TRACK","TRACK")
    for zone in board.Zones():
        if zone.IsOnLayer(pcbnew.F_Cu):
            add(zone,"ZONE","F.Cu_ZONE")
    return sorted(items,key=lambda x:(x.kind,x.uid)),warnings


def gap_capacity(gap:float,track:float=TRACK_MM,
                 clearance:float=CLEARANCE_MM)->dict[str,int]:
    if gap<0 or track<=0 or clearance<0:
        raise ValueError("Invalid copper gap/DRC parameters")
    if not math.isfinite(gap):
        raise ValueError("Nonfinite copper gap")
    # n tracks with both wall clearances:
    # n*track+(n+1)*clearance <= gap
    strict=max(0,math.floor(
        (gap-clearance+1e-9)/(track+clearance)))
    optimistic=max(0,math.floor(
        (gap+1e-9)/(track+clearance)))
    return {"max_tracks_strict":strict,
            "max_tracks_edge_to_edge":optimistic}


def measure(objects:list[NativeObject],*,
            track:float=TRACK_MM,clearance:float=CLEARANCE_MM,
            max_gap:float=3.)->list[dict[str,Any]]:
    results=[]
    for i,left in enumerate(objects):
        for right in objects[i+1:]:
            # Same-net polygons often overlap legitimately; these
            # are not usable net-separating choke points.
            if left.net==right.net:
                continue
            if left.geometry.distance(right.geometry)>max_gap:
                continue
            p,q=nearest_points(left.geometry,right.geometry)
            gap=float(p.distance(q))
            count=gap_capacity(gap,track,clearance)
            results.append({
                "uuid_a":left.uid,"uuid_b":right.uid,
                "kind_a":left.kind,"kind_b":right.kind,
                "name_a":left.name,"name_b":right.name,
                "net_a":left.net,"net_b":right.net,
                "clear_gap_mm":round(gap,6),
                **count,
                "closest_pt_a_mm":(round(p.x,6),round(p.y,6)),
                "closest_pt_b_mm":(round(q.x,6),round(q.y,6)),
                "both_native_polygonized":(
                    left.polygonization==
                    "SHAPE_POLY_SET_native_0.0001mm" and
                    right.polygonization==
                    "SHAPE_POLY_SET_native_0.0001mm"),
            })
    return sorted(results,key=lambda x:(
        x["clear_gap_mm"],x["uuid_a"],x["uuid_b"]))


def analyze(board_path:Path,*,x:float=HOTSPOT[0],
            y:float=HOTSPOT[1],window:float=2.5,
            track:float=TRACK_MM,clearance:float=CLEARANCE_MM,
            max_gap:float=3.)->dict[str,Any]:
    import pcbnew
    if not pcbnew.Version().startswith(("8.","9.")):
        raise RuntimeError("Only native KiCad 8/9 supported")
    if not .5<=window<=12.0 or not .05<=track<=.4 or not .10<=clearance<=.35:
        raise ValueError("Unreviewed probe bounds or DRC values")
    checksum=hashlib.sha256(board_path.read_bytes()).hexdigest()
    board=pcbnew.LoadBoard(str(board_path))
    obstacles,warnings=collect(board,(x,y),window,pcbnew)
    gaps=measure(obstacles,track=track,clearance=clearance,max_gap=max_gap)
    verified=[g for g in gaps if g["both_native_polygonized"]]
    widest_verified=max((g["clear_gap_mm"] for g in verified),default=None)
    tightest=min((g["clear_gap_mm"] for g in gaps),default=None)
    tightest_native=min(
        (g["clear_gap_mm"] for g in verified),default=None)
    if hashlib.sha256(board_path.read_bytes()).hexdigest()!=checksum:
        raise RuntimeError("Read-only PCB source bytes changed")
    result={
        "status":("native_local_polygon_gaps_measured"
                  if not warnings else "native_gap_measurement_has_fallbacks"),
        "pcb_sha256_before_and_after":checksum,
        "kicad_version":pcbnew.Version(),
        "hotspot_mm":{"x":x,"y":y},
        "roi_half_size_mm":window,
        "design_rules_mm":{
            "track_width_mm":track,"clearance_mm":clearance,
            "three_tracks_wall_to_wall_mm":3*track+4*clearance,
        },
        "obstacle_count":len(obstacles),
        "native_polygon_count":sum(
            o.polygonization=="SHAPE_POLY_SET_native_0.0001mm"
            for o in obstacles),
        "analytic_approximation_count":sum(
            o.polygonization.startswith(
                "native_segment_circle_analytic_approximation")
            for o in obstacles),
        "native_polygon_warnings":warnings,
        "obstacles":[o.describe() for o in obstacles],
        "narrowest_gaps":gaps[:60],
        "all_gap_pairs_checked":len(gaps),
        "tightest_clear_gap_mm":tightest,
        "tightest_gap_is_fully_native_polygonized":(
            gaps[0]["both_native_polygonized"] if gaps else None),
        "tightest_fully_native_clear_gap_mm":tightest_native,
        "widest_verified_pair_gap_mm":widest_verified,
        "max_tracks_strict":(
            gaps[0]["max_tracks_strict"] if gaps else None),
        "hotspot_is_global_min_cut_proven":False,
        "min_cut_raster_may_be_quantization_artifact":True,
        "native_global_three_net_unroutability_proven":False,
        "no_new_vias":True,
        "source_board_unchanged":True,
        "accepted":False,
        "routing_completed":False,
        "fabrication_release":False,
    }
    return result


def main()->None:
    parser=argparse.ArgumentParser()
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--board",type=Path)
    source.add_argument("--archive",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--x",type=float,default=HOTSPOT[0])
    parser.add_argument("--y",type=float,default=HOTSPOT[1])
    parser.add_argument("--window",type=float,default=2.5)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.board:
        result=analyze(args.board,x=args.x,y=args.y,
                       window=args.window)
    else:
        from probe_block2_isolated_s1s2 import pinned_source_copy
        with tempfile.TemporaryDirectory(prefix="fcu-native-cut-") as td:
            board=pinned_source_copy(args.archive,Path(td))
            result=analyze(board,x=args.x,y=args.y,
                           window=args.window)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("NATIVE_FCU_BOTTLENECK="+json.dumps({
        k:result[k] for k in (
            "status","hotspot_mm","obstacle_count",
            "native_polygon_count","tightest_clear_gap_mm",
            "max_tracks_strict","native_global_three_net_unroutability_proven",
            "source_board_unchanged")},sort_keys=True))


if __name__=="__main__":
    main()

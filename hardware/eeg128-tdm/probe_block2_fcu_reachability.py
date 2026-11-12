#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Exact F.Cu free-polygon connectivity between locked U4 and target pads.

Native F.Cu obstacles already include 0.15 mm track/2 + 0.15 mm
clearance. This analysis never creates copper, vias, zones or Gerbers.
An ROI-disconnected result is not a proof of global PCB unroutability.
"""
from __future__ import annotations

import math
from typing import Any

Point=tuple[float,float]


def polygon_components(free:Any) -> tuple[Any,...]:
    """Return only nonzero-area disjoint free copper polygons."""
    from shapely.geometry import Polygon
    found=[]
    def visit(geom:Any)->None:
        if geom.is_empty:
            return
        if isinstance(geom,Polygon):
            if geom.area>1e-8:
                found.append(geom)
        elif hasattr(geom,"geoms"):
            for part in geom.geoms:
                visit(part)
    visit(free)
    return tuple(sorted(found,key=lambda poly:(
        -poly.area,poly.bounds[0],poly.bounds[1])))


def component_at(components:tuple[Any,...],pt:Point
                 ) -> int|None:
    from shapely.geometry import Point as ShapelyPoint
    point=ShapelyPoint(pt)
    for i,component in enumerate(components):
        if component.covers(point) or component.distance(point)<=1e-7:
            return i
    return None


def continuous_free_reachability(
    allowed_roi:Any, inflated_fixed_copper:Any,
    u4_tip:Point, target_pad:Point,
) -> tuple[Any|None,dict[str,Any],tuple[Point,Point]]:
    """Exact planar connected components, never grid-only inference.

    Returns the U4 component ONLY if the pad is in the same polygon.
    A narrow continuous free-space corridor may later fail an A* raster;
    the inverse cannot be safely inferred from raster failure.
    """
    from shapely.geometry import LineString
    from shapely.ops import nearest_points
    if allowed_roi.is_empty or not allowed_roi.is_valid:
        raise RuntimeError("Invalid native F.Cu connectivity ROI")
    free=allowed_roi.difference(inflated_fixed_copper)
    comps=polygon_components(free)
    su=component_at(comps,u4_tip)
    st=component_at(comps,target_pad)
    same=(su is not None and st is not None and su==st)
    witness=(u4_tip,target_pad)
    if su is not None and st is not None and su!=st:
        near=nearest_points(comps[su],comps[st])
        witness=((near[0].x,near[0].y),(near[1].x,near[1].y))
    elif su is not None and st is None:
        near=nearest_points(comps[su],LineString(
            (target_pad,(target_pad[0]+1e-6,target_pad[1]))))
        witness=((near[0].x,near[0].y),target_pad)
    diagnostic={
        "status":("same_continuous_FCu_component" if same
                  else "disconnected_within_bounded_native_FCu_ROI"),
        "continuous_polygon_components":len(comps),
        "u4_component_index":su,
        "target_component_index":st,
        "shared_component":bool(same),
        "u4_component_area_mm2":(
            round(comps[su].area,5) if su is not None else None),
        "target_component_area_mm2":(
            round(comps[st].area,5) if st is not None else None),
        "tested_ROI_bounds_mm":tuple(round(v,4)
                                     for v in allowed_roi.bounds),
        "min_component_gap_mm":(
            round(math.dist(*witness),6) if not same else 0.),
        "gap_witness_segment_mm":witness,
        "region_boundary_qualifier":"bounded_ROI_only_not_global_board_proof",
        "hard_centreline_clearance_mm":.300,
    }
    return (comps[su] if same else None),diagnostic,witness


def native_reachability_components(
    board:Any,nets:tuple[int,int,int],
    locked_u4:tuple[tuple[Point,...],...],
    target_pads:tuple[Point,...],
    *,extra_clearance_mm:float=.0,
) -> tuple[tuple[Any,...],dict[str,Any]]:
    """Native obstacle geometry, one exact free polygon per target net."""
    import pcbnew
    from shapely.geometry import LineString,box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles
    from probe_block2_u4_corridors import _native_fanout_blockers
    if (len(nets)!=3 or len(set(nets))!=3
            or len(locked_u4)!=3 or len(target_pads)!=3
            or extra_clearance_mm!=0.):
        raise RuntimeError("Native reachability identity/clearance drift")
    borders=board.GetBoardEdgesBoundingBox()
    edges=(pcbnew.ToMM(borders.GetX())+.56,
           pcbnew.ToMM(borders.GetY())+.56,
           pcbnew.ToMM(borders.GetRight())-.56,
           pcbnew.ToMM(borders.GetBottom())-.56)
    pts=[p for wire in locked_u4 for p in wire]+list(target_pads)
    # Broad ROI includes genuine detours around obstacles, not the old
    # 3.2-mm local macro corridor. It remains strictly inside PCB edges.
    region=box(
        max(edges[0],min(p[0] for p in pts)-10.),
        max(edges[1],min(p[1] for p in pts)-10.),
        min(edges[2],max(p[0] for p in pts)+10.),
        min(edges[3],max(p[1] for p in pts)+10.))
    if region.is_empty or region.area<30.:
        raise RuntimeError("Native reachability region too small")
    comps=[]
    detail=[]
    for i,net in enumerate(nets):
        obs,_=obstacles(board,net,.15,.15,region,.65,
                        (pcbnew.F_Cu,pcbnew.B_Cu))
        foreign=unary_union([
            LineString(locked_u4[j]).buffer(.300-1e-9,resolution=8)
            for j in range(3) if j!=i])
        blocked=obs[0].buffer(-1e-9).union(foreign)
        component,diagnostic,witness=continuous_free_reachability(
            region,blocked,locked_u4[i][-1],target_pads[i])
        diagnostic["agent"]=i
        # Every UUID here is an EXACT identity of copper on a geometric
        # witness/reference chord, not an asserted minimal planar cut set.
        cut=LineString(witness)
        near=_native_fanout_blockers(board,net,cut)
        if not near:
            near=_native_fanout_blockers(
                board,net,
                LineString((locked_u4[i][-1],target_pads[i])))
        diagnostic["native_copper_UUID_witnesses"]=near
        diagnostic["witness_is_min_cut_proof"]=False
        diagnostic["u4_tip_mm"]=locked_u4[i][-1]
        diagnostic["target_pad_mm"]=target_pads[i]
        detail.append(diagnostic)
        comps.append(component)
    return tuple(comps),{
        "status":("three_globally_reachable_FCu_components_in_ROI"
                  if all(x is not None for x in comps)
                  else "native_midpoint_FCu_component_disconnected"),
        "all_three_reachable":all(x is not None for x in comps),
        "per_agent":detail,
        "region_bounds_mm":tuple(round(v,4)
                                 for v in region.bounds),
        "no_new_vias":True,
        "geometry_unsatisfiable_proven":False,
        "native_DRC_still_required":True,
    }

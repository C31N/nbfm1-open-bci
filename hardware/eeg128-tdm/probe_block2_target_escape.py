#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native target-pad triplet escape; no board mutation, no fabrication release.

The physical three target pads are selected from the original open
endpoints by net ID and F.Cu copper geometry. The coupled finite search
individually routes each target pad to a shared 0.300-mm pitch fanout
outside its copper cluster and makes the three target escapes immutable.
This creates a second independent, fail-closed hard-copper boundary for
the subsequent macro search.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

Point=tuple[float,float]
Endpoints=tuple[tuple[Point,Point],...]
Wires=tuple[tuple[Point,...],...]


def _target_pads(board:Any, nets:tuple[int,int,int],
                 endpoints:Endpoints, u4_sides:tuple[int,...]
                 ) -> tuple[tuple[Any,...],tuple[Point,...]]:
    import pcbnew
    from route_targeted_closure import xy
    selected=[]
    centers=[]
    used=set()
    for agent in range(3):
        far=endpoints[agent][1-u4_sides[agent]]
        matches=[]
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if (pad.GetNetCode()!=nets[agent] or
                        not pad.IsOnLayer(pcbnew.F_Cu)):
                    continue
                gap=math.dist(xy(pad.GetPosition()),far)
                if gap<=.85:
                    matches.append((gap,pad.m_Uuid.AsString(),fp,pad))
        if not matches:
            raise RuntimeError(
                "native_FCu_target_pad_not_found_for_agent_"+str(agent))
        matches.sort(key=lambda v:(v[0],v[1]))
        gap,uid,fp,pad=matches[0]
        if uid in used:
            raise RuntimeError("target_pad_UUID_not_unique")
        if len(matches)>1 and abs(matches[0][0]-matches[1][0])<1e-5:
            raise RuntimeError("target_pad_ambiguity")
        if gap>.55:
            raise RuntimeError("target_endpoint_to_pad_center_too_far")
        used.add(uid)
        selected.append(pad)
        centers.append(xy(pad.GetPosition()))
    return tuple(selected),tuple(centers)


def native_target_triplet_preflight(
    board:Any, original_endpoints:Endpoints,
    nets:tuple[int,int,int],u4_sides:tuple[int,...],
    sealed_u4_wires:Wires,
) -> tuple[Wires,tuple[int,...],dict[str,Any]]:
    """Joint A* target pad escapes with exact native F.Cu obstacle checks."""
    import numpy as np
    import pcbnew
    from shapely import contains_xy,prepare
    from shapely.geometry import LineString,box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles,pad_copper_shape
    from probe_block2_u4_topological import GRID_MM
    from probe_block2_target_coupled import (
        coupled_target_open_space_escapes,
    )

    if (len(nets)!=3 or len(set(nets))!=3 or
            len(u4_sides)!=3 or any(x not in (0,1) for x in u4_sides)
            or len(sealed_u4_wires)!=3):
        raise RuntimeError("target_triplet_preflight_invalid_identity")
    pads,ports=_target_pads(board,nets,original_endpoints,u4_sides)
    target_sides=tuple(1-v for v in u4_sides)
    widths=[.15]*3
    if any(not p.IsOnLayer(pcbnew.F_Cu) for p in pads):
        raise RuntimeError("target_pad_FCu_identity_changed")
    bundle_targets=tuple(w[-1] for w in sealed_u4_wires)
    span=[max(pt[a] for pt in ports)-min(pt[a] for pt in ports)
          for a in (0,1)]
    tangent=0 if span[0]>=span[1] else 1
    normal_axis=1-tangent
    centroid=[sum(pt[a] for pt in ports)/3 for a in (0,1)]
    other_centroid=[sum(pt[a] for pt in bundle_targets)/3
                    for a in (0,1)]
    delta=other_centroid[normal_axis]-centroid[normal_axis]
    if abs(delta)<.50:
        raise RuntimeError("no_well_defined_outward_target_escape_axis")
    sign=1. if delta>0 else -1.
    # The target pad COPPER hull is the hard source cluster. This determines
    # the free-space side of the goal lanes, not the old U4 dogleg template.
    pads_shape=unary_union([
        pad_copper_shape(pad,pcbnew.F_Cu) for pad in pads])
    pad_bounds=pads_shape.bounds
    board_bounds=board.GetBoardEdgesBoundingBox()
    low=(pcbnew.ToMM(board_bounds.GetX())+.56,
         pcbnew.ToMM(board_bounds.GetY())+.56)
    high=(pcbnew.ToMM(board_bounds.GetRight())-.56,
          pcbnew.ToMM(board_bounds.GetBottom())-.56)
    xlo=max(low[0],min(p[0] for p in ports)-5.8)
    xhi=min(high[0],max(p[0] for p in ports)+5.8)
    ylo=max(low[1],min(p[1] for p in ports)-5.8)
    yhi=min(high[1],max(p[1] for p in ports)+5.8)
    if not xhi-xlo>=4.5 or not yhi-ylo>=4.5:
        raise RuntimeError("target_escape_window_outside_board")
    xs=np.arange(xlo,xhi+GRID_MM/2,GRID_MM)
    ys=np.arange(ylo,yhi+GRID_MM/2,GRID_MM)
    gx,gy=np.meshgrid(xs,ys)
    region=box(xlo,ylo,xhi,yhi)
    shapes=[]
    masks=[]
    for i,net in enumerate(nets):
        geom,_=obstacles(board,net,widths[i],.15,region,.65,
                         (pcbnew.F_Cu,pcbnew.B_Cu))
        # The other U4 fanouts are hard even if the local windows overlap.
        foreign=unary_union([
            LineString(sealed_u4_wires[j]).buffer(
                .300-1e-9,resolution=8)
            for j in range(3) if j!=i])
        shape=geom[0].buffer(-1e-9).union(foreign)
        prepare(shape)
        shapes.append(shape)
        masks.append(contains_xy(shape,gx,gy))
    # No fixed 0.300-mm target bundle: the native target pads are
    # 2.600 mm apart. A coupled search now reserves THREE individually
    # routed F.Cu exits and their full clearance without converging them.
    started=time.monotonic()
    routes,diag=coupled_target_open_space_escapes(
        masks,shapes,xs,ys,ports,tangent,sign,
        deadline=started+42.,max_expanded=170000)
    pad_ids=[pad.m_Uuid.AsString() for pad in pads]
    pad_refs=[]
    for i,pad in enumerate(pads):
        pad_refs.append({
            "agent":i,"UUID":pad_ids[i],
            "pad_number":pad.GetNumber(),
            "net_name":pad.GetNetname(),
            "pad_center_mm":ports[i],
        })
    if routes is None:
        # These UUIDs are observable blockers near direct target chords,
        # NOT a claimed complete topological minimum cut.
        from probe_block2_u4_corridors import _native_fanout_blockers
        references=[]
        for i in range(3):
            line=LineString((ports[i],bundle_targets[i]))
            references.append({
                "agent":i,
                "reference_line_only":True,
                "nearby_native_copper_UUIDs":
                    _native_fanout_blockers(board,nets[i],line)[:6],
            })
        report={
            "status":"target_triplet_native_preflight_blocked",
            "near_reference_obstacle_samples":references,
            "source_pad_refs":pad_refs,
            "native_target_cluster_hull_mm":pad_bounds,
            "target_search":diag,
            "new_vias_added":0,
            "geometry_unsatisfiable_proven":False,
        }
        raise RuntimeError(
            json.dumps(report,separators=(",",":"),sort_keys=True)[:5800])
    lines=tuple(LineString(p) for p in routes)
    if (any(lines[i].relate_pattern(shapes[i],"T********")
            for i in range(3))
            or min(lines[i].distance(lines[j])
                   for i in range(3) for j in range(i+1,3))<.300-1e-8):
        raise RuntimeError("target_triplet_exact_geometry_postcheck_failed")
    serialized=json.dumps(
        routes,separators=(",",":"),allow_nan=False).encode()
    report={
        "status":"three_native_target_escapes_preflighted_not_DRC",
        "source_pad_refs":pad_refs,
        "target_pad_UUIDs":pad_ids,
        "target_pad_centres_mm":ports,
        "target_cluster_bounds_mm":pad_bounds,
        "target_escape_immutable_sha256":hashlib.sha256(
            serialized).hexdigest(),
        "target_escape_vertex_counts":[len(x) for x in routes],
        "target_escape_paths_mm":routes,
        "hard_centreline_clearance_mm":.300,
        "target_lane_consolidation_required":False,
        "minimum_target_centerline_mm":diag["minimum_centerline_mm"],
        "search":diag,
        "no_new_vias":True,
        "fixed_copper_unchanged":True,
        "native_DRC_still_required":True,
    }
    return routes,target_sides,report

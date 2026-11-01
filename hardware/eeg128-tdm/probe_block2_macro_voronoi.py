#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Scratch-only approximate Voronoi-medial macro routing on native F.Cu.

The chamfer-distance ridges of the grid-sampled F.Cu free space approximate
the medial axis (not a claim of exact analytic Voronoi/CDT). Compute actual
connected-component counts instead of assuming a historical 54. Plan three
distinct lane-biased macro paths, choose 3-5 waypoints on each, and call the
existing native-obstacle A* ONLY between successive waypoints. All macro paths
remain geometric proposals until 201 original victims, independent DRC,
L3 area, parity and independent replay are each proven.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from typing import Any, Callable

Point = tuple[float,float]
Progress = Callable[[str, dict[str,Any]], None]
TARGETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
STEPS = ((-1,0,1.),(1,0,1.),(0,-1,1.),(0,1,1.),
         (-1,-1,math.sqrt(2)),(-1,1,math.sqrt(2)),
         (1,-1,math.sqrt(2)),(1,1,math.sqrt(2)))


def _components(mask: Any) -> tuple[Any, list[int]]:
    """8-connected components of free grid samples, no implicit 54 assumption."""
    import numpy as np
    h,w=mask.shape
    labels=np.full((h,w),-1,dtype=np.int32)
    sizes=[]
    for y in range(h):
        for x in range(w):
            if mask[y,x] or labels[y,x]!=-1:
                continue
            ident=len(sizes)
            todo=[(y,x)]
            labels[y,x]=ident
            size=0
            while todo:
                py,px=todo.pop()
                size+=1
                for dy,dx,_ in STEPS:
                    qy,qx=py+dy,px+dx
                    if (0<=qy<h and 0<=qx<w
                            and not mask[qy,qx] and labels[qy,qx]==-1):
                        labels[qy,qx]=ident
                        todo.append((qy,qx))
            sizes.append(size)
    return labels,sizes


def _chamfer_distance(blocked: Any) -> Any:
    """Approximate obstacle clearance for deterministic medial-ridge scores."""
    import numpy as np
    h,w=blocked.shape
    # Boundary is blocked; outside map must not be treated as free space.
    field=np.full((h,w),float("inf"))
    field[blocked]=0
    field[0,:]=0
    field[-1,:]=0
    field[:,0]=0
    field[:,-1]=0
    for y in range(h):
        for x in range(w):
            for dy,dx,weight in STEPS:
                py,px=y+dy,x+dx
                if py<y or (py==y and px<x):
                    if 0<=py<h and 0<=px<w:
                        field[y,x]=min(field[y,x],field[py,px]+weight)
    for y in range(h-1,-1,-1):
        for x in range(w-1,-1,-1):
            for dy,dx,weight in STEPS:
                py,px=y+dy,x+dx
                if py>y or (py==y and px>x):
                    if 0<=py<h and 0<=px<w:
                        field[y,x]=min(field[y,x],field[py,px]+weight)
    return field


def macro_routes(
    board: Any,
    endpoints: dict[str, tuple[Point,Point]],
    order: tuple[str,str,str],
    *,
    step_mm: float = .44,
    lane_bias: float = 7.0,
    micro_step_mm: float = .22,
    deadline_s: float = 130.,
    progress: Progress | None = None,
) -> tuple[list[list[tuple[int,float,float]]] | None,dict[str,Any]]:
    import numpy as np
    import pcbnew
    from shapely import contains_xy, prepare
    from shapely.geometry import box
    from route_targeted_closure import obstacles, search, add_path

    if (set(order)!=set(TARGETS) or len(order)!=3 or
            not .20<=step_mm<=.65 or not .18<=micro_step_mm<=.30
            or not 0<=lane_bias<=30 or not 30<=deadline_s<=190):
        raise ValueError("Unreviewed three-net macro corridor request")
    began=time.monotonic()
    pts=[point for n in TARGETS for point in endpoints[n]]
    bounds=board.GetBoardEdgesBoundingBox()
    pad=.56
    x0=max(min(x for x,_ in pts)-4,pcbnew.ToMM(bounds.GetX())+pad)
    x1=min(max(x for x,_ in pts)+4,pcbnew.ToMM(bounds.GetRight())-pad)
    y0=max(min(y for _,y in pts)-4,pcbnew.ToMM(bounds.GetY())+pad)
    y1=min(max(y for _,y in pts)+4,pcbnew.ToMM(bounds.GetBottom())-pad)
    xs=np.arange(x0,x1+step_mm/2,step_mm)
    ys=np.arange(y0,y1+step_mm/2,step_mm)
    if len(xs)<3 or len(ys)<3 or len(xs)*len(ys)>180000:
        return None,{"status":"macro_grid_unavailable"}
    gx,gy=np.meshgrid(xs,ys)
    window=box(x0,y0,x1,y1)
    diag:dict[str,Any]={
        "status":"macro_started","macro_grid":[len(xs),len(ys)],
        "macro_step_mm":step_mm,"micro_step_mm":micro_step_mm,
        "component_counts_by_net":{},"medial_ridge_nodes_by_net":{},
        "macro_waypoints":{},"micro_segments_completed":{},
        "all_targets_qualified":False,"new_vias_added":0,
        "route_order":order,"macro_lane_assignment":{},
        "native_drc_required":True,"source_board_no_release":True,
    }
    def emit(stage:str) -> None:
        diag["last_stage"]=stage
        if progress:
            progress(stage,diag)
    emit("macro_native_obstacle_grid_started")
    # Explicit fixed assignment to spatially distinct route corridors; never
    # claim that the source has exactly 54 free-space components.
    lane_for={"CH028_N_MUX":0,"CH029_N_MUX":1,"CH030_N_MUX":2}
    assigned_lines=[]
    planned={}
    all_routes=[]
    seq=itertools.count()
    for net in order:
        if time.monotonic()-began>deadline_s:
            diag["status"]="macro_time_budget_exhausted"
            emit("macro_deadline")
            return None,diag
        netcode=board.FindNet(net).GetNetCode()
        geoms,_=obstacles(board,netcode,.15,.15,window,.65,
                           (pcbnew.F_Cu,pcbnew.B_Cu))
        geom=geoms[0].buffer(-1e-9)
        prepare(geom)
        blocked=contains_xy(geom,gx,gy)
        labels,sizes=_components(blocked)
        dist=_chamfer_distance(blocked)
        # A discrete medial axis is approximated by distance-field ridges,
        # with all native obstacles still hard-blocked in the macro graph.
        h,w=blocked.shape
        ridge=np.zeros((h,w),dtype=bool)
        for y in range(1,h-1):
            for x in range(1,w-1):
                if blocked[y,x]:
                    continue
                q=dist[y-1:y+2,x-1:x+2]
                if dist[y,x]>=max(float(q[0,1]),float(q[2,1]),
                                  float(q[1,0]),float(q[1,2])):
                    ridge[y,x]=True
        diag["component_counts_by_net"][net]=len(sizes)
        diag["medial_ridge_nodes_by_net"][net]=int(ridge.sum())
        diag["macro_lane_assignment"][net]=(
            "north" if lane_for[net]==0 else
            "middle" if lane_for[net]==1 else "south")
        emit("macro_voronoi_ridges_" + net)
        def metric(node:tuple[int,int]) -> Point:
            return float(xs[node[0]]),float(ys[node[1]])
        def anchor(pt:Point) -> tuple[int,int] | None:
            ix=int(round((pt[0]-x0)/step_mm))
            iy=int(round((pt[1]-y0)/step_mm))
            coords=((x,y) for y in range(max(0,iy-5),min(h,iy+6))
                    for x in range(max(0,ix-5),min(w,ix+6))
                    if not blocked[y,x])
            return min(coords,key=lambda t:math.dist(metric(t),pt),
                       default=None)
        a=anchor(endpoints[net][0])
        b=anchor(endpoints[net][1])
        if a is None or b is None or labels[a[1],a[0]]!=labels[b[1],b[0]]:
            diag["status"]="macro_different_free_components"
            diag["blocked_target"]=net
            emit("macro_component_barrier_" + net)
            return None,diag
        # Corridor axis is defined relative to THIS actual free window.
        # Penalize excursions into the other two net lanes, and revisit
        # alternative orders on separate pinned scratch boards.
        target_y=y0+(.17+.33*lane_for[net])*(y1-y0)
        q=[(0.,next(seq),0.,a)]
        prev:dict[tuple[int,int],tuple[int,int] | None]={a:None}
        costs={a:0.}
        complete=None
        while q:
            if time.monotonic()-began>deadline_s:
                break
            _,_,g,node=heapq.heappop(q)
            if costs.get(node)!=g:
                continue
            if node==b:
                complete=node
                break
            for dy,dx,weight in STEPS:
                nx,ny=node[0]+dx,node[1]+dy
                if not(0<=nx<w and 0<=ny<h) or blocked[ny,nx]:
                    continue
                if dx and dy and (blocked[node[1],nx] or blocked[ny,node[0]]):
                    continue
                pt=metric((nx,ny))
                clearance_penalty=2./max(float(dist[ny,nx]),1.)
                ridge_reward=.10 if ridge[ny,nx] else .28
                # Endpoints are always exempt from corridor preference.
                relative=min(math.dist(pt,endpoints[net][0]),
                             math.dist(pt,endpoints[net][1]))
                lane_cost=lane_bias*abs(pt[1]-target_y)/(y1-y0)*min(1.,relative/2.)
                other_cost=sum(32. if math.dist(pt,prior)<.65 else 0.
                               for lane in assigned_lines for prior in lane)
                g2=g+step_mm*weight*(1+clearance_penalty+
                                      ridge_reward+lane_cost+other_cost)
                nxt=(nx,ny)
                if g2<costs.get(nxt,float("inf")):
                    costs[nxt]=g2
                    prev[nxt]=node
                    heapq.heappush(q,(g2+math.dist(pt,metric(b)),
                                      next(seq),g2,nxt))
        if complete is None:
            diag["status"]="macro_skeleton_path_unavailable"
            diag["blocked_target"]=net
            emit("macro_graph_search_failed_" + net)
            return None,diag
        course=[]
        cursor:tuple[int,int] | None=complete
        while cursor is not None:
            course.append(metric(cursor))
            cursor=prev[cursor]
        course.reverse()
        if len(course)<5:
            diag["status"]="macro_course_too_short_for_waypoints"
            diag["blocked_target"]=net
            emit("macro_waypoint_shortage_"+net)
            return None,diag
        # Three internal macro-waypoints (4 microrouting hops), snapped to
        # actual reachable graph vertices with nonzero obstacle clearance.
        indices=sorted(set(round((len(course)-1)*q/4) for q in (1,2,3)))
        waypoints=[course[i] for i in indices]
        if len(waypoints)!=3:
            diag["status"]="macro_underdetermined_waypoint_count"
            emit("macro_waypoint_count_failed_"+net)
            return None,diag
        diag["macro_waypoints"][net]=waypoints
        diag["micro_segments_completed"][net]=0
        planned[net]=waypoints
        # All three macro corridors are planned on the SAME pre-route fixed
        # copper; micro tracks are not committed until macro reservations
        # exist for every target. This avoids prematurely disconnecting the
        # second target on the coarse grid.
        assigned_lines.append(course[::max(1,len(course)//80)])
        emit("macro_waypoints_selected_"+net)
    if set(planned)!=set(TARGETS):
        raise RuntimeError("All three target corridors not preplanned")
    emit("macro_three_waypoint_corridors_preplanned")
    # F.Cu only, no via: actual native A* microroutes each fixed macro hop.
    # A crossing found at this stage is a failed candidate, never released.
    for net in order:
        netcode=board.FindNet(net).GetNetCode()
        waypoints=planned[net]
        hop_points=[endpoints[net][0]]+waypoints+[endpoints[net][1]]
        netroutes=[]
        for start,goal in zip(hop_points,hop_points[1:]):
            hop=search(board,start,goal,netcode,.15,.15,False,
                       1.45,step=micro_step_mm,max_nodes=15000,
                       deadline=min(time.monotonic()+10,began+deadline_s),
                       start_layer=0,goal_layer=0,
                       layers=(pcbnew.F_Cu,pcbnew.B_Cu))
            if hop is None or len(hop)<2 or any(p[0]!=0 for p in hop):
                diag["status"]="macro_micro_hop_unavailable"
                diag["blocked_target"]=net
                diag["failed_hop_endpoints"]=[start,goal]
                emit("macro_micro_hop_failed_"+net)
                return None,diag
            add_path(board,hop,netcode,.15,layers=(pcbnew.F_Cu,pcbnew.B_Cu))
            netroutes.extend(hop if not netroutes else hop[1:])
            diag["micro_segments_completed"][net]+=1
            emit("macro_micro_hop_committed_"+net)
        all_routes.append(netroutes)
        emit("macro_target_routed_"+net)
    diag["status"]="macro_three_targets_proposed_unverified"
    diag["all_targets_qualified"]=False
    emit("macro_three_targets_complete_native_DRC_pending")
    return all_routes,diag

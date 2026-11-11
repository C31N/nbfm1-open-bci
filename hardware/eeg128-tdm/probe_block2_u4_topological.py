#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded native-obstacle three-net U4 topological F.Cu escape search.

No fixed dog-leg templates. Independent grid A* paths negotiate hard native
copper and dynamically reserve already found neighbouring signals. A 1.5-mm
0.300-mm centre-pitch bundle is REQUIRED only beyond the U3 pin-7 obstacle.
This is disposable, no-release geometry. No via, pad, zone or board mutations.
A failed bounded search never proves that the PCB cannot be routed.
"""
from __future__ import annotations

from collections import Counter
import heapq
import itertools
import math
import time
from typing import Any

Point = tuple[float, float]
Endpoints = tuple[tuple[Point, Point], ...]
Wires = tuple[tuple[Point, ...], ...]
U3_PAD7_UUID = "e37256fc-3b9f-435d-8042-f7d4c1147aca"
GRID_MM = .15
COPPER_CENTRE_PITCH_MM = .300
BUNDLE_MM = 1.5
MOVES = ((0,-1),(1,0),(-1,0),(0,1),(1,-1),(-1,-1),(1,1),(-1,1))


def _astar_grid(
    blocked: Any, start: tuple[int,int], goal: tuple[int,int],
    *, max_nodes: int, deadline: float,
) -> tuple[tuple[tuple[int,int], ...] | None, str, int]:
    """Deterministic 8-neighbour A*, never cuts blocked diagonal corners."""
    h,w=blocked.shape
    sx,sy=start
    gx,gy=goal
    if not (0<=sx<w and 0<=sy<h and 0<=gx<w and 0<=gy<h):
        return None,"anchor_outside_grid",0
    if blocked[sy,sx] or blocked[gy,gx]:
        return None,"endpoint_masked",0
    counter=itertools.count()
    pq=[(math.hypot(gx-sx,gy-sy),next(counter),0.,(sx,sy))]
    costs={start:0.}
    parents: dict[tuple[int,int],tuple[int,int]|None]={start:None}
    count=0
    while pq and count<max_nodes:
        if time.monotonic()>=deadline:
            return None,"wall_budget_exhausted",count
        _,_,distance,current=heapq.heappop(pq)
        if distance!=costs[current]:
            continue
        count+=1
        if current==goal:
            path=[]
            here:tuple[int,int]|None=current
            while here is not None:
                path.append(here)
                here=parents[here]
            return tuple(reversed(path)),"path_found",count
        x,y=current
        for dx,dy in MOVES:
            nx,ny=x+dx,y+dy
            if not (0<=nx<w and 0<=ny<h) or blocked[ny,nx]:
                continue
            if dx and dy and (blocked[y,nx] or blocked[ny,x]):
                continue
            n=(nx,ny)
            g=distance+math.hypot(dx,dy)
            if g<costs.get(n,math.inf)-1e-10:
                costs[n]=g
                parents[n]=current
                priority=g+math.hypot(gx-nx,gy-ny)
                heapq.heappush(pq,(priority,next(counter),g,n))
    return None,("node_budget_exhausted" if pq else "frontier_exhausted"),count


def _candidate_lanes(
    xs: Any, ys: Any, ports: tuple[Point,...],
    u3_bounds: tuple[float,float,float,float],
    normal_sign: float, tangent: int,
) -> list[tuple[int,int]]:
    """Rank all three-track goal lanes in free space beyond U3 pad 7."""
    normal_axis=1-tangent
    pcenter=sum(p[tangent] for p in ports)/3
    tcoord=xs if tangent==0 else ys
    ncoord=ys if tangent==0 else xs
    # Downstream bundle's initial point is 0.45 mm past the native U3 box.
    u3_exit=(u3_bounds[normal_axis] if normal_sign<0 else
             u3_bounds[normal_axis+2])
    results=[]
    for offset in (.60,1.10,1.60,2.10):
        y_target=u3_exit+normal_sign*offset
        normal_idx=min(range(len(ncoord)),
                       key=lambda j:abs(float(ncoord[j])-y_target))
        for lateral in (1.8,-1.8,2.7,-2.7,3.6,-3.6,4.5,-4.5,0.,5.4,-5.4):
            x_target=pcenter+lateral
            middle=min(range(len(tcoord)),
                       key=lambda j:abs(float(tcoord[j])-x_target))
            if middle<2 or middle>=len(tcoord)-2:
                continue
            # Every two grid cells = 0.300 mm, independent of U4 pad pitch.
            if normal_idx<10 and normal_sign<0:
                continue
            if normal_idx+10>=len(ncoord) and normal_sign>0:
                continue
            results.append((middle,normal_idx))
    return results


def _route_candidates(
    base_masks: list[Any], fixed_shapes: list[Any],
    xs: Any, ys: Any, ports: tuple[Point,...],
    goal_rows: list[tuple[int,int]], tangent: int, normal_sign: float,
    *, deadline: float, max_expanded: int,
) -> tuple[Wires|None,dict[str,Any]]:
    """Try lane placements and 3-agent priority orders; reserve each path.

    Each net's path is routed independently through the real fixed-copper
    field. The other two nets' routed F.Cu become hard 0.300-mm obstacles.
    A final exact Shapely clearance check always overrides grid optimism.
    """
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    def xy(node: tuple[int,int]) -> Point:
        return float(xs[node[0]]),float(ys[node[1]])

    ranks=sorted(range(3),key=lambda i:ports[i][tangent])
    normal_axis=1-tangent
    attempts=Counter()
    failing: list[dict[str,Any]]=[]
    expanded_total=0
    best_components=0
    tried=0
    for middle,normal_start in goal_rows:
        if time.monotonic()>=deadline:
            break
        goal_starts=[None,None,None]
        bundle_segments=[]
        for j,agent in enumerate(ranks):
            lane_idx=middle+2*(j-1)
            idx=(lane_idx,normal_start) if tangent==0 else (normal_start,lane_idx)
            far=(lane_idx,normal_start-10 if normal_sign<0 else normal_start+10
                 ) if tangent==0 else (
                     normal_start-10 if normal_sign<0 else normal_start+10,
                     lane_idx)
            goal_starts[agent]=idx
            bundle_segments.append((agent,LineString([xy(idx),xy(far)]),far))
        # If any downstream 1.5-mm rail intersects fixed native copper,
        # skip it entirely. The lane itself is not relaxed by the solver.
        if any(line.relate_pattern(fixed_shapes[i],"T********")
               for i,line,_ in bundle_segments):
            attempts["bundle_fixed_copper_blocked"]+=1
            continue
        if any(base_masks[i][a[1],a[0]]
               for i,a in enumerate(goal_starts)):
            attempts["bundle_anchor_blocked"]+=1
            continue
        tried+=1
        for ordering in itertools.permutations(ranks):
            if time.monotonic()>=deadline or expanded_total>=max_expanded:
                break
            paths: dict[int,tuple[Point,...]]={}
            reserved=[]
            failed=False
            for agent in ordering:
                mask=base_masks[agent].copy()
                native=fixed_shapes[agent]
                if reserved:
                    copper=unary_union([
                        line.buffer(COPPER_CENTRE_PITCH_MM-1e-9,
                                    quad_segs=8)
                        for line in reserved])
                    gx,gy=np.meshgrid(xs,ys)
                    mask |= contains_xy(copper,gx,gy)
                    native=unary_union([native,copper])
                # Keep existing U4 pad copper precisely as the launch point.
                pad=ports[agent]
                row_indices=[]
                ix=int(round((pad[0]-float(xs[0]))/GRID_MM))
                iy=int(round((pad[1]-float(ys[0]))/GRID_MM))
                for dx in range(-2,3):
                    for dy in range(-2,3):
                        ax,ay=ix+dx,iy+dy
                        if (0<=ax<len(xs) and 0<=ay<len(ys)
                                and not mask[ay,ax]):
                            line=LineString([pad,xy((ax,ay))])
                            if not line.relate_pattern(native,"T********"):
                                row_indices.append((math.dist(pad,xy((ax,ay))),
                                                    ax,ay))
                if not row_indices:
                    attempts["no_native_pad_anchor"]+=1
                    failed=True
                    break
                anchor=min(row_indices)[1:]
                goal=goal_starts[agent]
                path,why,expanded=_astar_grid(
                    mask,anchor,goal,max_nodes=8000,
                    deadline=deadline)
                expanded_total+=expanded
                attempts[why]+=1
                if path is None:
                    failed=True
                    break
                raw=[pad]+[xy(p) for p in path]
                terminal=next(line for i,line,_ in bundle_segments
                              if i==agent)
                raw.append(tuple(terminal.coords[-1]))
                shape=LineString(raw)
                # Guard all true segment interiors, including grid diagonals,
                # against original fixed copper AND reserved new tracks.
                if shape.relate_pattern(native,"T********"):
                    attempts["native_segment_intersection"]+=1
                    failed=True
                    break
                paths[agent]=tuple(raw)
                reserved.append(shape)
                best_components=max(best_components,len(paths))
            if failed:
                if len(failing)<14:
                    failing.append({
                        "lane":(middle,normal_start),
                        "priority_order":ordering,
                        "completed_agents":sorted(paths),
                        "last_agent":agent,
                        "reason":why if 'path' in locals() and path is None
                                 else "native_segment_or_anchor_block",
                    })
                continue
            wires=tuple(paths[i] for i in range(3))
            lines=[LineString(w) for w in wires]
            gap=min(lines[i].distance(lines[j])
                    for i in range(3) for j in range(i+1,3))
            if gap<COPPER_CENTRE_PITCH_MM-1e-8:
                attempts["mutual_copper_clearance"]+=1
                continue
            diag={
                "status":"topological_U4_three_FCu_escape_proposed",
                "goal_lane_placement":(middle,normal_start),
                "goal_lane_mm":[xy(goal_starts[i]) for i in range(3)],
                "routing_priority":ordering,
                "total_a_star_nodes":expanded_total,
                "enumerated_goal_lanes":len(goal_rows),
                "tested_goal_lanes":tried,
                "a_star_outcomes":dict(attempts),
                "minimum_centerline_mm":gap,
                "tip_pitch_mm":COPPER_CENTRE_PITCH_MM,
                "parallel_length_mm":BUNDLE_MM,
                "no_new_vias":True,
                "native_DRC_still_required":True,
            }
            return wires,diag
    return None,{
        "status":"topological_U4_escape_bounded_no_solution",
        "enumerated_goal_lanes":len(goal_rows),
        "tested_goal_lanes":tried,
        "best_routed_agents":best_components,
        "total_a_star_nodes":expanded_total,
        "max_expanded_nodes":max_expanded,
        "a_star_outcomes":dict(attempts),
        "sampled_dead_ends":failing,
        "search_wall_budget_exhausted":time.monotonic()>=deadline,
        "native_DRC_still_required":True,
        "geometry_unsatisfiable_proven":False,
    }


def native_u4_topological_preflight(
    board: Any, ports: tuple[Point,...], nets: tuple[int,int,int],
    endpoints: Endpoints,
) -> tuple[Wires, tuple[int,...],Point,dict[str,Any]]:
    """Topological local U4 solver, identity-gated and fully non-mutating."""
    import numpy as np
    import pcbnew
    from shapely import contains_xy,prepare
    from shapely.geometry import box
    from route_targeted_closure import obstacles,pad_copper_shape
    from probe_block2_u4_corridors import CH027_PINS

    if len(ports)!=3 or len(nets)!=3 or len(set(nets))!=3:
        raise RuntimeError("Three distinct native U4 F.Cu nets required")
    u3=[f for f in board.GetFootprints() if f.GetReference()=="U3"]
    if len(u3)!=1:
        raise RuntimeError("U3 protected footprint identity drift")
    pins=[p for p in u3[0].Pads()
          if (p.GetNumber()=="7" and p.m_Uuid.AsString()==U3_PAD7_UUID
              and p.GetNetname()=="CH018_P_MUX"
              and p.IsOnLayer(pcbnew.F_Cu))]
    if len(pins)!=1:
        raise RuntimeError("U3 pin 7 net or UUID changed")
    fixed_ch027=[tr for tr in board.GetTracks()
                 if any(tr.m_Uuid.AsString().startswith(prefix)
                        for prefix in CH027_PINS)]
    if (len(fixed_ch027)!=2 or
            {tr.m_Uuid.AsString()[:8] for tr in fixed_ch027}
            !=set(CH027_PINS) or
            any(tr.GetNetname()!="CH027_N_MUX"
                or tr.GetLayer()!=pcbnew.F_Cu
                or isinstance(tr,pcbnew.PCB_VIA)
                for tr in fixed_ch027)):
        raise RuntimeError("Protected CH027 U4 segments changed")
    sides=[]
    others=[]
    for i in range(3):
        dist=(math.dist(ports[i],endpoints[i][0]),
              math.dist(ports[i],endpoints[i][1]))
        side=0 if dist[0]<=dist[1] else 1
        if dist[side]>1.2:
            raise RuntimeError("Target endpoint no longer near U4 pad")
        sides.append(side)
        others.append(endpoints[i][1-side])
    span=[max(p[a] for p in ports)-min(p[a] for p in ports)
          for a in (0,1)]
    tangent=0 if span[0]>=span[1] else 1
    normal_axis=1-tangent
    sign=(1. if sum(p[normal_axis]-ports[i][normal_axis]
                    for i,p in enumerate(others))>0 else -1.)
    direction=(sign,0.) if normal_axis==0 else (0.,sign)
    bounds=board.GetBoardEdgesBoundingBox()
    bbox_coords=(pcbnew.ToMM(bounds.GetX())+.56,
                 pcbnew.ToMM(bounds.GetY())+.56,
                 pcbnew.ToMM(bounds.GetRight())-.56,
                 pcbnew.ToMM(bounds.GetBottom())-.56)
    u3_bounds=pad_copper_shape(pins[0],pcbnew.F_Cu).bounds
    # Local bounded exact-geometry search window; no extrapolation beyond PCB.
    xlo=max(bbox_coords[0],min(min(p[0] for p in ports)-6.5,
                                 u3_bounds[0]-5.))
    xhi=min(bbox_coords[2],max(max(p[0] for p in ports)+6.5,
                                 u3_bounds[2]+5.))
    ylo=max(bbox_coords[1],min(min(p[1] for p in ports)-9.0,
                                 u3_bounds[1]-4.0))
    yhi=min(bbox_coords[3],max(max(p[1] for p in ports)+2.0,
                                 u3_bounds[3]+2.0))
    xs=np.arange(xlo,xhi+GRID_MM/2,GRID_MM)
    ys=np.arange(ylo,yhi+GRID_MM/2,GRID_MM)
    if len(xs)<20 or len(ys)<20:
        raise RuntimeError("U4 topological search grid outside PCB")
    gx,gy=np.meshgrid(xs,ys)
    region=box(xlo,ylo,xhi,yhi)
    shapes=[]
    masks=[]
    for code in nets:
        shape=obstacles(board,code,.15,.15,region,.65,
                        (pcbnew.F_Cu,pcbnew.B_Cu))[0][0].buffer(-1e-9)
        prepare(shape)
        shapes.append(shape)
        masks.append(contains_xy(shape,gx,gy))
    lanes=_candidate_lanes(xs,ys,ports,u3_bounds,sign,tangent)
    start=time.monotonic()
    wires,report=_route_candidates(
        masks,shapes,xs,ys,ports,lanes,tangent,sign,
        deadline=start+70.,max_expanded=300000)
    if wires is None:
        import json
        # Diagnostic UUIDs near straight-reference corridors are ONLY
        # candidate explanations, not proof of the exact A* cut set.
        from shapely.geometry import LineString
        from probe_block2_u4_corridors import _native_fanout_blockers
        direct=[]
        for i in range(3):
            reference=LineString((ports[i],others[i]))
            direct.append({
                "agent":i,
                "near_direct_reference_only":
                    _native_fanout_blockers(board,nets[i],reference)[:4],
            })
        report.update({
            "U4_pad_centres_mm":ports,
            "U3_pad7_bounds_mm":u3_bounds,
            "U3_pad7_UUID":U3_PAD7_UUID,
            "protected_CH027_UUIDs":[tr.m_Uuid.AsString()
                                     for tr in fixed_ch027],
            "near_direct_reference_objects":direct,
            "new_vias_added":0,
        })
        raise RuntimeError(
            "U4_topological_bounded_preflight_blocked: "
            +json.dumps(report,separators=(",",":"),sort_keys=True)[:5400])
    # Confirm exact native copper again after the discrete search.
    from shapely.geometry import LineString
    if any(LineString(wires[i]).relate_pattern(shapes[i],"T********")
           for i in range(3)):
        raise RuntimeError("U4 topological proposal intersects native F.Cu")
    result=dict(report)
    result.update({
        "U4_pad_centres_mm":ports,
        "U3_pad7_UUID":U3_PAD7_UUID,
        "U3_pad7_bounds_mm":u3_bounds,
        "CH027_protected_UUIDs":sorted(
            tr.m_Uuid.AsString() for tr in fixed_ch027),
        "fanout_paths_mm":wires,
        "transition_mm":max(
            abs(wires[i][-1][normal_axis]-ports[i][normal_axis])
            for i in range(3))-BUNDLE_MM,
        "native_obstacle_preflight_passed":True,
        "fixed_copper_unchanged":True,
    })
    return wires,tuple(sides),direction,result

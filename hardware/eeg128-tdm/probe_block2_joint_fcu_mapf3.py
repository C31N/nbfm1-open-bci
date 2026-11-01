#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded genuine three-agent joint-state A* on native KiCad F.Cu.

One priority queue contains ALL three heads plus EACH full committed partial
copper path. This is not a sequential A*, and it does not reserve corridors
as hard obstacles before searching. Existing CH038 restitution and all fixed
copper are native obstacles. No via transitions or In1.Cu allowed.
A result is a geometric hypothesis ONLY; independent KiCad DRC is mandatory.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from typing import Any, Callable

Node = tuple[int, int]
GridPath = tuple[Node, ...]
MultiPath = tuple[GridPath, GridPath, GridPath]
Point = tuple[float, float]
Progress = Callable[[str, dict[str, Any]], None]


def simultaneous_fcu_astar3(
    board: Any,
    endpoints: tuple[tuple[Point, Point], ...],
    nets: tuple[int, int, int],
    *,
    grid_mm: float = .30,
    max_states: int = 12000,
    seconds: float = 105.0,
    progress: Progress | None = None,
) -> tuple[list[list[tuple[int, float, float]]] | None, dict[str, Any]]:
    import pcbnew
    import numpy as np
    from shapely import contains_xy, prepare
    from shapely.geometry import LineString, box, Point as ShapelyPoint
    from route_targeted_closure import obstacles

    if len(endpoints) != 3 or len(nets) != 3 or len(set(nets)) != 3:
        raise ValueError("Exactly three unique target netcodes required")
    if not (.18 <= grid_mm <= .44 and 300 <= max_states <= 20000
            and 10 <= seconds <= 150):
        raise ValueError("Unreviewed MAPF3 grid/time/node budget")
    started = time.monotonic()
    points = [p for pair in endpoints for p in pair]
    bounds = board.GetBoardEdgesBoundingBox()
    pad = .56
    x0 = max(min(x for x, _ in points)-3.2,
             pcbnew.ToMM(bounds.GetX())+pad)
    x1 = min(max(x for x, _ in points)+3.2,
             pcbnew.ToMM(bounds.GetRight())-pad)
    y0 = max(min(y for _, y in points)-3.2,
             pcbnew.ToMM(bounds.GetY())+pad)
    y1 = min(max(y for _, y in points)+3.2,
             pcbnew.ToMM(bounds.GetBottom())-pad)
    xs=np.arange(x0,x1+grid_mm/2,grid_mm)
    ys=np.arange(y0,y1+grid_mm/2,grid_mm)
    if len(xs)<3 or len(ys)<3:
        return None, {"status":"no_joint_grid"}
    xx, yy=np.meshgrid(xs,ys)
    bbox=box(x0,y0,x1,y1)
    masks=[]
    shapes=[]
    if progress:
        progress("mapf3_native_obstacles_started",
                 {"grid_shape":[len(xs),len(ys)]})
    for agent,net in enumerate(nets):
        native_shapes,_=obstacles(
            board,net,.15,.15,bbox,.65,
            (pcbnew.F_Cu,pcbnew.B_Cu))
        shape=native_shapes[0].buffer(-1e-9)
        prepare(shape)
        masks.append(contains_xy(shape,xx,yy))
        shapes.append(shape)
        if progress:
            progress("mapf3_native_agent_obstacles_finished",
                     {"agent":agent})
    def coord(n: Node) -> Point:
        return (float(xs[n[0]]),float(ys[n[1]]))
    def anchor(which: int, point: Point) -> Node | None:
        ix=int(round((point[0]-x0)/grid_mm))
        iy=int(round((point[1]-y0)/grid_mm))
        near=((x,y) for x in range(max(0,ix-3),min(len(xs),ix+4))
              for y in range(max(0,iy-3),min(len(ys),iy+4))
              if not masks[which][y,x])
        for n in sorted(near,key=lambda n:math.dist(coord(n),point)):
            if not LineString((point,coord(n))).relate_pattern(
                    shapes[which],"T********"):
                return n
        return None
    starts=[anchor(i,p[0]) for i,p in enumerate(endpoints)]
    goals=[anchor(i,p[1]) for i,p in enumerate(endpoints)]
    diag:dict[str,Any]={
        "status":"joint_mapf3_prepared",
        "grid_shape":[len(xs),len(ys)],
        "grid_mm":grid_mm, "max_joint_states":max_states,
        "start_anchors":starts, "goal_anchors":goals,
        "three_agents_joint":True,
        "all_partial_paths_in_one_state":True,
        "CH038_replacement_preplaced":True,
        "new_vias_added":0, "qualified":False,
    }
    if any(v is None for v in starts+goals):
        diag["status"]="joint_3_escapes_missing"
        return None,diag
    starts3=(starts[0],starts[1],starts[2])
    goals3=(goals[0],goals[1],goals[2])
    def segs(path:GridPath) -> list[Any]:
        if len(path)==1:
            return [ShapelyPoint(coord(path[0]))]
        return [LineString((coord(a),coord(b)))
                for a,b in zip(path,path[1:])]
    def collision(from_pt: Node,to_pt: Node,
                  others: tuple[GridPath,...]) -> bool:
        proposed=LineString((coord(from_pt),coord(to_pt)))
        for other in others:
            for segment in segs(other):
                if proposed.distance(segment)<.301:
                    return True
        return False
    def heuristic(heads:tuple[Node,Node,Node]) -> float:
        return sum(math.dist(coord(heads[i]),coord(goals3[i]))
                   for i in range(3))
    paths:MultiPath=((starts3[0],),(starts3[1],),(starts3[2],))
    initial=(starts3,paths,0)
    seq=itertools.count()
    q=[(heuristic(starts3),next(seq),0.0,initial)]
    visited=set()
    moves=((1,0),(-1,0),(0,1),(0,-1),
           (1,1),(1,-1),(-1,1),(-1,-1))
    expanded=0
    if progress:
        progress("mapf3_shared_queue_started",
                 {"start_anchors":starts,"goal_anchors":goals})
    while q and expanded<max_states:
        if time.monotonic()-started>seconds:
            diag["status"]="joint_3_wall_budget_exhausted"
            break
        _,_,g,(heads,partial,turn)=heapq.heappop(q)
        ident=(partial,turn)
        if ident in visited:
            continue
        visited.add(ident)
        expanded+=1
        if all(heads[i]==goals3[i] for i in range(3)):
            result=[
                [(0,*endpoints[i][0])]
                +[(0,*coord(pt)) for pt in partial[i]]
                +[(0,*endpoints[i][1])]
                for i in range(3)]
            diag.update(status="joint_three_FCu_paths_found_unverified",
                        expanded_joint_states=expanded,
                        wall_s=round(time.monotonic()-started,3))
            return result,diag
        index=next((i for d in range(3)
                    if (i:=(turn+d)%3) >= 0 and heads[i]!=goals3[i]),
                   None)
        if index is None:
            continue
        head=heads[index]
        other_paths=tuple(partial[j] for j in range(3) if j!=index)
        for dx,dy in moves:
            nxt=(head[0]+dx,head[1]+dy)
            x,y=nxt
            if not (0<=x<len(xs) and 0<=y<len(ys)):
                continue
            if masks[index][y,x] or nxt in partial[index]:
                continue
            if dx and dy and (masks[index][head[1],x]
                              or masks[index][y,head[0]]):
                continue
            if collision(head,nxt,other_paths):
                continue
            next_heads=list(heads)
            next_heads[index]=nxt
            next_paths=list(partial)
            next_paths[index]=partial[index]+(nxt,)
            heads2=(next_heads[0],next_heads[1],next_heads[2])
            paths2=(next_paths[0],next_paths[1],next_paths[2])
            g2=g+grid_mm*math.hypot(dx,dy)
            heapq.heappush(q,(
                g2+heuristic(heads2),next(seq),g2,
                (heads2,paths2,(index+1)%3)))
        if progress and expanded%1000==0:
            progress("mapf3_shared_queue_progress",
                     {"expanded_joint_states":expanded,
                      "queue_size":len(q),
                      "wall_s":round(time.monotonic()-started,3)})
    else:
        diag["status"]="joint_3_state_budget_exhausted"
    diag.update(expanded_joint_states=expanded,
                queue_size=len(q),
                wall_s=round(time.monotonic()-started,3))
    return None,diag

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded spatial conflict-based search for three F.Cu target nets.

CBS nodes hold three complete candidate paths and a growing set of exact
forbidden GRID EDGES for each agent. The first sub-clearance segment conflict
branches twice: ban the involved edge for one net OR for the other net, then
rerun low-level A* for only that net. All fixed original copper (including
native-DRC-verified CH038 return) remains an immutable KiCad obstacle.
This is a scratch-only proposal; native DRC and victim restitution are still
required separately. No new vias, no In1.Cu, no fabrication output.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from typing import Any, Callable

Point = tuple[float, float]
GridNode = tuple[int, int]
GridPath = tuple[GridNode, ...]
GridEdge = tuple[GridNode, GridNode]
Progress = Callable[[str, dict[str, Any]], None]


def spatial_cbs_fcu3(
    board: Any,
    endpoints: tuple[tuple[Point, Point], ...],
    nets: tuple[int, int, int],
    *,
    step_mm: float = .30,
    max_cbs_nodes: int = 90,
    max_lowlevel_nodes: int = 18000,
    seconds: float = 105,
    selection: str = "length",
    split_mode: str = "single-edge",
    progress: Progress | None = None,
) -> tuple[list[list[tuple[int, float, float]]] | None, dict[str, Any]]:
    import pcbnew
    import numpy as np
    from shapely import contains_xy, prepare
    from shapely.geometry import LineString, box
    from route_targeted_closure import obstacles

    if len(endpoints) != 3 or len(nets) != 3 or len(set(nets)) != 3:
        raise ValueError("CBS requires exactly three distinct target nets")
    if not (.19 <= step_mm <= .44 and 5 <= max_cbs_nodes <= 1200
            and 1000 <= max_lowlevel_nodes <= 50000
            and 10 <= seconds <= 150
            and selection in ("length", "conflict-volume")
            and split_mode in ("single-edge", "corridor-bundle")):
        raise ValueError("Unreviewed bounded CBS parameter")
    started = time.monotonic()
    all_ends = [xy for pair in endpoints for xy in pair]
    limits = board.GetBoardEdgesBoundingBox()
    margin = .56
    x0 = max(min(x for x, _ in all_ends)-3.2,
             pcbnew.ToMM(limits.GetX())+margin)
    x1 = min(max(x for x, _ in all_ends)+3.2,
             pcbnew.ToMM(limits.GetRight())-margin)
    y0 = max(min(y for _, y in all_ends)-3.2,
             pcbnew.ToMM(limits.GetY())+margin)
    y1 = min(max(y for _, y in all_ends)+3.2,
             pcbnew.ToMM(limits.GetBottom())-margin)
    xs = np.arange(x0, x1+step_mm/2, step_mm)
    ys = np.arange(y0, y1+step_mm/2, step_mm)
    if len(xs) < 3 or len(ys) < 3:
        return None, {"status": "spatial_CBS_no_grid"}
    gx, gy = np.meshgrid(xs, ys)
    bbox = box(x0,y0,x1,y1)
    masks=[]
    shapes=[]
    if progress:
        progress("CBS3_fixed_copper_obstacles_started",
                 {"grid_shape":[len(xs),len(ys)]})
    for i, net in enumerate(nets):
        geometry, _ = obstacles(
            board, net, .15, .15, bbox, .65,
            (pcbnew.F_Cu, pcbnew.B_Cu))
        shape = geometry[0].buffer(-1e-9)
        prepare(shape)
        shapes.append(shape)
        masks.append(contains_xy(shape,gx,gy))
        if progress:
            progress("CBS3_fixed_copper_agent_done",{"agent":i})

    def physical(node: GridNode) -> Point:
        return float(xs[node[0]]), float(ys[node[1]])

    def find_anchor(i: int, pt: Point) -> GridNode | None:
        ix=int(round((pt[0]-x0)/step_mm))
        iy=int(round((pt[1]-y0)/step_mm))
        nodes=((x,y) for x in range(max(0,ix-3),min(len(xs),ix+4))
               for y in range(max(0,iy-3),min(len(ys),iy+4))
               if not masks[i][y,x])
        for node in sorted(nodes,key=lambda q:math.dist(physical(q),pt)):
            if not LineString((pt,physical(node))).relate_pattern(
                    shapes[i],"T********"):
                return node
        return None
    start=[find_anchor(i,endpoints[i][0]) for i in range(3)]
    goal=[find_anchor(i,endpoints[i][1]) for i in range(3)]
    diag:dict[str,Any]={
        "status":"CBS3_prepared", "grid_shape":[len(xs),len(ys)],
        "step_mm":step_mm, "max_cbs_nodes":max_cbs_nodes,
        "selection":selection,
        "split_mode":split_mode,
        "start_anchors":start, "goal_anchors":goal,
        "simultaneous_three_net_conflict_search":True,
        "CH038_return_preplaced":True, "qualified":False,
        "new_vias_added":0,
        "expanded_cbs_nodes":0, "expanded_lowlevel_nodes":0,
        "resolved_conflicts":0,
    }
    if any(q is None for q in start+goal):
        diag["status"]="CBS3_endpoint_escape_blocked"
        return None,diag

    def edge(a: GridNode,b: GridNode) -> GridEdge:
        return (a,b) if a <= b else (b,a)

    moves=((1,0),(-1,0),(0,1),(0,-1),
           (1,1),(1,-1),(-1,1),(-1,-1))
    counter=itertools.count()
    def low_level(agent:int, forbidden:frozenset[GridEdge]) -> GridPath | None:
        first=start[agent]
        last=goal[agent]
        mask=masks[agent]
        q=[(math.dist(physical(first),physical(last)),
            next(counter),0.0,first)]
        cost={first:0.0}
        parents:dict[GridNode,GridNode | None]={first:None}
        expanded=0
        while q and expanded<max_lowlevel_nodes:
            if time.monotonic()-started >= seconds:
                return None
            _,_,g,node=heapq.heappop(q)
            if g!=cost[node]:
                continue
            expanded+=1
            if node==last:
                path=[]
                p:GridNode | None=node
                while p is not None:
                    path.append(p)
                    p=parents[p]
                diag["expanded_lowlevel_nodes"]+=expanded
                return tuple(reversed(path))
            for dx,dy in moves:
                nxt=(node[0]+dx,node[1]+dy)
                x,y=nxt
                if not (0<=x<len(xs) and 0<=y<len(ys)):
                    continue
                if mask[y,x] or edge(node,nxt) in forbidden:
                    continue
                if dx and dy and (mask[node[1],x] or mask[y,node[0]]):
                    continue
                g2=g+step_mm*math.hypot(dx,dy)
                if g2<cost.get(nxt,float("inf")):
                    cost[nxt]=g2
                    parents[nxt]=node
                    h=math.dist(physical(nxt),physical(last))
                    heapq.heappush(q,(g2+h,next(counter),g2,nxt))
        diag["expanded_lowlevel_nodes"]+=expanded
        return None

    def path_segments(agent:int,path:GridPath) -> list[tuple[Any,GridEdge]]:
        # For short exact-endpoint stubs, blame the adjacent grid edge in
        # CBS. All geometric results must still pass independent native DRC.
        if len(path)<2:
            return []
        nodes=[endpoints[agent][0]]+[physical(n) for n in path]+[
            endpoints[agent][1]]
        keys=[edge(path[0],path[1])]
        keys.extend(edge(a,b) for a,b in zip(path,path[1:]))
        keys.append(edge(path[-2],path[-1]))
        return [(LineString((a,b)),key)
                for (a,b),key in zip(zip(nodes,nodes[1:]),keys)]

    # Exact 0.300-mm centreline spacing is legal for 0.15-mm width plus
    # 0.15-mm native clearance; do not invent a 0.001-mm extra no-go band.
    # Independent KiCad DRC remains authoritative for all real copper.
    clearance_threshold = .300 - 1e-9
    def first_conflict(paths:tuple[GridPath,GridPath,GridPath]
                       ) -> tuple[int,int,GridEdge,GridEdge,float] | None:
        segs=[path_segments(i,paths[i]) for i in range(3)]
        for i in range(3):
            for j in range(i+1,3):
                line_i=LineString([endpoints[i][0]]
                                  +[physical(x) for x in paths[i]]
                                  +[endpoints[i][1]])
                line_j=LineString([endpoints[j][0]]
                                  +[physical(x) for x in paths[j]]
                                  +[endpoints[j][1]])
                if line_i.distance(line_j)>=clearance_threshold:
                    continue
                for gi,ki in segs[i]:
                    for gj,kj in segs[j]:
                        d=gi.distance(gj)
                        if d<clearance_threshold:
                            return i,j,ki,kj,d
        return None

    initial_paths=[]
    for i in range(3):
        path=low_level(i,frozenset())
        if path is None:
            diag["status"]="CBS3_individual_FCu_path_unavailable"
            diag["blocked_agent"]=i
            return None,diag
        initial_paths.append(path)
    paths0=(initial_paths[0],initial_paths[1],initial_paths[2])
    zero=(frozenset(),frozenset(),frozenset())
    def score(paths:tuple[GridPath,GridPath,GridPath]) -> float:
        length_cost = sum(len(p) for p in paths)
        if selection == "length":
            return float(length_cost)
        # Prioritize removing the *geometric conflict volume*, rather than
        # exploring hundreds of almost equal-length paths whose copper still
        # crosses. This mode changes search order, not route legalities.
        copper = [
            LineString([endpoints[i][0]]
                       +[physical(x) for x in paths[i]]
                       +[endpoints[i][1]]).buffer(.15, resolution=4)
            for i in range(3)]
        overlap = sum(
            copper[i].intersection(copper[j]).area
            for i in range(3) for j in range(i+1,3))
        return length_cost + 250.0*overlap
    q=[(score(paths0),next(counter),zero,paths0)]
    seen={zero}
    if progress:
        progress("CBS3_conflict_tree_started",
                 {"individual_path_nodes":[len(p) for p in paths0]})
    while q and diag["expanded_cbs_nodes"]<max_cbs_nodes:
        if time.monotonic()-started>=seconds:
            diag["status"]="CBS3_wall_budget_exhausted"
            break
        _,_,limits_by_net,paths=heapq.heappop(q)
        diag["expanded_cbs_nodes"]+=1
        conflict=first_conflict(paths)
        if conflict is None:
            result=[
                [(0,*endpoints[i][0])]
                +[(0,*physical(x)) for x in paths[i]]
                +[(0,*endpoints[i][1])]
                for i in range(3)]
            diag.update(
                status="CBS3_joint_FCu_candidate_unverified",
                candidate_path_grid_nodes=[len(p) for p in paths],
                wall_s=round(time.monotonic()-started,3))
            return result,diag
        i,j,ei,ej,dist=conflict
        diag["resolved_conflicts"]+=1
        diag["last_conflict"]={
            "net_index_pair":[i,j], "closest_clearance_mm":dist,
            "edge_a":ei, "edge_b":ej,
        }
        for agent,prohibited in ((i,ei),(j,ej)):
            # CBS normally bans exactly one conflicting edge on each branch.
            # The exploratory corridor-bundle mode bans *every* edge of the
            # presently occupied path that collides with the other complete
            # net. This is an aggressive, bounded conflict-directed heuristic,
            # not a proof of unsatisfiability if no path survives.
            forbidden_edges = frozenset((prohibited,))
            if split_mode == "corridor-bundle":
                counterpart = j if agent == i else i
                rival_line = LineString(
                    [endpoints[counterpart][0]]
                    + [physical(x) for x in paths[counterpart]]
                    + [endpoints[counterpart][1]])
                # Restrict the bundle to at most two edges around first conflict.
                # Banning all ~42 overlapping segments severed BOTH root
                # search branches in native run #2; this is a local conflict
                # direction choice, never a full corridor blackout.
                center_a = physical(prohibited[0])
                center_b = physical(prohibited[1])
                center = ((center_a[0]+center_b[0])/2,
                          (center_a[1]+center_b[1])/2)
                colliding = sorted(
                    ((math.dist(
                        ((physical(key[0])[0]+physical(key[1])[0])/2,
                         (physical(key[0])[1]+physical(key[1])[1])/2),
                        center), key)
                     for segment,key in path_segments(agent, paths[agent])
                     if segment.distance(rival_line) < clearance_threshold),
                    key=lambda item: item[0])
                local = [key for dist,key in colliding if dist <= 1.05]
                forbidden_edges |= frozenset(local[:2])
                diag["last_corridor_bundle_edge_count"] = len(forbidden_edges)
                diag["last_corridor_bundle_original_overlap_edges"] = len(colliding)
            newer=list(limits_by_net)
            newer[agent]=limits_by_net[agent] | forbidden_edges
            key=(newer[0],newer[1],newer[2])
            if key in seen:
                continue
            seen.add(key)
            reroute=low_level(agent,key[agent])
            if reroute is None:
                continue
            newpaths=list(paths)
            newpaths[agent]=reroute
            version=(newpaths[0],newpaths[1],newpaths[2])
            heapq.heappush(q,(score(version),next(counter),key,version))
        if progress and diag["expanded_cbs_nodes"]%10==0:
            progress("CBS3_conflict_tree_progress",{
                "expanded_cbs_nodes":diag["expanded_cbs_nodes"],
                "resolved_conflicts":diag["resolved_conflicts"],
                "queue_size":len(q),
                "last_conflict":diag["last_conflict"],
            })
    else:
        diag["status"]="CBS3_conflict_tree_budget_exhausted"
    diag.update(open_cbs_nodes=len(q),wall_s=round(time.monotonic()-started,3))
    return None,diag

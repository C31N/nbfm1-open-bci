#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded coupled target-pad escapes without premature lane consolidation.

The three native target pads are independent F.Cu sources. Candidate exits
are generated on both sides of the pad row and routed with raster A*.
As soon as a candidate is accepted, its full 0.150-mm copper plus 0.150-mm
clearance is an unrelaxable obstacle for the other two nets. Entire
speculative THREE-net states may backtrack; never mutate PCB copper.
"""
from __future__ import annotations

from collections import Counter
import itertools
import math
import time
from typing import Any

Point=tuple[float,float]
Wires=tuple[tuple[Point,...],...]


def coupled_target_open_space_escapes(
    masks:list[Any],shapes:list[Any],xs:Any,ys:Any,
    ports:tuple[Point,...],tangent:int,outward:float,
    *,deadline:float,max_expanded:int=170000,
) -> tuple[Wires|None,dict[str,Any]]:
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from probe_block2_u4_topological import _astar_grid

    if (len(masks)!=3 or len(shapes)!=3 or len(ports)!=3
            or tangent not in (0,1) or outward not in (-1.,1.)):
        raise ValueError("Invalid three-target topological source")
    normal=1-tangent
    dx=float(xs[1]-xs[0])
    dy=float(ys[1]-ys[0])
    if abs(dx-.15)>1e-5 or abs(dy-.15)>1e-5:
        raise ValueError("Target search grid pitch must be 0.150mm")
    budgets=Counter()
    order_failures=[]
    expanded_total=0
    best=0
    orders_started=0
    last_blocked_agent=None
    starts=[]
    initial=[]
    for i,port in enumerate(ports):
        px=int(round((port[0]-float(xs[0]))/.15))
        py=int(round((port[1]-float(ys[0]))/.15))
        potential=[]
        for yy in range(max(0,py-4),min(len(ys),py+5)):
            for xx in range(max(0,px-4),min(len(xs),px+5)):
                if masks[i][yy,xx]:
                    continue
                p=(float(xs[xx]),float(ys[yy]))
                gap=math.dist(port,p)
                if gap>.65:
                    continue
                if LineString((port,p)).relate_pattern(
                    shapes[i],"T********"):
                    continue
                potential.append((gap,xx,yy))
        if not potential:
            return None,{
                "status":"target_native_pad_anchor_blocked",
                "blocked_agent":i,
                "outcomes":{"no_native_pad_anchor":1},
                "best_routed_agents":0,
                "expanded_nodes":0,
                "geometry_unsatisfiable_proven":False,
            }
        _,xx,yy=min(potential)
        starts.append((xx,yy))
        initial.append((port,(float(xs[xx]),float(ys[yy]))))

    def candidate_goals(agent:int) -> list[tuple[int,int]]:
        port=ports[agent]
        candidates=[]
        for side in (outward,-outward):
            # Prefer pad exits farther into real F.Cu free space.
            # Near-pad anchors remain deterministic fallbacks.
            for d in (5.10,4.20,3.00,2.10,1.35):
                for side_offset in (0.,-.60,.60,-1.20,1.20,-1.80,1.80):
                    target=[port[0],port[1]]
                    target[normal]+=side*d
                    target[tangent]+=side_offset
                    x=int(round((target[0]-float(xs[0]))/.15))
                    y=int(round((target[1]-float(ys[0]))/.15))
                    if (4<=x<len(xs)-4 and 4<=y<len(ys)-4
                            and not masks[agent][y,x]):
                        candidates.append((x,y))
        # Remove duplicates while preserving deterministic preference.
        return list(dict.fromkeys(candidates))

    goal_lists=[candidate_goals(i) for i in range(3)]
    if any(not g for g in goal_lists):
        return None,{
            "status":"target_no_free_external_grid_goal",
            "goal_counts":[len(g) for g in goal_lists],
            "best_routed_agents":0,
            "geometry_unsatisfiable_proven":False,
        }

    def find_variant(
        agent:int,reserved:list[LineString],variant:int,
    ) -> tuple[tuple[Point,...]|None,str]:
        nonlocal expanded_total
        mask=masks[agent].copy()
        shape=shapes[agent]
        if reserved:
            copper=unary_union([
                line.buffer(.300-1e-9,resolution=8) for line in reserved])
            gx,gy=np.meshgrid(xs,ys)
            mask |= contains_xy(copper,gx,gy)
            shape=unary_union([shape,copper])
        start=starts[agent]
        if mask[start[1],start[0]]:
            budgets["reserved_pad_anchor_blocked"]+=1
            return None,"reserved_pad_anchor_blocked"
        goals=goal_lists[agent]
        # Four distinct deterministic subsequences, not four retries of
        # the same shortest path.
        selected=goals[variant::4]
        for goal in selected:
            if time.monotonic()>=deadline or expanded_total>=max_expanded:
                return None,"budget_exhausted"
            if mask[goal[1],goal[0]]:
                budgets["reserved_goal_blocked"]+=1
                continue
            route,why,n=_astar_grid(
                mask,start,goal,max_nodes=4600,deadline=deadline)
            expanded_total+=n
            budgets[why]+=1
            if route is None:
                continue
            wire=(ports[agent],)+tuple(
                (float(xs[x]),float(ys[y])) for x,y in route)
            line=LineString(wire)
            if line.relate_pattern(shape,"T********"):
                budgets["native_segment_collision"]+=1
                continue
            if any(line.distance(other)<.300-1e-8
                   for other in reserved):
                budgets["mutual_copper_separation_rejected"]+=1
                continue
            return wire,"path_found"
        return None,"candidate_frontier_exhausted"

    for ordering in itertools.permutations(range(3)):
        if time.monotonic()>=deadline or expanded_total>=max_expanded:
            break
        orders_started+=1
        routed:dict[int,tuple[Point,...]]={}
        reserved=[]
        order_causes=Counter()
        def recurse(depth:int)->bool:
            nonlocal best,last_blocked_agent
            if time.monotonic()>=deadline or expanded_total>=max_expanded:
                return False
            best=max(best,len(routed))
            if depth==3:
                return True
            agent=ordering[depth]
            for variant in range((3,2,1)[depth]):
                wire,why=find_variant(agent,reserved,variant)
                order_causes[why]+=1
                if wire is None:
                    last_blocked_agent=agent
                    continue
                line=LineString(wire)
                routed[agent]=wire
                reserved.append(line)
                budgets["target_paths_temporarily_reserved"]+=1
                if recurse(depth+1):
                    return True
                reserved.pop()
                del routed[agent]
                budgets["target_speculative_backtracks"]+=1
            return False
        if recurse(0):
            paths=(routed[0],routed[1],routed[2])
            gap=min(reserved[i].distance(reserved[j])
                    for i in range(3) for j in range(i+1,3))
            return paths,{
                "status":"target_three_independent_FCu_escapes_proposed",
                "successful_order":ordering,
                "orders_started":orders_started,
                "expanded_nodes":expanded_total,
                "minimum_centerline_mm":gap,
                "hard_clearance_centreline_mm":.300,
                "candidate_goals_per_agent":[len(g) for g in goal_lists],
                "outcomes":dict(budgets),
                "no_new_vias":True,
                "native_DRC_still_required":True,
            }
        order_failures.append({
            "ordering":ordering,
            "rejections":dict(order_causes),
        })
    return None,{
        "status":"target_coupled_topological_bounded_no_solution",
        "orders_started":orders_started,
        "expanded_nodes":expanded_total,
        "max_expanded_nodes":max_expanded,
        "candidate_goals_per_agent":[len(g) for g in goal_lists],
        "best_routed_agents":best,
        "last_blocked_agent":last_blocked_agent,
        "search_wall_budget_exhausted":time.monotonic()>=deadline,
        "outcomes":dict(budgets),
        "sample_failed_orders":order_failures[:6],
        "geometry_unsatisfiable_proven":False,
    }

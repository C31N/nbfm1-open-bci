#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""No-release sequential / local rip-up / local joint corridor preflight.

Only scratch route proposals are modified. The ORIGINAL PCB, the frozen
U4 and target escape paths, and all unrelated copper are never changed.
Every success needs three complete Shapely-checked F.Cu trajectories;
the independent native DRC and 201-victim gates remain mandatory.
"""
from __future__ import annotations

from collections import Counter
import itertools
import math
import time
from typing import Any

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString,Point as ShapePoint
from shapely.ops import unary_union

from probe_block2_joint_topology_costs import (
    PlanarOrderFilter,WindowBox,conflict_window,
)
from probe_block2_u4_topological import _astar_grid
from joint_start_anchor_resolver import resolve_window_anchors
from local_joint_rip_reroute import reassemble_speculative_outside
from local_joint_anchor_preflight import preflight_joint_entry_exit

Node=tuple[int,int]
Paths=tuple[tuple[Node,...],...]


def _line(path:tuple[Node,...],xs:Any,ys:Any,
          tips:tuple[tuple[float,float],tuple[float,float]])->LineString:
    return LineString((tips[0],)+tuple(
        (float(xs[x]),float(ys[y])) for x,y in path)+(tips[1],))


def _valid_three(paths:Paths,shapes:tuple[Any,...],
                 xs:Any,ys:Any,tips:tuple[Any,...]
                 )->tuple[bool,float]:
    if len(paths)!=3 or any(len(p)<2 for p in paths):
        return False,0.
    wires=[_line(paths[i],xs,ys,tips[i]) for i in range(3)]
    if any(w.intersects(shapes[i]) or not w.is_valid
           for i,w in enumerate(wires)):
        return False,0.
    gap=min(wires[i].distance(wires[j])
            for i in range(3) for j in range(i+1,3))
    return gap>=.300-1e-8,gap


def _window_slices(path:tuple[Node,...],xs:Any,ys:Any,
                   window:WindowBox)->tuple[int,int]|None:
    inside=[k for k,(x,y) in enumerate(path)
            if window.contains((float(xs[x]),float(ys[y])))]
    if not inside:
        return None
    return inside[0],inside[-1]


def hybrid_fcu_preflight(
    masks:list[Any],shapes:list[Any],xs:Any,ys:Any,
    starts:tuple[Node,Node,Node],goals:tuple[Node,Node,Node],
    exact_tips:tuple[Any,...], *,
    hotspot:tuple[float,float]=(48.145,35.750),
    half_window_mm:float=2.5,
    budget_seconds:float=12.,
)->tuple[Paths|None,dict[str,Any]]:
    if (len(masks)!=3 or len(shapes)!=3 or len(starts)!=3
            or len(goals)!=3 or len(exact_tips)!=3):
        raise ValueError("Three nets and immutable endpoints required")
    started=time.monotonic()
    deadline=started+budget_seconds
    gx,gy=np.meshgrid(xs,ys)
    window=conflict_window(hotspot,half_window_mm)
    native_shapes=tuple(shapes)
    counters={"sequential_attempts":0,"sequential_solved_agents":0,
              "local_rip_cycles":0,"local_joint_expansions":0,
              "anchor_retry_expansions":0}
    anchor_reasons:Counter[str]=Counter()
    anchor_trials:list[dict[str,Any]]=[]
    def point(node:Node)->tuple[float,float]:
        return float(xs[node[0]]),float(ys[node[1]])
    sources=tuple(point(p) for p in starts)
    targets=tuple(point(p) for p in goals)
    dx=sum(b[0]-a[0] for a,b in zip(sources,targets))
    dy=sum(b[1]-a[1] for a,b in zip(sources,targets))
    order=PlanarOrderFilter(
        sources,targets,(-dy,dx) if math.hypot(dx,dy)>1e-9 else (0.,1.),
        certified_monotone_region=False,inversion_weight=.08)
    soft_guidance={
        "planar_order_endpoints_agree":order.start_goal_order_matches,
        "planar_order_hard_pruning":order.hard,
        "planar_order_soft_preference_only":not order.hard,
        "joint_wall_cost_on_preinflated_shapes":True,
    }
    individual:dict[int,tuple[Node,...]]={}
    best_partial:dict[int,tuple[Node,...]]={}

    def route_one(
        agent:int,begin:Node,end:Node,
        reserved:list[LineString],
        *,restrict_to_window:bool=False,
    )->tuple[Node,...]|None:
        if time.monotonic()>=deadline:
            return None
        blocked=np.asarray(masks[agent],dtype=bool).copy()
        obstacles=native_shapes[agent]
        if reserved:
            region=unary_union([w.buffer(.300-1e-9,quad_segs=8)
                                for w in reserved])
            blocked|=contains_xy(region,gx,gy)
            obstacles=obstacles.union(region)
        if restrict_to_window:
            in_window=(gx>=window.xmin)&(gx<=window.xmax)&(
                gy>=window.ymin)&(gy<=window.ymax)
            blocked|=~in_window
        if blocked[begin[1],begin[0]] or blocked[end[1],end[0]]:
            anchor_reasons["endpoint_masked"]+=1
            return None
        result,reason,expanded= _astar_grid(
            blocked,begin,end,max_nodes=1600,deadline=deadline)
        anchor_reasons[reason]+=1
        if len(anchor_trials)<32:
            anchor_trials.append({
                "agent":agent,"stage":(
                    "window" if restrict_to_window else "global"),
                "method":"A_star_1600","result":reason,"expansions":expanded})
        # Budget exhaustion alone is not proof of a missing F.Cu passage.
        # Retry only on the unchanged hard masks and only within the
        # existing time budget; never invent endpoints or remove obstacles.
        if reason=="node_budget_exhausted" and time.monotonic()<deadline:
            retried,why,nodes=_astar_grid(
                blocked,begin,end,max_nodes=6400,deadline=deadline)
            counters["anchor_retry_expansions"]+=nodes
            anchor_reasons["retry_"+why]+=1
            if len(anchor_trials)<32:
                anchor_trials.append({
                    "agent":agent,"stage":(
                        "window" if restrict_to_window else "global"),
                    "method":"A_star_6400","result":why,"expansions":nodes})
            result=retried
        if result is None:
            return None
        points=tuple(result)
        # Full native segment collision, including off-grid diagonal
        # corner cutting. Own sources remain on the original net.
        line=LineString(tuple((float(xs[x]),float(ys[y]))
                              for x,y in points))
        if line.intersects(obstacles):
            anchor_reasons["continuous_native_copper_collision"]+=1
            return None
        return points

    # Stage 1: try all six orders with HARD 0.300-mm copper reservation.
    for order in itertools.permutations(range(3)):
        if time.monotonic()>=deadline:
            break
        paths={}
        wires=[]
        for agent in order:
            counters["sequential_attempts"]+=1
            p=route_one(agent,starts[agent],goals[agent],wires)
            if p is None:
                break
            line=_line(p,xs,ys,exact_tips[agent])
            if (line.intersects(native_shapes[agent]) or
                    any(line.distance(other)<.300-1e-8
                        for other in wires)):
                break
            paths[agent]=p
            wires.append(line)
        if len(paths)>len(best_partial):
            best_partial=dict(paths)
        counters["sequential_solved_agents"]=max(
            counters["sequential_solved_agents"],len(paths))
        if len(paths)==3:
            proposal=tuple(paths[i] for i in range(3))
            ok,gap=_valid_three(
                proposal,native_shapes,xs,ys,exact_tips)
            if ok:
                return proposal,{
                    "status":"hybrid_three_native_macros_proposed",
                    "stage_used":"sequential",
                    "local_joint_expansions":0,
                    "minimum_complete_centreline_mm":gap,
                    "new_vias_added":0,"native_DRC_still_required":True,
                    "anchor_a_star_reasons":dict(anchor_reasons),
                    "anchor_attempts":anchor_trials,
                    **soft_guidance,**counters}
    # Collect independent source-to-target paths solely as speculative
    # anchors. They are NOT simultaneously legal copper.
    for agent in range(3):
        if time.monotonic()>=deadline:
            break
        path=route_one(agent,starts[agent],goals[agent],[])
        if path is not None:
            individual[agent]=path

    # Stage 2: modify ONLY the path section intersecting WindowBox.
    if len(individual)==3:
        for victim in range(3):
            if time.monotonic()>=deadline:
                break
            vpath=individual[victim]
            span=_window_slices(vpath,xs,ys,window)
            if span is None or span[1]<=span[0]:
                continue
            first,last=span
            # No pad/escape endpoints can be ripped or moved.
            if first==0 or last>=len(vpath)-1:
                continue
            counters["local_rip_cycles"]+=1
            reserves=[_line(individual[i],xs,ys,exact_tips[i])
                      for i in range(3) if i!=victim]
            inner=route_one(
                victim,vpath[first],vpath[last],reserves,
                restrict_to_window=True)
            if inner is None:
                continue
            candidate=dict(individual)
            candidate[victim]=(
                vpath[:first]+inner+vpath[last+1:])
            triple=tuple(candidate[i] for i in range(3))
            ok,gap=_valid_three(
                triple,native_shapes,xs,ys,exact_tips)
            if ok:
                return triple,{
                    "status":"hybrid_three_native_macros_proposed",
                    "stage_used":"local_rip_reroute",
                    "local_joint_expansions":0,
                    "minimum_complete_centreline_mm":gap,
                    "new_vias_added":0,"native_DRC_still_required":True,
                    "anchor_a_star_reasons":dict(anchor_reasons),
                    "anchor_attempts":anchor_trials,
                    **soft_guidance,**counters}

    # Stage 3: coupled joint-search over several individually valid
    # source/target combinations. The independently found outside paths are
    # only search hints; immutable native copper remains in hard shapes.
    spans={i:_window_slices(p,xs,ys,window)
           for i,p in individual.items()}
    local_joint_status="not_attempted_missing_bounded_anchors"
    local_joint_reject_reasons:dict[str,Any]={}
    local_joint_anchor_audit:dict[str,Any]={}
    outside_replan_diagnostic:dict[str,Any]={}
    anchor_resolution=None
    if len(spans)==3 and all(v is not None and
                             0<v[0]<v[1]<len(individual[i])-1
                             for i,v in spans.items()):
        from probe_block2_elastic_joint_corridor import (
            ElasticJointCorridorRouter,FCuCorridorGrid,
        )
        from collections import Counter as RejectCounter
        preflight_rejections:RejectCounter[str]=RejectCounter()
        solver_rejections:RejectCounter[str]=RejectCounter()
        local_joint_attempts:list[dict[str,Any]]=[]
        selected_spans=tuple(spans[i] for i in range(3))
        individual_paths=tuple(individual[i] for i in range(3))
        anchor_resolution=resolve_window_anchors(
            individual_paths,selected_spans,masks,native_shapes,
            xs,ys,window,max_shift_nodes=4,max_side_triplets=12,
            max_solutions=4,min_anchor_pitch_mm=.440,
        )
        local_joint_anchor_audit={
            "conservative_resolver":anchor_resolution.as_diagnostic()}
        if not anchor_resolution.candidate_pairs:
            # A speculative route is not actual copper. Discard the
            # conflicting outer portions but keep every native obstacle.
            anchor_resolution=resolve_window_anchors(
                individual_paths,selected_spans,masks,native_shapes,
                xs,ys,window,max_shift_nodes=4,max_side_triplets=12,
                speculative_outside=True,max_solutions=4,
                min_anchor_pitch_mm=.440,
            )
            local_joint_anchor_audit["speculative_resolver"]=(
                anchor_resolution.as_diagnostic())
        local_joint_anchor_audit["final_resolver"]=(
            anchor_resolution.as_diagnostic())
        allowed=(gx>=window.xmin)&(gx<=window.xmax)&(
            gy>=window.ymin)&(gy<=window.ymax)
        # Keep total local expansions bounded across every anchor pair,
        # not 4,800 per pair. A budget exhausts without PCB writes.
        remaining_nodes=4800
        for attempt_index,(source_idxs,target_idxs) in enumerate(
                anchor_resolution.candidate_pairs):
            if time.monotonic()>=deadline or remaining_nodes<=0:
                break
            current_spans={
                i:(source_idxs[i],target_idxs[i]) for i in range(3)}
            local_masks=[]
            local_shapes=[]
            starts_local=[]
            goals_local=[]
            tips_local=[]
            for i in range(3):
                a,b=current_spans[i]
                route=individual[i]
                static_other=[]
                if not anchor_resolution.outside_paths_speculative:
                    for j in range(3):
                        if j==i:
                            continue
                        a2,b2=current_spans[j]
                        outside=[
                            individual[j][:a2+1],
                            individual[j][b2:],
                        ]
                        static_other += [
                            LineString([
                                (float(xs[x]),float(ys[y]))
                                for x,y in seg]).buffer(
                                    .300-1e-9,quad_segs=8)
                            for seg in outside if len(seg)>=2
                        ]
                foreign=unary_union(static_other) if static_other else None
                shape=(native_shapes[i].union(foreign)
                       if foreign is not None else native_shapes[i])
                local_masks.append(
                    np.asarray(masks[i],dtype=bool) |
                    ~allowed |
                    (contains_xy(foreign,gx,gy)
                     if foreign is not None else False))
                local_shapes.append(shape)
                starts_local.append(route[a])
                goals_local.append(route[b])
                tips_local.append((
                    (float(xs[route[a][0]]),float(ys[route[a][1]])),
                    (float(xs[route[b][0]]),float(ys[route[b][1]]))))
            grid=FCuCorridorGrid(local_masks,local_shapes,xs,ys)
            preflight=preflight_joint_entry_exit(
                grid,tuple(starts_local),tuple(goals_local))
            preflight_rejections.update(preflight["reject_reasons"])
            attempt={
                "ordinal":attempt_index+1,
                "source_indices":list(source_idxs),
                "target_indices":list(target_idxs),
                "start_pitch_mm":round(min(
                    math.dist(point(starts_local[i]),point(starts_local[j]))
                    for i in range(3) for j in range(i+1,3)),6),
                "target_pitch_mm":round(min(
                    math.dist(point(goals_local[i]),point(goals_local[j]))
                    for i in range(3) for j in range(i+1,3)),6),
                "first_step":preflight,
                "fixed_outside_paths_preserved":(
                    not anchor_resolution.outside_paths_speculative),
            }
            if preflight["status"]!="JOINT_ANCHOR_FIRST_STEP_FEASIBLE":
                attempt["status"]=preflight["status"]
                attempt["expansions"]=0
                local_joint_attempts.append(attempt)
                continue
            remaining=max(.1,deadline-time.monotonic())
            # Limit each attempt, reserving time and nodes for the next.
            search_nodes=min(1200,remaining_nodes)
            solver=ElasticJointCorridorRouter(grid)
            result=solver.solve_midpoint(
                tuple(starts_local),tuple(goals_local),
                exact_tips=tuple(tips_local),
                max_expansions=search_nodes,
                max_seconds=min(2.3,remaining),
                midpoint_band_mm=.5)
            used=result["expansions"]
            remaining_nodes-=used
            counters["local_joint_expansions"]+=used
            solver_rejections.update(result.get("reject_reasons",{}))
            attempt["status"]=result["status"]
            attempt["expansions"]=used
            attempt["closest_remaining_total_mm"]=result.get(
                "closest_remaining_total_mm")
            local_joint_attempts.append(attempt)
            if result["status"]!="MIDPOINT_BUNDLE_SOLVED":
                continue
            if anchor_resolution.outside_paths_speculative:
                triple,outside_replan_diagnostic=(
                    reassemble_speculative_outside(
                        tuple(tuple(p) for p in result["routes"]),
                        starts,goals,exact_tips,native_shapes,
                        xs,ys,route_one,
                    ))
            else:
                out={}
                for i in range(3):
                    a,b=current_spans[i]
                    out[i]=individual[i][:a]+tuple(
                        result["routes"][i])+individual[i][b+1:]
                triple=tuple(out[i] for i in range(3))
            if triple is None:
                attempt["status"]=outside_replan_diagnostic.get(
                    "status","LOCAL_JOINT_ROLLBACK")
                continue
            ok,gap=_valid_three(
                triple,native_shapes,xs,ys,exact_tips)
            if ok:
                local_joint_anchor_audit.update({
                    "attempts":local_joint_attempts,
                    "attempted_anchor_pairs":len(local_joint_attempts),
                    "fixed_outside_paths_preserved":(
                        not anchor_resolution.outside_paths_speculative),
                    "locked_escape_ripup_permitted":False,
                })
                return triple,{
                    "status":"hybrid_three_native_macros_proposed",
                    "stage_used":"local_joint_astar",
                    "local_joint_expansions":counters["local_joint_expansions"],
                    "minimum_complete_centreline_mm":gap,
                    "new_vias_added":0,
                    "native_DRC_still_required":True,
                    "local_joint_anchor_audit":local_joint_anchor_audit,
                    "outside_replan_diagnostic":outside_replan_diagnostic,
                    "anchor_a_star_reasons":dict(anchor_reasons),
                    "anchor_attempts":anchor_trials,
                    **soft_guidance,**counters}
            attempt["status"]="LOCAL_JOINT_FULL_ROUTE_DRC_REJECTED"
        local_joint_anchor_audit.update({
            "attempts":local_joint_attempts,
            "attempted_anchor_pairs":len(local_joint_attempts),
            "selected_anchor_pairs":len(anchor_resolution.candidate_pairs),
            "first_step_reject_reasons":dict(preflight_rejections),
            "fixed_outside_paths_preserved":(
                not anchor_resolution.outside_paths_speculative),
            "locked_escape_ripup_permitted":False,
        })
        local_joint_reject_reasons=dict(solver_rejections)
        if local_joint_attempts:
            local_joint_status="MIDPOINT_MULTI_ANCHOR_EXHAUSTED"
        else:
            local_joint_status=anchor_resolution.status

    return None,{
        "status":"hybrid_unresolved_global_joint_fallback_required",
        "stage_used":"failed",
        "local_joint_expansions":counters["local_joint_expansions"],
        "speculative_partial_paths":len(best_partial),
        "individually_reachable_paths":len(individual),
        "local_window_mm":[window.xmin,window.ymin,
                           window.xmax,window.ymax],
        "local_joint_eligible":(
            anchor_resolution is not None
            and anchor_resolution.starts is not None),
        "wall_seconds":round(time.monotonic()-started,3),
        "anchor_a_star_reasons":dict(anchor_reasons),
        "anchor_attempts":anchor_trials,
        "independent_anchor_success_agents":sorted(individual),
        "local_joint_status":local_joint_status,
        "local_joint_anchor_audit":local_joint_anchor_audit,
        "outside_replan_diagnostic":outside_replan_diagnostic,
        "local_joint_reject_reasons":local_joint_reject_reasons,
        "multi_anchor_eligible_count":(
            len(anchor_resolution.candidate_pairs)
            if anchor_resolution is not None else 0),
        **soft_guidance,
        "new_vias_added":0,
        "native_DRC_still_required":True,
        "geometry_unsatisfiable_proven":False,
        **counters,
    }

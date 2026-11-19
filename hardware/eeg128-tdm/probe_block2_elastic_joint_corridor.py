#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Simultaneous, fail-closed three-net F.Cu joint corridor A* diagnosis.

Input masks are ALREADY inflated by physical track radius (0.075 mm) plus
clearance (0.150 mm). EDT is a width/branch heuristic only: no double
inflation. All proposed segments are checked against exact Shapely native
copper, and all three COMPLETE paths are checked against one another.
This module NEVER edits native board copper or changes release gates.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import heapq
import itertools
import json
import math
import time
from typing import Any, Sequence

from shapely.geometry import LineString, Point as ShapePoint

Node = tuple[int, int]
PITCH_MM = .300
TOL = 1e-8
DIRS: tuple[Node, ...] = (
    (1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1),
)


@dataclass(frozen=True)
class BundleState:
    p1: Node
    p2: Node
    p3: Node
    heading: int
    # Modes affect diagnostics, not which moves are legal from the
    # current geometric positions. Merge equivalent joint A* states.
    mode: str = field(compare=False)

    @property
    def points(self) -> tuple[Node,Node,Node]:
        return self.p1,self.p2,self.p3


class FCuCorridorGrid:
    """Native exact geometry and raster masks for three distinct net codes."""

    def __init__(
        self, masks: Sequence[Any], inflated_shapes: Sequence[Any],
        xs: Any, ys: Any,
    ) -> None:
        import numpy as np
        if len(masks)!=3 or len(inflated_shapes)!=3:
            raise ValueError("Exactly three per-net copper obstacle sets")
        self.xs=np.asarray(xs,dtype=float)
        self.ys=np.asarray(ys,dtype=float)
        if len(xs)<4 or len(ys)<4:
            raise ValueError("Empty joint search grid")
        self.res=float(self.xs[1]-self.xs[0])
        if (self.res<=0. or
                not np.allclose(np.diff(self.xs),self.res) or
                not np.allclose(np.diff(self.ys),self.res)):
            raise ValueError("Joint F.Cu grid must have square pixel pitch")
        self.masks=tuple(np.asarray(m,dtype=bool) for m in masks)
        if any(m.shape!=(len(self.ys),len(self.xs)) for m in self.masks):
            raise ValueError("Net mask dimensions drifted")
        self.shapes=tuple(inflated_shapes)
        self.width=len(self.xs)
        self.height=len(self.ys)
        self.edt_mm:tuple[Any,Any,Any]|None=None
        self.locked_escape_sha256:str|None=None

    def physical(self,p:Node)->tuple[float,float]:
        return float(self.xs[p[0]]),float(self.ys[p[1]])

    @staticmethod
    def canonical_sha256(segments:Sequence[Any])->str:
        payload=json.dumps(segments,separators=(",",":"),allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lock_escape_segments(self,segments:Sequence[Any])->str:
        self.locked_escape_sha256=self.canonical_sha256(segments)
        return self.locked_escape_sha256

    def verify_escape_integrity(self,segments:Sequence[Any])->bool:
        return (self.locked_escape_sha256 is not None and
                self.locked_escape_sha256==
                self.canonical_sha256(segments))

    def build_distance_field(self)->None:
        from scipy.ndimage import distance_transform_edt
        # Raster mask is already an exact-nominal inflated copper mask.
        # EDT is never used to weaken or replace the native Shapely check.
        self.edt_mm=tuple(
            distance_transform_edt(~mask,sampling=self.res)
            for mask in self.masks)

    def is_point_drc_clear(self,agent:int,p:Node)->bool:
        x,y=p
        return (0<=x<self.width and 0<=y<self.height
                and not self.masks[agent][y,x])

    def local_corridor_width_mm(self,points:tuple[Node,Node,Node])->float:
        if self.edt_mm is None:
            raise RuntimeError("EDT not initialized")
        if any(not self.is_point_drc_clear(i,p)
               for i,p in enumerate(points)):
            return 0.
        return min(
            float(self.edt_mm[i][p[1],p[0]])*2.
            for i,p in enumerate(points))

    def is_segment_drc_clear(self,agent:int,a:Node,b:Node)->bool:
        # A physical edge is bidirectional and immutable for the whole
        # scratch search. Cache exact native clearance without raster
        # approximation; this is purely a performance improvement.
        return self._exact_immutable_edge_clear(
            agent,min(a,b),max(a,b))

    @lru_cache(maxsize=180000)
    def _exact_immutable_edge_clear(
        self,agent:int,a:Node,b:Node,
    )->bool:
        if not (self.is_point_drc_clear(agent,a) and
                self.is_point_drc_clear(agent,b)):
            return False
        if a==b:
            return not ShapePoint(self.physical(a)).intersects(
                self.shapes[agent])
        segment=LineString((self.physical(a),self.physical(b)))
        return not segment.intersects(self.shapes[agent])


class ElasticJointCorridorRouter:
    """Bounded joint-state A*, with complete physical path validation."""

    def __init__(
        self,grid:FCuCorridorGrid,
        min_pitch_mm:float=PITCH_MM,
        parallel_threshold_mm:float=1.050,
        pinch_threshold_mm:float=.600,
    )->None:
        if abs(min_pitch_mm-PITCH_MM)>1e-9:
            raise ValueError("Cannot relax 0.300-mm centreline pitch")
        self.grid=grid
        self.pitch=min_pitch_mm
        self.parallel_threshold=parallel_threshold_mm
        self.pinch_threshold=pinch_threshold_mm
        self.stats:Counter[str]=Counter()

    def _distance(self,a:Node,b:Node)->float:
        return math.dist(self.grid.physical(a),self.grid.physical(b))

    def _classify(self,points:tuple[Node,Node,Node])->str:
        width=self.grid.local_corridor_width_mm(points)
        if width>=self.parallel_threshold:
            return "PARALLEL"
        if width<self.pinch_threshold:
            # EDT samples an ALREADY buffered obstacle raster: a local
            # diameter below 0.60 mm is only a search heuristic. Treating
            # it as a hard cut incorrectly rejected native-free source
            # anchors. Exact Shapely copper + segment pitch remain hard.
            self.stats["subthreshold_EDT_exact_geometry_only"]+=1
        return "STAGGERED_PINCH"

    def _check_transition(
        self,old:tuple[Node,Node,Node],
        new:tuple[Node,Node,Node],
    )->bool:
        lines=[]
        for i,(a,b) in enumerate(zip(old,new)):
            if not self.grid.is_segment_drc_clear(i,a,b):
                self.stats["native_fixed_copper_or_mask"]+=1
                return False
            lines.append(
                LineString((self.grid.physical(a),self.grid.physical(b)))
                if a!=b else ShapePoint(self.grid.physical(a)))
        # Only now are ALL three positions guaranteed to be inside the
        # PCB grid. Never project an unchecked neighbour to coordinates.
        for i in range(3):
            for j in range(i+1,3):
                if self._distance(new[i],new[j])<self.pitch-TOL:
                    self.stats["pairwise_point_pitch"]+=1
                    return False
        for i in range(3):
            for j in range(i+1,3):
                if lines[i].distance(lines[j])<self.pitch-TOL:
                    self.stats["continuous_segment_pitch"]+=1
                    return False
        return True

    def _neighbors(self,current:BundleState)->list[BundleState]:
        style=self._classify(current.points)
        if style=="BLOCKED":
            self.stats["blocked_by_corridor_width_heuristic"]+=1
            return []
        candidates=[]
        seen=set()
        # Whole-bundle translation is searched jointly. In narrow
        # corridors any one or two agents may advance while others hold.
        patterns=(
            (1,1,1),(1,0,0),(0,1,0),(0,0,1),
            (1,1,0),(0,1,1),(1,0,1)
        )
        for turn in (-2,-1,0,1,2):
            heading=(current.heading+turn)%8
            dx,dy=DIRS[heading]
            for pattern in patterns:
                if style=="PARALLEL" and pattern!=(1,1,1):
                    # Allow staggered motion even in wide corridors:
                    # the target pad separation need not be parallel.
                    if abs(turn)>1:
                        continue
                pts=tuple(
                    (p[0]+m*dx,p[1]+m*dy)
                    for p,m in zip(current.points,pattern))
                if pts in seen or not self._check_transition(
                    current.points,pts):
                    continue
                seen.add(pts)
                candidates.append(BundleState(
                    pts[0],pts[1],pts[2],heading,
                    ("PARALLEL" if pattern==(1,1,1)
                     and style=="PARALLEL" else "STAGGERED_PINCH")))
        return candidates

    def _heuristic(
        self,state:BundleState,goals:tuple[Node,Node,Node],
    )->float:
        # Euclidean lower bound. In the bounded multi-agent search it is
        # weighted in the priority queue to reduce indecisive detours.
        # Weighted A* may lose shortest-path optimality, NEVER clearance.
        return sum(self._distance(a,b)
                   for a,b in zip(state.points,goals))

    def _step_cost(self,a:BundleState,b:BundleState)->float:
        cost=sum(self._distance(x,y) for x,y in zip(a.points,b.points))
        steer=.015 if a.heading!=b.heading else 0.
        d01=abs(self._distance(b.p1,b.p2)-self.pitch)
        d12=abs(self._distance(b.p2,b.p3)-self.pitch)
        return cost+steer+.03*(d01+d12)

    @staticmethod
    def _reconstruct(
        parent:dict[BundleState,BundleState],end:BundleState,
    )->list[BundleState]:
        path=[end]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        return list(reversed(path))

    def _validate_whole_routes(
        self,paths:tuple[tuple[Node,...],...],
        exact_tips:tuple[tuple[tuple[float,float],
                               tuple[float,float]],...],
    )->tuple[bool,str,float]:
        lines=[]
        for i,route in enumerate(paths):
            points=(exact_tips[i][0],)+tuple(
                self.grid.physical(node) for node in route)+(
                    exact_tips[i][1],)
            line=LineString(points)
            if not line.is_valid or line.intersects(self.grid.shapes[i]):
                return False,"native_FCu_segment_collision",0.
            lines.append(line)
        gap=min(lines[i].distance(lines[j])
                for i in range(3) for j in range(i+1,3))
        if gap<self.pitch-TOL:
            return False,"full_three_route_pitch_violation",gap
        return True,"exact_unverified_FCu_geometry",gap

    def _rigid_simultaneous_astar(
        self,start:tuple[Node,Node,Node],
        goals:tuple[Node,Node,Node],
        *,deadline:float,max_nodes:int=8500,
    )->tuple[tuple[tuple[Node,...],...]|None,dict[str,Any]]:
        """Fast exact-coherent three-head A*: no independent net planning.

        Used only when target head offsets equal source head offsets.
        Every expansion translates all three traces and validates all
        three continuous segments against fixed copper and each other.
        """
        offsets=tuple((p[0]-start[0][0],p[1]-start[0][1])
                      for p in start)
        final_offsets=tuple((p[0]-goals[0][0],p[1]-goals[0][1])
                            for p in goals)
        if offsets!=final_offsets:
            return None,{"status":"rigid_goal_offsets_incompatible",
                         "expansions":0}
        def whole(lead:Node)->tuple[Node,Node,Node]:
            return tuple((lead[0]+d[0],lead[1]+d[1])
                         for d in offsets)
        begin=start[0]
        finish=goals[0]
        seq=itertools.count()
        heap=[(self._distance(begin,finish),next(seq),0.,begin)]
        g_score={begin:0.}
        parent:dict[Node,Node]={}
        expanded=0
        while heap and expanded<max_nodes and time.monotonic()<deadline:
            _,_,dist,node=heapq.heappop(heap)
            if dist>g_score[node]+1e-9:
                continue
            expanded+=1
            if node==finish:
                centres=[node]
                while centres[-1] in parent:
                    centres.append(parent[centres[-1]])
                centres.reverse()
                states=[whole(point) for point in centres]
                routes=tuple(tuple(t[i] for t in states)
                             for i in range(3))
                return routes,{
                    "status":"rigid_three_net_joint_path_found",
                    "expansions":expanded,
                    "states":len(states)}
            old=whole(node)
            for dx,dy in DIRS:
                nxt=(node[0]+dx,node[1]+dy)
                news=whole(nxt)
                if not self._check_transition(old,news):
                    continue
                new_g=dist+self._distance(node,nxt)*3.
                if new_g<g_score.get(nxt,math.inf)-1e-9:
                    g_score[nxt]=new_g
                    parent[nxt]=node
                    heuristic=self._distance(nxt,finish)*3.
                    heapq.heappush(heap,(
                        new_g+heuristic,next(seq),new_g,nxt))
        return None,{
            "status":("rigid_bundle_budget_exhausted"
                      if heap else "rigid_bundle_frontier_exhausted"),
            "expansions":expanded}

    def solve_midpoint(
        self,
        u4_anchors:tuple[Node,Node,Node],
        target_anchors:tuple[Node,Node,Node],
        *,
        exact_tips:tuple[tuple[tuple[float,float],
                               tuple[float,float]],...]|None=None,
        initial_heading:int|None=None,
        max_expansions:int=30000,
        max_seconds:float=48.,
    )->dict[str,Any]:
        if self.grid.edt_mm is None:
            self.grid.build_distance_field()
        started=time.monotonic()
        goals=tuple(target_anchors)
        if initial_heading is None:
            dx=sum(b[0]-a[0] for a,b in zip(
                u4_anchors,target_anchors))
            dy=sum(b[1]-a[1] for a,b in zip(
                u4_anchors,target_anchors))
            initial_heading=min(range(8),key=lambda h:
                -DIRS[h][0]*dx-DIRS[h][1]*dy)
        state=BundleState(*u4_anchors,heading=initial_heading,
                          mode="PARALLEL")
        diagnostic:dict[str,Any]={
            "status":"MIDPOINT_PINCH_CORRIDOR_EXHAUSTED",
            "closed_nets":0,
            "expansions":0,
            "checkpoint_preserved":139,
            "accepted":False,
            "routing_completed":False,
            "fabrication_release":False,
            "new_vias_added":0,
            "hard_centreline_pitch_mm":self.pitch,
            "grid_resolution_mm":self.grid.res,
            "EDT_mode_thresholds_mm":{
                "PARALLEL":self.parallel_threshold,
                "STAGGERED_PINCH":self.pinch_threshold},
            "native_DRC_still_required":True,
            "geometry_unsatisfiable_proven":False,
        }
        if not self._check_transition(state.points,state.points):
            diagnostic["status"]="MIDPOINT_JOINT_START_ANCHORS_INVALID"
            diagnostic["reject_reasons"]=dict(self.stats)
            return diagnostic
        if any(not self.grid.is_point_drc_clear(i,p)
               for i,p in enumerate(goals)):
            diagnostic["status"]="MIDPOINT_JOINT_TARGET_ANCHORS_INVALID"
            return diagnostic
        rigid_routes,rigid_diag=self._rigid_simultaneous_astar(
            tuple(u4_anchors),goals,
            deadline=started+min(8.,max_seconds*.30),
            max_nodes=8500)
        diagnostic["rigid_bundle_preflight"]=rigid_diag
        if rigid_routes is not None and exact_tips is not None:
            valid,reason,gap=self._validate_whole_routes(
                rigid_routes,exact_tips)
            if valid:
                diagnostic.update({
                    "status":"MIDPOINT_BUNDLE_SOLVED",
                    "closed_nets":3,
                    "routes":rigid_routes,
                    "minimum_complete_centreline_mm":gap,
                    "joint_states_in_solution":len(rigid_routes[0]),
                    "expansions":rigid_diag["expansions"],
                    "wall_seconds":round(time.monotonic()-started,3),
                    "search_mode":"RIGID_SIMULTANEOUS_A_STAR",
                    "reject_reasons":dict(self.stats),
                })
                return diagnostic
            self.stats[reason]+=1
        counter=itertools.count()
        heuristic_weight=1.65
        start_h=self._heuristic(state,goals)
        heap=[(start_h*heuristic_weight,0.,next(counter),state)]
        g_score={state:0.}
        parent:dict[BundleState,BundleState]={}
        expansions=0
        closest_remaining_mm=start_h
        closest_state=state
        while heap and expansions<max_expansions:
            if time.monotonic()-started>=max_seconds:
                diagnostic["status"]="MIDPOINT_JOINT_WALL_BUDGET_EXHAUSTED"
                break
            _,g,_,current=heapq.heappop(heap)
            if g>g_score.get(current,math.inf)+1e-9:
                continue
            expansions+=1
            remaining=self._heuristic(current,goals)
            if remaining<closest_remaining_mm:
                closest_remaining_mm=remaining
                closest_state=current
            if current.points==goals:
                chain=self._reconstruct(parent,current)
                paths=tuple(
                    tuple(state.points[i] for state in chain)
                    for i in range(3))
                if exact_tips is not None:
                    valid,reason,gap=self._validate_whole_routes(
                        paths,exact_tips)
                    if not valid:
                        self.stats[reason]+=1
                        # Continue finding other joint proposals rather
                        # than ever declaring an unsafe route as solved.
                        continue
                else:
                    self.stats["missing_exact_native_tips"]+=1
                    break
                diagnostic.update({
                    "status":"MIDPOINT_BUNDLE_SOLVED",
                    "closed_nets":3,
                    "routes":paths,
                    "minimum_complete_centreline_mm":gap,
                    "joint_states_in_solution":len(chain),
                    "expansions":expansions,
                    "wall_seconds":round(time.monotonic()-started,3),
                    "reject_reasons":dict(self.stats),
                    "heuristic_weight":heuristic_weight,
                    "exact_native_edge_cache":self.grid._exact_immutable_edge_clear.cache_info()._asdict(),
                    "native_DRC_still_required":True,
                })
                return diagnostic
            for nxt in self._neighbors(current):
                cost=g+self._step_cost(current,nxt)
                if cost<g_score.get(nxt,math.inf)-1e-9:
                    g_score[nxt]=cost
                    parent[nxt]=current
                    h=self._heuristic(nxt,goals)
                    heapq.heappush(heap,(
                        cost+heuristic_weight*h,cost,next(counter),nxt))
        else:
            diagnostic["status"]=(
                "MIDPOINT_JOINT_NODE_BUDGET_EXHAUSTED"
                if heap else "MIDPOINT_PINCH_CORRIDOR_EXHAUSTED")
        diagnostic["expansions"]=expansions
        diagnostic["wall_seconds"]=round(time.monotonic()-started,3)
        diagnostic["reject_reasons"]=dict(self.stats)
        diagnostic["open_joint_states_remaining"]=len(heap)
        diagnostic["closest_remaining_total_mm"]=round(
            closest_remaining_mm,6)
        diagnostic["closest_head_positions_grid"]=closest_state.points
        diagnostic["heuristic_weight"]=heuristic_weight
        diagnostic["exact_native_edge_cache"]=(
            self.grid._exact_immutable_edge_clear.cache_info()._asdict())
        return diagnostic

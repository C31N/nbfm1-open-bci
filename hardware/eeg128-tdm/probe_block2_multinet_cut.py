#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""No-release optimistic three-net F.Cu vertex-capacity diagnostic.

Deliberately UNION the three different net-specific free raster masks:
this overestimates each signal's available copper and ignores net pairing
and minimum 0.300-mm intertrace distance. Any vertex-flow value below 3
is strong evidence of a common grid bottleneck, but never proves that
the continuous native KiCad copper is globally unroutable.
"""
from __future__ import annotations

from collections import deque
from typing import Any


def optimistic_fcu_three_net_cut(
    forbidden_by_net:list[Any],
    starts:list[tuple[int,int]],
    goals:list[tuple[int,int]],
    xs:Any,ys:Any,
    *,diagonal_corner_override:bool=False,
) -> dict[str,Any]:
    import numpy as np
    if len(forbidden_by_net)!=3 or len(starts)!=3 or len(goals)!=3:
        raise RuntimeError("Exactly three native F.Cu agents required")
    shape=np.asarray(forbidden_by_net[0]).shape
    if len(shape)!=2 or any(np.asarray(a).shape!=shape
                            for a in forbidden_by_net):
        raise RuntimeError("Native grid dimensions mismatch")
    h,w=shape
    if (h<4 or w<4 or len(xs)!=w or len(ys)!=h
            or any(not (0<=x<w and 0<=y<h)
                   for x,y in starts+goals)):
        raise RuntimeError("Invalid F.Cu raster anchors")
    # Optimistic OR means one net may legally use a pixel even if the
    # other two cannot. This deliberately RELAXES true PCB constraints.
    free=np.logical_not(np.logical_and.reduce(forbidden_by_net))
    yy,xx=np.nonzero(free)
    ids=np.full(shape,-1,dtype=np.int32)
    ids[yy,xx]=np.arange(len(yy),dtype=np.int32)
    cells=len(yy)
    source=2*cells
    sink=source+1
    graph:list[list[list[int]]]=[[] for _ in range(sink+1)]
    def arc(a:int,b:int,capacity:int)->None:
        graph[a].append([b,len(graph[b]),capacity])
        graph[b].append([a,len(graph[a])-1,0])
    for y,x in zip(yy,xx):
        v=int(ids[y,x])
        arc(2*v,2*v+1,1)
        for dx,dy in (
            (0,1),(1,0),(0,-1),(-1,0),
            (1,1),(1,-1),(-1,1),(-1,-1)
        ):
            nx,ny=int(x)+dx,int(y)+dy
            if not (0<=nx<w and 0<=ny<h and free[ny,nx]):
                continue
            if (dx and dy and not diagonal_corner_override
                    and (not free[y,nx] or not free[ny,x])):
                continue
            arc(2*v+1,2*int(ids[ny,nx]),3)
    for x,y in starts:
        if free[y,x]:
            arc(source,2*int(ids[y,x]),1)
    for x,y in goals:
        if free[y,x]:
            arc(2*int(ids[y,x])+1,sink,1)
    # At most three augmentations; each BFS walks only the optimistic
    # native grid, so this runs without scipy or external native modules.
    value=0
    while value<3:
        seen=[False]*len(graph)
        parent=[(-1,-1)]*len(graph)
        q=deque((source,))
        seen[source]=True
        while q and not seen[sink]:
            u=q.popleft()
            for edge_index,edge in enumerate(graph[u]):
                v,_,cap=edge
                if cap>0 and not seen[v]:
                    seen[v]=True
                    parent[v]=(u,edge_index)
                    q.append(v)
        if not seen[sink]:
            break
        vertex=sink
        while vertex!=source:
            from_v,edge_index=parent[vertex]
            e=graph[from_v][edge_index]
            e[2]-=1
            graph[vertex][e[1]][2]+=1
            vertex=from_v
        value+=1
    # Minimum-capacity cut of the *optimistically united grid*.
    seen=[False]*len(graph)
    q=deque((source,))
    seen[source]=True
    while q:
        u=q.popleft()
        for v,_,capacity in graph[u]:
            if capacity>0 and not seen[v]:
                seen[v]=True
                q.append(v)
    witness=[]
    for y,x in zip(yy,xx):
        v=int(ids[y,x])
        if seen[2*v] and not seen[2*v+1]:
            witness.append({
                "grid_index":[int(x),int(y)],
                "position_mm":[float(xs[x]),float(ys[y])],
                "net_specific_free":[
                    bool(not forbidden_by_net[i][y,x])
                    for i in range(3)],
            })
    return {
        "status":("optimistic_grid_capacity_at_least_three"
                  if value==3
                  else "optimistic_FCu_raster_vertex_cut_below_three"),
        "optimistic_max_vertex_disjoint_paths":value,
        "vertex_cut_size":len(witness),
        "vertex_cut_witnesses":witness[:20],
        "optimistic_free_union_grid_nodes":cells,
        "diagonal_corner_override":diagonal_corner_override,
        "ignored_network_specific_copper_obstacles":True,
        "ignored_required_0_300mm_centreline_spacing":True,
        "source_sink_net_pairing_preserved":False,
        "grid_may_under_sample_continuous_geometry":True,
        "native_continuous_FCu_impossibility_proven":False,
        "new_vias_added":0,
        "accepted":False,
        "routing_completed":False,
        "fabrication_release":False,
    }

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Two/three-layer proposals with a strict 0.505 mm L3 exclusion for new traces and vias.

Requires Shapely 2.1. No board writes, via-in-pad or clearance exceptions.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
import shapely
import pcbnew
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.geometry.base import BaseGeometry
from route_targeted_closure import obstacles, xy, make_track, make_via, Point2, RoutingPath


def polygons(shape: BaseGeometry) -> list[shapely.Polygon]:
    if shape.geom_type=='Polygon': return [shape]
    return [p for g in getattr(shape,'geoms',[]) for p in polygons(g)]


def mesh_route(board: pcbnew.BOARD, start: Point2, goal: Point2, net: int,
               layers: tuple[int, ...], power: BaseGeometry, region: BaseGeometry,
               start_layer: int = 0, goal_layer: int = 0, allow_vias: bool = True,
               extra_obstacles: list[BaseGeometry] | None = None) -> RoutingPath | None:
    """Propose a complete two/three-layer path; native DRC remains authoritative."""
    if not hasattr(shapely,'constrained_delaunay_triangles'):
        raise RuntimeError('Optional mesh proposals require Shapely 2.1 or later')
    if len(layers) not in (2,3) or len(set(layers))!=len(layers) or any(
            l not in (pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu) for l in layers):
        raise ValueError('Two or three distinct F.Cu/In2.Cu/B.Cu layers are required')
    pairs=[obstacles(board,net,.15,.15,region,.60,(layers[0],layer)) for layer in layers[1:]]
    blocked=[pairs[0][0][0]]+[pair[0][1] for pair in pairs]
    via=pairs[0][1]
    blocked=[unary_union([shape,power.buffer(.505)]) if layers[i]==pcbnew.In2_Cu
             else shape for i,shape in enumerate(blocked)]
    if extra_obstacles:
        blocked=[unary_union([blocked[i],extra_obstacles[i]]) for i in range(len(layers))]
    # Additional five-nanometre inward guard avoids output on rounded boundaries.
    free=[region.difference(s).buffer(-.000005) for s in blocked]
    viafree=region.difference(unary_union([via,power.buffer(.505)] )).buffer(-.000005)
    coords=[]; adj=[]; lookup={}
    def node(layer: int, pt: Point2) -> int:
        key=(layer,round(pt[0],9),round(pt[1],9))
        if key not in lookup:
            lookup[key]=len(coords);coords.append((layer,float(pt[0]),float(pt[1])));adj.append([])
        return lookup[key]
    def edge(a: int, b: int, cost: float | None = None) -> None:
        if a==b:return
        c=math.dist(coords[a][1:],coords[b][1:]) if cost is None else cost
        adj[a].append((b,c));adj[b].append((a,c))
    anchors=[(start_layer,start),(goal_layer,goal)]
    vias=[]
    existing={xy(t.GetPosition()) for t in board.GetTracks()
              if isinstance(t,pcbnew.PCB_VIA) and t.GetNetCode()==net}
    if allow_vias:
        for patch in polygons(viafree):
            if patch.area<1e-10:continue
            pts=[patch.representative_point()]
            # Several samples help navigate finite via windows without any grid.
            for frac in (.2,.5,.8):
                x0,y0,x1,y1=patch.bounds
                for f2 in (.2,.5,.8):
                    p=Point(x0+(x1-x0)*frac,y0+(y1-y0)*f2)
                    if patch.contains(p):pts.append(p)
            for pt in pts:
                if all(f.covers(pt) for f in free):vias.append(pt.coords[0])
        vias += [pt for pt in sorted(existing) if sum(f.covers(Point(pt)) for f in free)>=2]
        anchors += [(i,pt) for pt in vias for i in range(len(layers)) if free[i].covers(Point(pt))]
    source=node(start_layer,start);target=node(goal_layer,goal)
    # Triangle portals form a connected roadmap even through very narrow corridors.
    for layer,area in enumerate(free):
        triangles=list(shapely.constrained_delaunay_triangles(area).geoms)
        if not triangles:continue
        tree=STRtree(triangles); tri_nodes=defaultdict(list);edges=defaultdict(list)
        for i,tri in enumerate(triangles):
            points=list(tri.exterior.coords)[:3]
            for a,b in zip(points,points[1:]+points[:1]):
                key=tuple(sorted(((round(a[0],9),round(a[1],9)),(round(b[0],9),round(b[1],9)))))
                edges[key].append(i)
        for key,ids in edges.items():
            if len(ids)!=2:continue
            a,b=key; idx=node(layer,((a[0]+b[0])/2,(a[1]+b[1])/2))
            for i in ids:tri_nodes[i].append(idx)
        for alayer,pt in anchors:
            if alayer!=layer:continue
            point=Point(pt)
            for i in tree.query(point):
                if triangles[i].covers(point):tri_nodes[int(i)].append(node(layer,pt));break
        for ns in tri_nodes.values():
            for i,a in enumerate(ns):
                for b in ns[i+1:]:edge(a,b)
    for pt in vias:
        valid=[i for i in range(len(layers)) if free[i].covers(Point(pt))]
        for i,layer in enumerate(valid):
            for other in valid[i+1:]:edge(node(layer,pt),node(other,pt),2.)
    q=[(0.,source)];dist={source:0.};parent={}
    while q:
        cost,i=heapq.heappop(q)
        if cost>dist[i]:continue
        if i==target:break
        for j,w in adj[i]:
            new=cost+w
            if new<dist.get(j,float('inf')):dist[j]=new;parent[j]=i;heapq.heappush(q,(new,j))
    if target not in dist:return None
    path=[target]
    while path[-1]!=source:path.append(parent[path[-1]])
    raw=[coords[i] for i in path[::-1]]
    # Visibility pruning preserves each layer transition and checks full segments.
    result=[];i=0
    while i<len(raw):
        result.append(raw[i]);j=i+1
        while j<len(raw) and raw[j][0]==raw[i][0]:j+=1
        if j==i+1:i+=1;continue
        end=j-1
        while end>i+1 and not free[raw[i][0]].covers(LineString([raw[i][1:],raw[end][1:]])):end-=1
        i=end
    # Rounding to integer nanometres is checked again before returning a proposal.
    result=[(l,round(x,6),round(y,6)) for l,x,y in result]
    for a,b in zip(result,result[1:]):
        if a[0]==b[0]:
            if not region.difference(blocked[a[0]]).covers(LineString([a[1:],b[1:]])):return None
        elif a[1:]!=b[1:] or (a[1:] not in existing and not viafree.covers(Point(a[1:]))):return None
    return result


def add_mesh_path(board: pcbnew.BOARD, path: RoutingPath, net: int,
                  layers: tuple[int, ...]) -> None:
    """Apply a complete proposal while reusing existing through vias exactly."""
    path=[tuple(p) for p in path]
    if len(path)<2 or any(len(p)!=3 or p[0] not in range(len(layers))
                         or not all(math.isfinite(v) for v in p[1:]) for p in path):
        raise ValueError('A complete finite path is required')
    if any(a[0]!=b[0] and a[1:]!=b[1:] for a,b in zip(path,path[1:])):
        raise ValueError('Layer transitions must share an exact via coordinate')
    existing={xy(t.GetPosition()) for t in board.GetTracks()
              if isinstance(t,pcbnew.PCB_VIA) and t.GetNetCode()==net}
    for a,b in zip(path,path[1:]):
        if a[0]==b[0]:make_track(board,a[1:],b[1:],net,.15,layers[a[0]])
        elif a[1:] not in existing:
            make_via(board,a[1:],net,.60);existing.add(a[1:])

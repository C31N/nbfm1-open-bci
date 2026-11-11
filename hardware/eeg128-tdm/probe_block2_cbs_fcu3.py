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
    reference_paths: tuple[list[Point] | None, ...] | None = None,
    uuid_detours: bool = False,
    u4_fanout: bool = False,
) -> tuple[list[list[tuple[int, float, float]]] | None, dict[str, Any]]:
    import pcbnew
    import numpy as np
    from shapely import contains_xy, prepare
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles
    from probe_block2_u4_corridors import (
        adaptive_cbs_regions, connected_conflict_corridor,
        rasterized_conflict_region_edges, verify_u4_escape_group,
    )
    from shapely.geometry import Point as ShapelyPoint
    from probe_block2_u4_dogleg import native_u4_lateral_preflight

    if len(endpoints) != 3 or len(nets) != 3 or len(set(nets)) != 3:
        raise ValueError("CBS requires exactly three distinct target nets")
    if not (.19 <= step_mm <= .44 and 5 <= max_cbs_nodes <= 1200
            and 1000 <= max_lowlevel_nodes <= 50000
            and 10 <= seconds <= 150
            and selection in ("length", "conflict-volume")
            and split_mode in ("single-edge", "corridor-bundle",
                               "u4-corridor")):
        raise ValueError("Unreviewed bounded CBS parameter")
    if reference_paths is not None and (len(reference_paths) != 3
            or any(path is not None and len(path) < 2
                   for path in reference_paths)):
        raise ValueError("Guided CBS3 requires valid known reference paths")
    if u4_fanout and split_mode != "u4-corridor":
        raise ValueError("Deterministic U4 fanout needs u4-corridor mode")
    original_endpoints = endpoints
    fanout_wires = None
    fanout_sides = None
    fanout_normal = None
    fanout_diag = None
    started = time.monotonic()
    u4_ports = ()
    u4_reservation: dict[str, Any] | None = None
    if split_mode == "u4-corridor":
        try:
            u4_ports, u4_reservation = verify_u4_escape_group(
                board, nets, endpoints)
        except RuntimeError as exc:
            return None, {
                "status": "CBS3_U4_reservation_source_drift",
                "reason": str(exc)[:250],
                "qualified": False, "new_vias_added": 0,
            }
    if u4_fanout:
        try:
            if sorted(u4_reservation["U4_pad_numbers"]) != ["17","18","19"]:
                raise RuntimeError("U4 native target pin numbers changed")
            fanout_wires,fanout_sides,fanout_normal,fanout_diag = (
                native_u4_lateral_preflight(
                    board,u4_ports,nets,original_endpoints))
        except RuntimeError as exc:
            return None, {
                "status":"CBS3_U4_lateral_fanout_preflight_blocked",
                "reason":str(exc)[:6000],
                "u4_deterministic_fanout_enabled":True,
                "qualified":False,"new_vias_added":0,
                "geometry_unsatisfiable_proven":False,
            }
        revised=[]
        for i,pair in enumerate(original_endpoints):
            ends=list(pair)
            ends[fanout_sides[i]]=fanout_wires[i][-1]
            revised.append(tuple(ends))
        endpoints=tuple(revised)
        if progress:
            progress("CBS3_U4_lateral_dogleg_immutable_preplan",fanout_diag)
    from probe_block2_uuid_detours import detour_geometry
    hard_detours, detour_diagnostic = (
        detour_geometry(board) if uuid_detours else (None, None))
    all_ends = [xy for pair in endpoints for xy in pair]
    limits = board.GetBoardEdgesBoundingBox()
    margin = .56
    detour_reach = 7.2 if uuid_detours else 3.2
    x0 = max(min(x for x, _ in all_ends)-detour_reach,
             pcbnew.ToMM(limits.GetX())+margin)
    x1 = min(max(x for x, _ in all_ends)+detour_reach,
             pcbnew.ToMM(limits.GetRight())-margin)
    y0 = max(min(y for _, y in all_ends)-detour_reach,
             pcbnew.ToMM(limits.GetY())+margin)
    y1 = min(max(y for _, y in all_ends)+detour_reach,
             pcbnew.ToMM(limits.GetBottom())-margin)
    xs = np.arange(x0, x1+step_mm/2, step_mm)
    ys = np.arange(y0, y1+step_mm/2, step_mm)
    if len(xs) < 3 or len(ys) < 3:
        return None, {"status": "spatial_CBS_no_grid"}
    gx, gy = np.meshgrid(xs, ys)
    bbox = box(x0,y0,x1,y1)
    u4_roi = (unary_union([ShapelyPoint(port).buffer(1.65)
                           for port in u4_ports])
              if u4_ports else None)
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
        if hard_detours is not None:
            shape = shape.union(hard_detours)
        if fanout_wires is not None:
            shape=shape.union(unary_union([
                LineString(fanout_wires[j]).buffer(.300-1e-9,resolution=8)
                for j in range(3) if j != i]))
        prepare(shape)
        shapes.append(shape)
        mask=contains_xy(shape,gx,gy)
        if fanout_wires is not None:
            # A* cannot expand inside the U4 pad-to-fanout-tip half-plane.
            # Copper before the tips is already deterministically reserved.
            center=(sum(p[0] for p in u4_ports)/3,
                    sum(p[1] for p in u4_ports)/3)
            projection=(fanout_normal[0]*(gx-center[0])
                        +fanout_normal[1]*(gy-center[1]))
            mask |= projection < (
                fanout_diag["transition_mm"]
                +fanout_diag["parallel_length_mm"] - 1e-8)
        masks.append(mask)
        if progress:
            progress("CBS3_fixed_copper_agent_done",{"agent":i})

    # Missing rubber-band paths are UNGUIDED; never force an artificial
    # crossing or turn hints into immutable physical copper.
    reference_masks = (
        [contains_xy(LineString(path).buffer(.65), gx, gy)
         if path is not None else None for path in reference_paths]
        if reference_paths is not None else None
    )
    competitor_masks = (
        [contains_xy(
            unary_union([LineString(path).buffer(.33)
                         for j, path in enumerate(reference_paths)
                         if j != i and path is not None]),
            gx, gy)
         if any(j != i and path is not None
                for j, path in enumerate(reference_paths))
         else np.zeros(gx.shape, dtype=bool)
         for i in range(3)]
        if reference_paths is not None else None
    )

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
        "u4_coupled_reservation":u4_reservation,
        "u4_deterministic_fanout_enabled":u4_fanout,
        "u4_deterministic_fanout_diagnostic":fanout_diag,
        "u4_conflict_radius_mm":1.65 if u4_roi is not None else None,
        "u4_first_conflict_priority":u4_roi is not None,
        "u4_corridor_splits":0,
        "CBS3_spatial_limit_fallback_triggered":False,
        "CBS3_spatial_limit_fallback_count":0,
        "CBS3_spatial_limit_fallback_last_edges":None,
        "CBS3_spatial_limit_fallback_limit":320,
        "CBS3_both_children_unspawned_count":0,
        "CBS3_last_conflict_both_children_unspawned":False,
        "CBS3_lowlevel_outcomes":{"path_found":0,
                                  "wall_budget_exhausted":0,
                                  "node_budget_exhausted":0,
                                  "frontier_exhausted":0},
        "u4_secondary_branches":0,
        "u4_disconnected_spatial_children":0,
        "u4_rescue_reroutes_succeeded":0,
        "u4_secondary_by_type":{"strand":0,"single-edge-rescue":0},
        "start_anchors":start, "goal_anchors":goal,
        "simultaneous_three_net_conflict_search":True,
        "CH038_return_preplaced":True, "qualified":False,
        "new_vias_added":0,
        "uuid_detours_enabled": uuid_detours,
        "uuid_detour_reach_mm": detour_reach,
        "uuid_detour_diagnostic": detour_diagnostic,
        "expanded_cbs_nodes":0, "expanded_lowlevel_nodes":0,
        "resolved_conflicts":0,
    }
    if any(q is None for q in start+goal):
        diag["status"]="CBS3_endpoint_escape_blocked"
        return None,diag

    diag["rubber_band_guidance"] = reference_masks is not None
    diag["competitor_corridor_repulsion"] = competitor_masks is not None
    diag["partial_reference_count"] = (
        sum(path is not None for path in reference_paths)
        if reference_paths is not None else 0)
    diag["missing_reference_agents"] = (
        [i for i, path in enumerate(reference_paths) if path is None]
        if reference_paths is not None else [])

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
                diag["CBS3_lowlevel_outcomes"]["wall_budget_exhausted"] += 1
                diag["expanded_lowlevel_nodes"] += expanded
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
                diag["CBS3_lowlevel_outcomes"]["path_found"] += 1
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
                corridor_cost = (2.75 if reference_masks is not None
                                 and reference_masks[agent] is not None
                                 and not reference_masks[agent][y,x] else 0.)
                neighbor_cost = (12.0 if competitor_masks is not None
                                 and competitor_masks[agent][y,x] else 0.0)
                g2=g+step_mm*(math.hypot(dx,dy)+corridor_cost+neighbor_cost)
                if g2<cost.get(nxt,float("inf")):
                    cost[nxt]=g2
                    parents[nxt]=node
                    h=math.dist(physical(nxt),physical(last))
                    heapq.heappush(q,(g2+h,next(counter),g2,nxt))
        diag["expanded_lowlevel_nodes"]+=expanded
        reason = "node_budget_exhausted" if q else "frontier_exhausted"
        diag["CBS3_lowlevel_outcomes"][reason] += 1
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
        # Resolve three U4 exits as a COUPLED group before collisions farther
        # into F.Cu. Never waive the 0.300-mm copper-centreline requirement.
        for u4_first in ((True, False) if u4_roi is not None else (False,)):
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
                        if u4_first and not gi.intersects(u4_roi):
                            continue
                        for gj,kj in segs[j]:
                            if u4_first and not gj.intersects(u4_roi):
                                continue
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
            if fanout_wires is not None:
                # The scratch board is only mutated later, after all three
                # routes are simultaneously collision-free in CBS3.
                for agent,wire in enumerate(fanout_wires):
                    # Preserve ALL individually solved escape vertices;
                    # replacing them with a straight pad->tip chord would
                    # silently cross fixed native U3/CH027 copper.
                    if fanout_sides[agent] == 0:
                        result[agent] = (
                            [(0,*point) for point in wire[:-1]]
                            +result[agent])
                    else:
                        result[agent].extend(
                            (0,*point) for point in reversed(wire[:-1]))
                diag["u4_full_fanout_vertices_retained"] = [
                    len(wire) for wire in fanout_wires]
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
        spawned_agents = 0
        for agent,prohibited in ((i,ei),(j,ej)):
            # Each CBS disjunction forbids the original conflicting edge
            # for ONE agent. Spatial/strand options are exploratory
            # restrictions; optional weaker children preserve paths that a
            # broad hard corridor would otherwise erase prematurely.
            options: tuple[tuple[str, frozenset[GridEdge]], ...] = (
                ("single-edge", frozenset((prohibited,))),)
            if split_mode == "u4-corridor":
                counterpart = j if agent == i else i
                rival_line = LineString(
                    [endpoints[counterpart][0]]
                    + [physical(x) for x in paths[counterpart]]
                    + [endpoints[counterpart][1]])
                strand = connected_conflict_corridor(
                    path_segments(agent, paths[agent]), rival_line,
                    prohibited, clearance_threshold, max_edges=10)
                spatial_strand = rasterized_conflict_region_edges(
                    strand, xs, ys, padding_mm=.16, max_region_edges=320,
                    telemetry=diag)
                options = adaptive_cbs_regions(
                    spatial_strand, strand, prohibited,
                    expanded=diag["expanded_cbs_nodes"], queued=len(q))
                diag["u4_corridor_splits"] += 1
                diag["last_u4_spatial_region_edges"] = len(spatial_strand)
                diag["last_u4_corridor_edge_count"] = len(spatial_strand)
                diag["last_u4_corridor_agent"] = agent
            elif split_mode == "corridor-bundle":
                counterpart = j if agent == i else i
                rival_line = LineString(
                    [endpoints[counterpart][0]]
                    + [physical(x) for x in paths[counterpart]]
                    + [endpoints[counterpart][1]])
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
                local = [key for gap,key in colliding if gap <= 1.05]
                bundle = frozenset((prohibited,)) | frozenset(local[:2])
                options = (("corridor-bundle", bundle),)
                diag["last_corridor_bundle_edge_count"] = len(bundle)
                diag["last_corridor_bundle_original_overlap_edges"] = len(colliding)
            spawned_any = False
            for option_index, (option_kind, forbidden_edges) in enumerate(options):
                if (option_index > 0 and spawned_any
                        and not (len(q) < 16
                                 and diag["expanded_cbs_nodes"] >= 12)):
                    break
                newer=list(limits_by_net)
                newer[agent]=limits_by_net[agent] | forbidden_edges
                key=(newer[0],newer[1],newer[2])
                if key in seen:
                    continue
                seen.add(key)
                reroute=low_level(agent,key[agent])
                if reroute is None:
                    if option_kind == "spatial":
                        diag["u4_disconnected_spatial_children"] += 1
                    continue
                newpaths=list(paths)
                newpaths[agent]=reroute
                version=(newpaths[0],newpaths[1],newpaths[2])
                heapq.heappush(q,(score(version),next(counter),key,version))
                spawned_any = True
                if option_index > 0:
                    diag["u4_secondary_branches"] += 1
                    if option_kind in diag["u4_secondary_by_type"]:
                        diag["u4_secondary_by_type"][option_kind] += 1
                    diag["u4_rescue_reroutes_succeeded"] += 1
            if spawned_any:
                spawned_agents += 1
        # A bounded inability to spawn either CBS child is not a proof
        # of geometric impossibility: A* may have reached its own limits.
        both_unspawned = spawned_agents == 0
        diag["CBS3_last_conflict_both_children_unspawned"] = both_unspawned
        if both_unspawned:
            diag["CBS3_both_children_unspawned_count"] += 1
        if progress and diag["expanded_cbs_nodes"]%10==0:
            progress("CBS3_conflict_tree_progress",{
                "expanded_cbs_nodes":diag["expanded_cbs_nodes"],
                "resolved_conflicts":diag["resolved_conflicts"],
                "queue_size":len(q),
                "last_conflict":diag["last_conflict"],
            })
    else:
        if diag["CBS3_lowlevel_outcomes"]["wall_budget_exhausted"]:
            diag["status"]="CBS3_wall_budget_exhausted"
        elif q and diag["expanded_cbs_nodes"] >= max_cbs_nodes:
            diag["status"]="CBS3_conflict_tree_budget_exhausted"
        elif diag["CBS3_lowlevel_outcomes"]["node_budget_exhausted"]:
            diag["status"]="CBS3_lowlevel_node_budget_limited"
        else:
            diag["status"]="CBS3_conflict_tree_bounded_dead_end"
    diag["CBS3_exit_class"] = (
        "budget" if diag["status"] in (
            "CBS3_wall_budget_exhausted",
            "CBS3_conflict_tree_budget_exhausted",
            "CBS3_lowlevel_node_budget_limited")
        else "bounded_dead_end")
    diag["CBS3_spatial_fallback_observed_not_causal_proof"] = (
        diag["CBS3_spatial_limit_fallback_triggered"])
    diag["CBS3_geometry_unsatisfiable_proven"] = False
    diag.update(open_cbs_nodes=len(q),wall_s=round(time.monotonic()-started,3))
    return None,diag

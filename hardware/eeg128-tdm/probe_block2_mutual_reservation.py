#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed, immutable U4 escape + mutually reserved three-net macro search.

No board writes. Each successful macro path is immediately an unrelaxable
0.300-mm centreline exclusion for every subsequently searched net. Test all
six agent orders on independent scratch masks; never rip up accepted escape
geometry. The caller must still perform independent native DRC, 201-victim
restitution, L3 area, parity, and byte-identical replay before acceptance.
"""
from __future__ import annotations

from collections import Counter
import itertools
import time
from typing import Any, Callable

from shapely.geometry import LineString

CLEARANCE_CENTRE_MM = .300
_TOL_MM = 1e-8
Route = tuple[tuple[int,int], ...]
RouteOne = Callable[[int, tuple[LineString, ...]], Route | None]
LineForRoute = Callable[[int, Route], LineString]


def mutually_reserved_macro_search(
    route_one: RouteOne,
    line_for_route: LineForRoute,
    protected_shapes: tuple[Any, Any, Any],
    immutable_fanouts: tuple[LineString, LineString, LineString],
    *, deadline: float,
    max_orders: int = 6,
) -> tuple[tuple[Route, Route, Route] | None, dict[str, Any]]:
    """Coupled priority search: every accepted route seals copper immediately.

    A failed order is discarded completely, including its temporary macro
    reservations. The three immutable fanouts persist across all orders.
    The return value is merely proposed F.Cu geometry, never DRC qualification.
    """
    if len(protected_shapes)!=3 or len(immutable_fanouts)!=3:
        raise ValueError("Exactly three immutable native F.Cu escapes required")
    if not 1<=max_orders<=6:
        raise ValueError("Unreviewed macro search order limit")
    if any(not isinstance(line,LineString) or line.is_empty
           for line in immutable_fanouts):
        raise ValueError("Invalid sealed U4 escape")
    for i in range(3):
        for j in range(i+1,3):
            if (immutable_fanouts[i].distance(immutable_fanouts[j])
                    < CLEARANCE_CENTRE_MM-_TOL_MM):
                raise ValueError("Original U4 fanouts violate 0.300mm pitch")
    failures: list[dict[str,Any]]=[]
    stats: Counter[str]=Counter()
    orders_started=0
    for ordering in itertools.islice(itertools.permutations(range(3)),max_orders):
        if time.monotonic()>=deadline:
            stats["wall_budget_exhausted"]+=1
            break
        orders_started+=1
        chosen: dict[int,Route]={}
        reserved: list[tuple[int,LineString]]=[]
        for agent in ordering:
            if time.monotonic()>=deadline:
                stats["wall_budget_exhausted"]+=1
                break
            # Frozen output of preceding nets is passed to route_one as a
            # hard obstacle. The planner cannot move any preceding segment.
            route=route_one(agent,tuple(line for _,line in reserved))
            if route is None:
                stats["macro_unroutable_with_reservations"]+=1
                failures.append({
                    "priority_order":ordering,"blocked_agent":agent,
                    "already_reserved":tuple(i for i,_ in reserved),
                    "status":"no_grid_path_with_fixed_reservations"})
                break
            if len(route)<2:
                stats["degenerate_macro_path"]+=1
                failures.append({"priority_order":ordering,
                                 "blocked_agent":agent,
                                 "status":"degenerate_macro_path"})
                break
            line=line_for_route(agent,route)
            if line.is_empty or not line.is_valid:
                stats["invalid_macro_shape"]+=1
                break
            if line.relate_pattern(protected_shapes[agent],"T********"):
                stats["native_copper_segment_collision"]+=1
                failures.append({"priority_order":ordering,
                                 "blocked_agent":agent,
                                 "status":"native_copper_segment_collision"})
                break
            if any(line.distance(other)<CLEARANCE_CENTRE_MM-_TOL_MM
                   for i,other in enumerate(immutable_fanouts)
                   if i!=agent):
                stats["locked_escape_overlap"]+=1
                failures.append({"priority_order":ordering,
                                 "blocked_agent":agent,
                                 "status":"locked_escape_overlap"})
                break
            if any(line.distance(other)<CLEARANCE_CENTRE_MM-_TOL_MM
                   for _,other in reserved):
                stats["reserved_macro_clearance_violation"]+=1
                failures.append({"priority_order":ordering,
                                 "blocked_agent":agent,
                                 "status":"reserved_macro_clearance_violation"})
                break
            # Commit the proposal to this order's immutable reservations.
            reserved.append((agent,line))
            chosen[agent]=route
            stats["macro_paths_reserved"]+=1
        if len(chosen)==3:
            stats["successful_orderings"]+=1
            result=(chosen[0],chosen[1],chosen[2])
            return result,{
                "status":"three_macro_paths_reserved_unverified",
                "ordering":ordering,
                "orders_started":orders_started,
                "reservations_per_net":[len(x) for x in result],
                "minimum_post_escape_centreline_mm":min(
                    reserved[i][1].distance(reserved[j][1])
                    for i in range(3) for j in range(i+1,3)),
                "locked_U4_escape_count":3,
                "new_vias_added":0,
                "macro_search_counts":dict(stats),
                "native_DRC_still_required":True,
                "fully_restituted":False,
            }
    return None,{
        "status":"mutual_macro_reservation_bounded_no_solution",
        "orders_started":orders_started,
        "max_orders":max_orders,
        "macro_search_counts":dict(stats),
        "macro_failed_orders":failures[:max_orders],
        "locked_U4_escape_count":3,
        "new_vias_added":0,
        "geometry_unsatisfiable_proven":False,
        "native_DRC_still_required":True,
    }

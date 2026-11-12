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
RouteOne = Callable[[int, tuple[LineString, ...], int], Route | None]
LineForRoute = Callable[[int, Route], LineString]


def mutually_reserved_macro_search(
    route_one: RouteOne,
    line_for_route: LineForRoute,
    protected_shapes: tuple[Any, Any, Any],
    immutable_fanouts: tuple[LineString, LineString, LineString],
    *, immutable_targets: tuple[LineString, LineString, LineString] | None = None,
    deadline: float,
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
    if immutable_targets is not None:
        if (len(immutable_targets)!=3 or
                any(not isinstance(line,LineString) or line.is_empty
                    for line in immutable_targets)):
            raise ValueError("Invalid immutable native target escapes")
    all_clusters=(immutable_fanouts,immutable_targets)
    for cluster in all_clusters:
        if cluster is None:
            continue
        for i in range(3):
            for j in range(i+1,3):
                if (cluster[i].distance(cluster[j])
                        < CLEARANCE_CENTRE_MM-_TOL_MM):
                    raise ValueError("Sealed escape cluster violates pitch")
    if immutable_targets is not None:
        for i in range(3):
            for j in range(3):
                if (i!=j and
                        immutable_fanouts[i].distance(
                            immutable_targets[j])
                        < CLEARANCE_CENTRE_MM-_TOL_MM):
                    raise ValueError("Source-target sealed cross-net collision")
    failures: list[dict[str,Any]]=[]
    stats: Counter[str]=Counter()
    orders_started=0
    # A constrained two-level lookahead is required: greedy first paths
    # blocked every second route in the initial six-order native diagnosis.
    # Each search branch reserves the first path irrevocably UNTIL that
    # speculative branch fails, then discards the entire branch; original
    # U4 escape copper is NEVER discarded or altered.
    variants_per_depth=(4,3,1)

    for ordering in itertools.islice(
        itertools.permutations(range(3)),max_orders
    ):
        if time.monotonic()>=deadline:
            stats["wall_budget_exhausted"]+=1
            break
        orders_started+=1
        chosen: dict[int,Route]={}
        reserved: list[tuple[int,LineString]]=[]
        order_rejections=Counter()

        def descend(depth:int) -> bool:
            if time.monotonic()>=deadline:
                stats["wall_budget_exhausted"]+=1
                return False
            if depth==3:
                return True
            agent=ordering[depth]
            for variant in range(variants_per_depth[depth]):
                if time.monotonic()>=deadline:
                    stats["wall_budget_exhausted"]+=1
                    break
                # Every subsequent route receives all already committed
                # macro copper as a HARD rasterized obstacle in its A*.
                route=route_one(agent,tuple(x for _,x in reserved),variant)
                stats["lowlevel_attempts"]+=1
                if route is None:
                    stats["macro_unroutable_with_reservations"]+=1
                    order_rejections["no_grid_path"]+=1
                    continue
                if len(route)<2:
                    stats["degenerate_macro_path"]+=1
                    order_rejections["degenerate_macro_path"]+=1
                    continue
                line=line_for_route(agent,route)
                if line.is_empty or not line.is_valid:
                    stats["invalid_macro_shape"]+=1
                    order_rejections["invalid_macro_shape"]+=1
                    continue
                if line.relate_pattern(
                    protected_shapes[agent],"T********"
                ):
                    stats["native_copper_segment_collision"]+=1
                    order_rejections["native_copper_segment_collision"]+=1
                    continue
                if any(
                    line.distance(other)<CLEARANCE_CENTRE_MM-_TOL_MM
                    for cluster in all_clusters
                    if cluster is not None
                    for i,other in enumerate(cluster)
                    if i!=agent
                ):
                    stats["locked_escape_overlap"]+=1
                    order_rejections["locked_escape_overlap"]+=1
                    continue
                if any(
                    line.distance(other)<CLEARANCE_CENTRE_MM-_TOL_MM
                    for _,other in reserved
                ):
                    stats["reserved_macro_clearance_violation"]+=1
                    order_rejections["reserved_macro_clearance_violation"]+=1
                    continue
                chosen[agent]=route
                reserved.append((agent,line))
                stats["macro_paths_reserved"]+=1
                if descend(depth+1):
                    stats["successful_orderings"]+=1
                    return True
                # This is a discarded speculative MACRO branch, never a
                # rip-up of the sealed U4 fanouts or existing PCB copper.
                reserved.pop()
                del chosen[agent]
                stats["speculative_macro_branch_backtracks"]+=1
            return False

        if descend(0):
            result=(chosen[0],chosen[1],chosen[2])
            return result,{
                "status":"three_macro_paths_reserved_unverified",
                "ordering":ordering,
                "orders_started":orders_started,
                "macro_variant_limits":variants_per_depth,
                "reservations_per_net":[len(x) for x in result],
                "minimum_post_escape_centreline_mm":min(
                    reserved[i][1].distance(reserved[j][1])
                    for i in range(3) for j in range(i+1,3)),
                "locked_U4_escape_count":3,
                "locked_target_escape_count":(
                    3 if immutable_targets is not None else 0),
                "new_vias_added":0,
                "macro_search_counts":dict(stats),
                "native_DRC_still_required":True,
                "fully_restituted":False,
            }
        failures.append({
            "priority_order":ordering,
            "reason_counts":dict(order_rejections),
            "speculative_macros_rolled_back_only":True,
        })
    return None,{
        "status":"mutual_macro_reservation_bounded_no_solution",
        "orders_started":orders_started,
        "max_orders":max_orders,
        "macro_variant_limits":variants_per_depth,
        "macro_search_counts":dict(stats),
        "macro_failed_orders":failures[:max_orders],
        "locked_U4_escape_count":3,
        "locked_target_escape_count":(
            3 if immutable_targets is not None else 0),
        "new_vias_added":0,
        "geometry_unsatisfiable_proven":False,
        "native_DRC_still_required":True,
    }

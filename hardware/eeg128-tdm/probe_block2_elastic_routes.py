#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded F.Cu three-net elastic routing and zero-width topology fallback.

These are scratch-only geometric PROPOSALS. Topological zero-width wires
are neither copper nor manufacturing evidence. No vias, no In1.Cu, no
changes to fixed tracks, protected components or zones are authorized.
The caller must restore all 201 original victims, fill zones, run native
DRC, prove native schematic parity and byte-identical replay separately.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from typing import Any, Callable

Point = tuple[float, float]
TARGETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1),
         (1, 1), (1, -1), (-1, 1), (-1, -1))


def _nearest_distance(pt: Point, guide: list[Point]) -> float:
    """Distance to polyline SEGMENTS, not just to sparsely sampled vertices."""
    if len(guide) < 2:
        return float("inf")
    best = float("inf")
    for (ax, ay), (bx, by) in zip(guide, guide[1:]):
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        t = max(0.0, min(1.0, (
            (pt[0] - ax) * dx + (pt[1] - ay) * dy
        ) / denom)) if denom else 0.0
        best = min(best, math.hypot(
            pt[0] - ax - t * dx, pt[1] - ay - t * dy))
    return best


def repel_waypoints(
    course: list[Point],
    xs: Any,
    ys: Any,
    blocked: Any,
    labels: Any,
    ridge: Any,
    guides: list[list[Point]],
    *,
    max_shift_mm: float = 1.40,
) -> tuple[list[Point], list[dict[str, Any]]]:
    """Displace 3 internal waypoints within their same FREE component.

    The 201-victim native obstacle model is unchanged. A waypoint move is a
    soft search proposal, not proof that the connecting hop is routable.
    """
    if len(course) < 5:
        raise ValueError("Elastic waypoint course too short")
    indices = sorted(set(round((len(course) - 1) * q / 4)
                         for q in (1, 2, 3)))
    if len(indices) != 3:
        raise ValueError("Cannot select three ordered waypoints")
    results: list[Point] = []
    diagnostics: list[dict[str, Any]] = []
    for index in indices:
        target = course[index]
        ix = int(round((target[0] - float(xs[0])) /
                       (float(xs[1]) - float(xs[0]))))
        iy = int(round((target[1] - float(ys[0])) /
                       (float(ys[1]) - float(ys[0]))))
        ix = min(max(0, ix), len(xs) - 1)
        iy = min(max(0, iy), len(ys) - 1)
        component = int(labels[iy, ix])
        if component < 0 or bool(blocked[iy, ix]):
            raise RuntimeError("Original elastic waypoint outside free component")
        best = target
        def energy(pt: Point, on_ridge: bool) -> float:
            repel = sum(
                35.0 * max(0.0, 1.60 - _nearest_distance(pt, g)) ** 2
                for g in guides
            )
            return (repel + 6.0 * math.dist(pt, target)
                    + (0.0 if on_ridge else 1.5))
        best_cost = energy(best, bool(ridge[iy, ix]))
        radius_x = int(math.ceil(max_shift_mm /
                                (float(xs[1]) - float(xs[0]))))
        radius_y = int(math.ceil(max_shift_mm /
                                (float(ys[1]) - float(ys[0]))))
        for y in range(max(0, iy - radius_y),
                       min(len(ys), iy + radius_y + 1)):
            for x in range(max(0, ix - radius_x),
                           min(len(xs), ix + radius_x + 1)):
                if bool(blocked[y, x]) or int(labels[y, x]) != component:
                    continue
                trial = float(xs[x]), float(ys[y])
                if math.dist(trial, target) > max_shift_mm:
                    continue
                score = energy(trial, bool(ridge[y, x]))
                if score < best_cost - 1e-10:
                    best_cost = score
                    best = trial
        results.append(best)
        diagnostics.append({
            "original_mm": target,
            "repelled_mm": best,
            "shift_mm": round(math.dist(target, best), 5),
            "same_component": True,
            "max_shift_mm": max_shift_mm,
        })
    return results, diagnostics


def repulsion_field(
    gx: Any, gy: Any, guides: list[list[Point]]
) -> Any:
    """Continuous, nonnegative potential; no DRC/obstacle relaxation."""
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import LineString

    result = np.zeros(gx.shape, dtype=float)
    for guide in guides:
        if len(guide) < 2:
            continue
        line = LineString(guide)
        # Smooth stepped potential extending far beyond 0.30-mm legal spacing.
        for radius, weight in ((1.65, 3.0), (1.10, 8.0),
                               (0.60, 15.0), (0.32, 30.0)):
            result += contains_xy(line.buffer(radius), gx, gy) * weight
    return result


def _rubber_trace(
    xs: Any,
    ys: Any,
    blocked: Any,
    obstacle: Any,
    source: Point,
    target: Point,
    previous: list[list[Point]],
    expires: float,
    separation_mm: float = 0.0,
) -> list[Point] | None:
    """Zero-trace-width A* over an F.Cu free-space graph, no DRC claim."""
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import LineString

    # Before zero-width A*, softly repel later trees from every already
    # planned tree. This does not remove an obstacle or authorize copper.
    grid_x, grid_y = np.meshgrid(xs, ys)
    rubber_repulsion = np.zeros(blocked.shape, dtype=float)
    for guide in previous:
        line = LineString(guide)
        for radius, penalty in ((1.0, 3.0), (.65, 9.0),
                                (.42, 21.0), (.30, 55.0)):
            rubber_repulsion += (
                contains_xy(line.buffer(radius), grid_x, grid_y) * penalty
            )

    if not 0.0 <= separation_mm <= .5:
        raise ValueError("Unsupported topology separation")
    other_lines = [LineString(g) for g in previous]

    xstep = float(xs[1] - xs[0])
    ystep = float(ys[1] - ys[0])

    def physical(node: tuple[int, int]) -> Point:
        return float(xs[node[0]]), float(ys[node[1]])

    def anchor(pt: Point) -> tuple[int, int] | None:
        ix = int(round((pt[0] - float(xs[0])) / xstep))
        iy = int(round((pt[1] - float(ys[0])) / ystep))
        options = ((x, y) for y in range(max(0, iy - 7),
                                         min(len(ys), iy + 8))
                   for x in range(max(0, ix - 7),
                                  min(len(xs), ix + 8))
                   if not blocked[y, x])
        for node in sorted(options, key=lambda p: math.dist(physical(p), pt)):
            stub = LineString((pt, physical(node)))
            if (not stub.relate_pattern(obstacle, "T********")
                    and all(not stub.intersects(other)
                            and stub.distance(other) >= separation_mm - 1e-9
                            for other in other_lines)):
                return node
        return None

    start, end = anchor(source), anchor(target)
    if start is None or end is None:
        return None
    sequence = itertools.count()
    queue = [(math.dist(physical(start), physical(end)),
              next(sequence), 0.0, start)]
    costs = {start: 0.0}
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    expansions = 0
    while queue and expansions < 55000 and time.monotonic() < expires:
        _, _, g, node = heapq.heappop(queue)
        if g != costs.get(node):
            continue
        expansions += 1
        if node == end:
            rev: list[Point] = []
            cursor: tuple[int, int] | None = node
            while cursor is not None:
                rev.append(physical(cursor))
                cursor = parents[cursor]
            route = [source] + list(reversed(rev)) + [target]
            polygonal = LineString(route)
            if any(polygonal.intersects(other)
                   or polygonal.distance(other) < separation_mm - 1e-9
                   for other in other_lines):
                return None
            return route
        for dx, dy in MOVES:
            x, y = node[0] + dx, node[1] + dy
            if (not 0 <= x < len(xs) or not 0 <= y < len(ys)
                    or blocked[y, x]):
                continue
            if dx and dy and (blocked[node[1], x] or blocked[y, node[0]]):
                continue
            nxt = x, y
            segment = LineString((physical(node), physical(nxt)))
            if (segment.relate_pattern(obstacle, "T********")
                    or any(segment.intersects(other)
                           or segment.distance(other) < separation_mm - 1e-9
                           for other in other_lines)):
                continue
            proposal = (g + math.hypot(xstep * dx, ystep * dy)
                        * (1.0 + float(rubber_repulsion[y, x])))
            if proposal < costs.get(nxt, float("inf")):
                costs[nxt] = proposal
                parents[nxt] = node
                heuristic = math.dist(physical(nxt), physical(end))
                heapq.heappush(queue, (
                    proposal + heuristic, next(sequence), proposal, nxt))
    return None


def rubber_band_routes(
    board: Any,
    endpoints: dict[str, tuple[Point, Point]],
    order: tuple[str, str, str],
    *,
    step_mm: float = .22,
    seconds: float = 65.0,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
    uuid_detours: bool = False,
) -> tuple[
    list[list[tuple[int, float, float]]] | None,
    dict[str, Any],
    dict[str, list[Point]],
]:
    """Plan three crossing-free zero-width F.Cu trees, then inflate via A*.

    Two-terminal target nets have a single path as their minimal spanning
    tree. The zero-width stage does NOT prove 0.15-mm copper is feasible.
    Return the topological reference paths for corridor-biased CBS if the
    finite-width A* inflation fails. Only copper routed by existing native
    A* can be submitted for subsequent DRC and 201-victim restitution.
    """
    import numpy as np
    import pcbnew
    from shapely import contains_xy, prepare
    from shapely.geometry import LineString, Point as ShapelyPoint, box
    from shapely.ops import unary_union
    from route_targeted_closure import (
        obstacles, pad_copper_shape, routing_domain, search, add_path,
        xy,
    )

    if (set(order) != set(TARGETS) or len(order) != 3
            or not .18 <= step_mm <= .35
            or not 20 <= seconds <= 125):
        raise ValueError("Unreviewed topological rubber-band request")
    started = time.monotonic()
    expires = started + seconds
    from probe_block2_uuid_detours import detour_geometry
    hard_detours, detour_diagnostic = (
        detour_geometry(board) if uuid_detours else (None, None))
    coords = [p for name in TARGETS for p in endpoints[name]]
    bbox = board.GetBoardEdgesBoundingBox()
    x0 = max(min(p[0] for p in coords) - 4.4,
             pcbnew.ToMM(bbox.GetX()) + .25)
    x1 = min(max(p[0] for p in coords) + 4.4,
             pcbnew.ToMM(bbox.GetRight()) - .25)
    y0 = max(min(p[1] for p in coords) - 4.4,
             pcbnew.ToMM(bbox.GetY()) + .25)
    y1 = min(max(p[1] for p in coords) + 4.4,
             pcbnew.ToMM(bbox.GetBottom()) - .25)
    xs = np.arange(x0, x1 + step_mm / 2, step_mm)
    ys = np.arange(y0, y1 + step_mm / 2, step_mm)
    diag: dict[str, Any] = {
        "status": "zero_width_started",
        "zero_width_is_not_DRC": True,
        "topology_crossing_free": False,
        "rubber_band_nominal_width_mm": 0.0,
        "inflated_width_mm": .15,
        "actual_width_native_DRC_required": True,
        "no_new_vias": True,
        "In1_Cu_used": False,
        "spanning_tree_paths": {},
        "inflated_micro_hops": {},
        "uuid_detours_enabled": uuid_detours,
        "uuid_detour_diagnostic": detour_diagnostic,
    }
    if (len(xs) < 3 or len(ys) < 3 or len(xs) * len(ys) > 180000):
        diag["status"] = "rubber_grid_unavailable"
        return None, diag, {}
    gx, gy = np.meshgrid(xs, ys)
    window = box(x0, y0, x1, y1)
    domain = routing_domain(board, .000001)
    outside = window.difference(domain)
    reference: dict[str, list[Point]] = {}
    topology_models: dict[str, tuple[Any, Any]] = {}

    def emit(stage: str) -> None:
        diag["last_stage"] = stage
        if progress is not None:
            progress(stage, diag)

    for net in order:
        if time.monotonic() >= expires:
            diag["status"] = "rubber_topology_time_budget"
            return None, diag, reference
        code = board.FindNet(net).GetNetCode()
        physical: list[Any] = [outside]
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() == code or not pad.IsOnLayer(pcbnew.F_Cu):
                    continue
                boundary = pad.GetBoundingBox()
                pad_box = box(pcbnew.ToMM(boundary.GetX()),
                              pcbnew.ToMM(boundary.GetY()),
                              pcbnew.ToMM(boundary.GetRight()),
                              pcbnew.ToMM(boundary.GetBottom()))
                if pad_box.intersects(window):
                    physical.append(pad_copper_shape(pad, pcbnew.F_Cu))
        for track in board.GetTracks():
            if track.GetNetCode() == code:
                continue
            if isinstance(track, pcbnew.PCB_VIA):
                shape = ShapelyPoint(xy(track.GetPosition())).buffer(
                    pcbnew.ToMM(track.GetWidth()) / 2)
            elif track.GetLayer() == pcbnew.F_Cu:
                if isinstance(track, pcbnew.PCB_ARC):
                    bb = track.GetBoundingBox()
                    shape = box(pcbnew.ToMM(bb.GetX()),
                                pcbnew.ToMM(bb.GetY()),
                                pcbnew.ToMM(bb.GetRight()),
                                pcbnew.ToMM(bb.GetBottom()))
                else:
                    shape = LineString([
                        xy(track.GetStart()), xy(track.GetEnd())]).buffer(
                            pcbnew.ToMM(track.GetWidth()) / 2)
            else:
                continue
            if shape.intersects(window):
                physical.append(shape)
        obstacle = unary_union(physical).buffer(1e-9)
        if hard_detours is not None:
            obstacle = obstacle.union(hard_detours)
        prepare(obstacle)
        blocked = contains_xy(obstacle, gx, gy)
        topology_models[net] = (blocked, obstacle)
        path = _rubber_trace(
            xs, ys, blocked, obstacle, endpoints[net][0],
            endpoints[net][1], list(reference.values()), expires)
        if path is None:
            diag["status"] = "zero_width_topology_unavailable"
            diag["blocked_target"] = net
            emit("zero_width_topology_rejected_" + net)
            return None, diag, reference
        reference[net] = path
        diag["spanning_tree_paths"][net] = len(path)
        emit("zero_width_spanning_tree_planned_" + net)
    lines = [LineString(reference[name]) for name in TARGETS]
    diag["topology_crossing_free"] = all(
        not lines[i].intersects(lines[j])
        for i in range(3) for j in range(i + 1, 3))
    if not diag["topology_crossing_free"]:
        raise RuntimeError("Zero-width topological crossing detected")
    diag["rubber_pairwise_minimum_mm"] = min(
        lines[i].distance(lines[j])
        for i in range(3) for j in range(i + 1, 3))
    diag["rubber_repulsion_enabled"] = True
    diag["topology_separation_attempted"] = False
    diag["topology_separated_for_inflation"] = False
    diag["zero_width_initial_minimum_mm"] = diag["rubber_pairwise_minimum_mm"]
    # Width-aware topology re-negotiation is a *proposal only*. The original
    # crossing-free zero-width paths remain the fallback, and only independent
    # KiCad DRC may qualify real copper. Include fixed-copper trace clearance
    # in this step: a zero-width channel can be wider than zero yet still be
    # physically impossible to inflate to 0.15 mm.
    diag["topology_separation_attempts"] = []
    diag["width_aware_fixed_copper"] = False
    if (diag["rubber_pairwise_minimum_mm"] < .30
            and time.monotonic() < expires - 18):
        diag["topology_separation_attempted"] = True
        # Exact three nets => finite set of deterministic priority orders.
        # Try the previously starved net FIRST rather than always anchoring
        # both competing corridor trunks before seeking its escape.
        attempted_orders = []
        priorities = [
            tuple(reversed(order)),
            (order[-1], order[0], order[1]),
            (order[1], order[2], order[0]),
            order,
        ]
        for priority in priorities:
            if priority not in attempted_orders:
                attempted_orders.append(priority)
        width_models = {}
        for net in TARGETS:
            code = board.FindNet(net).GetNetCode()
            geo, _ = obstacles(
                board, code, .15, .15, window, .65,
                (pcbnew.F_Cu, pcbnew.B_Cu))
            inflated_obstacle = geo[0].buffer(-1e-9)
            if hard_detours is not None:
                inflated_obstacle = inflated_obstacle.union(hard_detours)
            prepare(inflated_obstacle)
            width_models[net] = (
                contains_xy(inflated_obstacle, gx, gy),
                inflated_obstacle)
        diag["width_aware_fixed_copper"] = True
        # Do not let permutations consume the inflation/CBS deadline.
        latest = min(expires - 18., time.monotonic() + 42.)
        for priority in attempted_orders:
            if time.monotonic() >= latest:
                break
            separated: dict[str, list[Point]] = {}
            failure = None
            for net in priority:
                if time.monotonic() >= latest:
                    failure = "separation_time_budget"
                    break
                blocked, obstacle = width_models[net]
                proposed = _rubber_trace(
                    xs, ys, blocked, obstacle, endpoints[net][0],
                    endpoints[net][1], list(separated.values()),
                    min(latest, time.monotonic() + 13.),
                    separation_mm=.30001)
                if proposed is None:
                    failure = net
                    break
                separated[net] = proposed
            detail = {
                "priority": priority,
                "reached_nets": list(separated),
                "blocked_target": failure,
                "obstacle_model": "native_fixed_copper_0.15mm_width_clearance",
                "mutual_centreline_mm": .30001,
            }
            diag["topology_separation_attempts"].append(detail)
            emit("width_aware_corridor_priority_checked")
            if len(separated) != 3:
                diag["topology_separation_blocked_target"] = failure
                continue
            proposed_lines = [LineString(separated[name])
                              for name in TARGETS]
            clearance = min(
                proposed_lines[i].distance(proposed_lines[j])
                for i in range(3) for j in range(i + 1, 3))
            detail["minimum_pairwise_mm"] = clearance
            if clearance < .30:
                raise RuntimeError("Width-aware negotiation violated .30 mm")
            reference = separated
            diag["rubber_pairwise_minimum_mm"] = clearance
            diag["topology_separated_for_inflation"] = True
            diag["topology_selected_priority"] = priority
            diag["spanning_tree_paths"] = {
                name: len(reference[name]) for name in TARGETS}
            emit("width_aware_three_corridors_proposed_native_DRC_pending")
            break

    # Exact KiCad source-item UUID inventory on the already stripped scratch
    # board. This is *diagnostic*; 0.10-mm clearance is never activated.
    from probe_block2_clearance_cutset import inspect_cutset
    try:
        diag["fixed_copper_cutset_analysis"] = inspect_cutset(
            board, reference)
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        diag["fixed_copper_cutset_analysis"] = {
            "status": "read_only_cutset_unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc)[:350],
        }
    emit("native_uuid_cutset_diagnosis_completed")
    emit("three_zero_width_spanning_trees_nonintersecting")
    all_routes: list[list[tuple[int, float, float]]] = []
    completed: set[str] = set()
    for net in order:
        trace = reference[net]
        positions = sorted(set(round((len(trace) - 1) * k / 4)
                               for k in (0, 1, 2, 3, 4)))
        if len(positions) != 5:
            diag["status"] = "rubber_waypoint_count_failed"
            return None, diag, reference
        waypoints = [trace[i] for i in positions]
        reserve = [
            LineString(reference[other]).buffer(.35)
            for other in order if other != net and other not in completed
        ]
        planned = []
        for start, end in zip(waypoints, waypoints[1:]):
            if time.monotonic() >= expires:
                diag["status"] = "rubber_inflation_time_budget"
                return None, diag, reference
            proposal = None
            for margin, budget in ((2.0, 12000), (4.2, 24000)):
                proposal = search(
                    board, start, end, board.FindNet(net).GetNetCode(),
                    .15, .15, False, margin, step=.22,
                    max_nodes=budget,
                    deadline=min(time.monotonic() + 12, expires),
                    start_layer=0, goal_layer=0,
                    layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                    cost_regions=tuple((0, region, 85.)
                                       for region in reserve),
                )
                if (proposal is not None and len(proposal) >= 2
                        and all(p[0] == 0 for p in proposal)):
                    if hard_detours is not None and LineString(
                            [(p[1], p[2]) for p in proposal]
                    ).intersects(hard_detours):
                        diag.setdefault("uuid_detour_rejected_hops", []).append(
                            {"net": net, "start": start, "end": end})
                        proposal = None
                    else:
                        break
                proposal = None
            if proposal is None:
                diag["status"] = "rubber_inflation_requires_cbs"
                diag["blocked_target"] = net
                emit("rubber_inflation_boundary_conflict_" + net)
                return None, diag, reference
            add_path(board, proposal, board.FindNet(net).GetNetCode(),
                     .15, layers=(pcbnew.F_Cu, pcbnew.B_Cu))
            planned.extend(proposal if not planned else proposal[1:])
            diag["inflated_micro_hops"][net] = (
                diag["inflated_micro_hops"].get(net, 0) + 1)
        completed.add(net)
        all_routes.append(planned)
        emit("rubber_inflated_target_" + net)
    diag["status"] = "rubber_inflated_three_unverified"
    emit("rubber_inflation_complete_pending_native_DRC")
    return all_routes, diag, reference

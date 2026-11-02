#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded, native-UUID-pinned U4 breakout corridor reservations for CBS3.

This changes only the disposable path planner: protected PCB geometry,
manufacturing clearances, layer rules, copper fills and replay gates stay
unchanged. A failed planning run cannot prove manufacturing infeasibility.
"""
from __future__ import annotations

from typing import Any

CH027_PINS = ("9a811be0", "515dd677")


def verify_u4_escape_group(
    board: Any,
    nets: tuple[int, int, int],
    endpoints: tuple[tuple[tuple[float, float], tuple[float, float]], ...],
) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
    """Find all three native U4 pads and both fixed CH027 F.Cu segments."""
    import math
    import pcbnew
    from route_targeted_closure import xy

    footprints = [f for f in board.GetFootprints()
                  if f.GetReference() == "U4"]
    if len(footprints) != 1 or len(nets) != 3 or len(set(nets)) != 3:
        raise RuntimeError("U4 coupled escape needs one U4 and three target nets")
    pads = list(footprints[0].Pads())
    ports: list[tuple[float, float]] = []
    numbers: list[str] = []
    uuids: list[str] = []
    for i, code in enumerate(nets):
        candidates = [p for p in pads if p.GetNetCode() == code
                      and p.IsOnLayer(pcbnew.F_Cu)]
        if not candidates:
            raise RuntimeError("Missing native F.Cu U4 pad for target agent " +
                               str(i))
        pad = min(candidates, key=lambda p: min(
            math.dist(xy(p.GetPosition()), end) for end in endpoints[i]))
        port = xy(pad.GetPosition())
        if min(math.dist(port, end) for end in endpoints[i]) > 1.2:
            raise RuntimeError("U4 breakout pad not near native target endpoint")
        ports.append(port)
        numbers.append(pad.GetNumber())
        uuids.append(pad.m_Uuid.AsString())
    if len(set(uuids)) != 3:
        raise RuntimeError("Coupled U4 escape pad identity collision")

    protected = {}
    for trace in board.GetTracks():
        uid = trace.m_Uuid.AsString()
        for prefix in CH027_PINS:
            if uid.startswith(prefix):
                if (prefix in protected
                        or trace.GetNetname() != "CH027_N_MUX"
                        or isinstance(trace, pcbnew.PCB_VIA)
                        or trace.GetLayer() != pcbnew.F_Cu):
                    raise RuntimeError("Pinned CH027 U4 protection drift")
                protected[prefix] = uid
    if set(protected) != set(CH027_PINS):
        raise RuntimeError("Pinned CH027 U4 F.Cu trace absent after ripup")

    return tuple(ports), {
        "status": "three_u4_escape_ports_jointly_reserved",
        "U4_pad_UUIDs": uuids,
        "U4_pad_numbers": numbers,
        "CH027_protected_UUIDs": [protected[p] for p in CH027_PINS],
        "no_CH027_ripup": True,
        "no_new_vias": True,
        "native_DRC_still_required": True,
    }


def connected_conflict_corridor(
    segments: list[tuple[Any, Any]],
    rival: Any,
    pivot: Any,
    clearance_mm: float,
    *, max_edges: int = 10,
) -> frozenset[Any]:
    """Ban a contiguous conflict STRAND, not disconnected offending edges.

    Every branch prohibits its own agent's strand; the complementary branch
    prohibits the rival's strand. The bound prevents severing a whole net.
    """
    if not 2 <= max_edges <= 14 or clearance_mm <= 0:
        raise ValueError("Invalid bounded corridor request")
    keys = [key for _, key in segments]
    if pivot not in keys:
        raise ValueError("CBS corridor pivot not in agent path")
    p = keys.index(pivot)
    colliding = [shape.distance(rival) < clearance_mm
                 for shape, _ in segments]
    a = b = p
    while a > 0 and colliding[a-1] and b-a+1 < max_edges-2:
        a -= 1
    while b+1 < len(segments) and colliding[b+1] and b-a+1 < max_edges-2:
        b += 1
    # Buffer one edge at each end, where possible. This disallows
    # immediate re-entry into the same micro-collision corridor.
    if a > 0 and b-a+1 < max_edges:
        a -= 1
    if b+1 < len(segments) and b-a+1 < max_edges:
        b += 1
    return frozenset(keys[a:b+1])


def rasterized_conflict_region_edges(
    corridor: frozenset[Any], xs: Any, ys: Any,
    *, padding_mm: float = .16, max_region_edges: int = 320,
) -> frozenset[Any]:
    """Prohibit ALL local graph edges crossing a bounded spatial corridor.

    Unlike blocking the current route's edges alone, this prevents the next
    CBS child from immediately re-entering the same geometric bottleneck via
    neighbouring diagonal/axial grid edges. Entirely search-local.
    """
    import math
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    if not corridor or not .08 <= padding_mm <= .30:
        raise ValueError("Invalid spatial CBS corridor")
    if not 30 <= max_region_edges <= 500:
        raise ValueError("Unreviewed regional CBS constraint budget")
    if len(xs) < 2 or len(ys) < 2:
        raise ValueError("Grid is not spatial")
    step_x = float(xs[1] - xs[0])
    step_y = float(ys[1] - ys[0])
    if step_x <= 0 or step_y <= 0:
        raise ValueError("Grid orientation changed")

    def point(node: tuple[int, int]) -> tuple[float, float]:
        return float(xs[node[0]]), float(ys[node[1]])

    shapes = [LineString((point(a), point(b))) for a, b in corridor]
    region = unary_union(shapes).buffer(padding_mm, resolution=4)
    minx, miny, maxx, maxy = region.bounds
    def clamp_index(v: float, zero: float, step: float,
                    maximum: int) -> int:
        return max(0, min(maximum, int(math.floor((v - zero)/step))))
    left = clamp_index(minx, float(xs[0]), step_x, len(xs)-1)
    right = clamp_index(maxx, float(xs[0]), step_x, len(xs)-1)+1
    top = clamp_index(miny, float(ys[0]), step_y, len(ys)-1)
    bottom = clamp_index(maxy, float(ys[0]), step_y, len(ys)-1)+1
    result = set(corridor)
    for y in range(top, min(len(ys), bottom+1)):
        for x in range(left, min(len(xs), right+1)):
            a = (x, y)
            for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
                b = (x+dx, y+dy)
                if not (0 <= b[0] < len(xs) and 0 <= b[1] < len(ys)):
                    continue
                if LineString((point(a), point(b))).intersects(region):
                    result.add((a, b) if a <= b else (b, a))
                if len(result) > max_region_edges:
                    # Fail closed to the bounded original region instead of
                    # introducing an unreviewed board-scale search blackout.
                    return corridor
    return frozenset(result)


def adaptive_cbs_regions(
    spatial: frozenset[Any],
    strand: frozenset[Any],
    pivot: Any,
    *,
    expanded: int,
    queued: int,
) -> tuple[tuple[str, frozenset[Any]], ...]:
    """Bounded disjunctive CBS alternatives; never relax native DRC.

    Spatial exclusion remains the preferred child. When the open CBS queue
    shrinks, also retain a weaker but still pivot-forbidden child to avoid
    incorrectly concluding that the entire escape is disconnected. All
    variants forbid the original conflict edge for the branched agent.
    """
    if expanded < 1 or queued < 0 or pivot not in strand or pivot not in spatial:
        raise ValueError("Invalid adaptive CBS corridor constraints")
    if not strand.issubset(spatial):
        raise ValueError("Spatial U4 corridor must cover original strand")
    options: list[tuple[str, frozenset[Any]]] = [("spatial", spatial)]
    if expanded >= 12 and queued < 16 and strand != spatial:
        options.append(("strand", strand))
    if expanded >= 32 and queued < 5:
        single = frozenset((pivot,))
        if all(keys != single for _, keys in options):
            options.append(("single-edge-rescue", single))
    return tuple(options)

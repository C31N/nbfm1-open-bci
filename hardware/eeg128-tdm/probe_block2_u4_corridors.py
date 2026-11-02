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

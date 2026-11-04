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
    telemetry: dict[str, Any] | None = None,
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
                    # A planner-only fallback, never proof of infeasibility.
                    # Preserve the event in the native JSON even if a later
                    # CBS child finds another path.
                    if telemetry is not None:
                        telemetry["CBS3_spatial_limit_fallback_triggered"] = True
                        telemetry["CBS3_spatial_limit_fallback_count"] = (
                            telemetry.get("CBS3_spatial_limit_fallback_count", 0) + 1)
                        telemetry["CBS3_spatial_limit_fallback_last_edges"] = len(result)
                        telemetry["CBS3_spatial_limit_fallback_limit"] = max_region_edges
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


def deterministic_u4_fanout_geometry(
    ports: tuple[tuple[float,float],...],
    endpoints: tuple[tuple[tuple[float,float],
                           tuple[float,float]],...],
    *, lead_mm: float = 1.5,
    parallel_mm: float = 1.5, pitch_mm: float = .300,
) -> tuple[tuple[tuple[tuple[float,float],...],...],
           tuple[int,...],tuple[float,float],dict[str,Any]]:
    """Generate pad/knee/tip wires with a straight 1.5-mm parallel section.

    No board changes; physical copper must pass native obstacle and DRC gates.
    """
    import math
    from shapely.geometry import LineString
    if (len(ports) != 3 or len(endpoints) != 3
            or not 1.5 <= lead_mm <= 3.5
            or not 1.5 <= parallel_mm <= 2.5 or pitch_mm != .300):
        raise RuntimeError("Unreviewed U4 fanout geometry")
    spans = [max(p[a] for p in ports)-min(p[a] for p in ports)
             for a in (0, 1)]
    tangent = 0 if spans[0] >= spans[1] else 1
    normal_axis = 1-tangent
    if spans[tangent] < .600 or spans[normal_axis] > .065:
        raise RuntimeError("U4 pads not on a common straight pitch row")
    rank = sorted(range(3), key=lambda i: ports[i][tangent])
    if any(ports[b][tangent]-ports[a][tangent] < .300-1e-9
           for a,b in zip(rank,rank[1:])):
        raise RuntimeError("U4 native pad pitch too narrow")
    sides, others = [], []
    for i,port in enumerate(ports):
        gaps = [math.dist(port,p) for p in endpoints[i]]
        side = 0 if gaps[0] <= gaps[1] else 1
        if gaps[side] > 1.2:
            raise RuntimeError("Target end is not at verified U4 pad")
        sides.append(side)
        others.append(endpoints[i][1-side])
    center = [sum(p[a] for p in ports)/3 for a in (0,1)]
    sign = (1. if sum(p[normal_axis]-ports[i][normal_axis]
                      for i,p in enumerate(others))>0 else -1.)
    if any(sign*(other[normal_axis]-ports[i][normal_axis])
           <= lead_mm + parallel_mm + .3 for i,other in enumerate(others)):
        raise RuntimeError("No common outward U4 fanout direction")
    wires = [None, None, None]
    for j,i in enumerate(rank):
        knee = list(center)
        knee[tangent] += (j-1)*pitch_mm
        knee[normal_axis] += sign*lead_mm
        tip = list(knee)
        tip[normal_axis] += sign*parallel_mm
        wires[i] = (ports[i],tuple(knee),tuple(tip))
    for a,b in zip(rank,rank[1:]):
        if abs(math.dist(wires[a][-1],wires[b][-1])-.300)>1e-8:
            raise RuntimeError("Parallel fanout pitch drift")
    clearance = min(LineString(wires[i]).distance(LineString(wires[j]))
                    for i in range(3) for j in range(i+1,3))
    if clearance < .300-1e-8:
        raise RuntimeError("Fanout tracks violate 0.300-mm pitch")
    normal = (sign,0.) if normal_axis==0 else (0.,sign)
    return tuple(wires),tuple(sides),normal,{
        "status":"u4_fanout_planned_not_DRC_qualified",
        "fanout_paths_mm":wires, "pad_side":sides,
        "tip_pitch_mm":.300, "minimum_centerline_mm":clearance,
        "parallel_length_mm":parallel_mm, "transition_mm":lead_mm,
        "no_new_vias":True, "native_DRC_still_required":True,
    }



def _native_fanout_blockers(
    board: Any, net_code: int, line: Any,
) -> list[dict[str,Any]]:
    """Name native F.Cu pads/tracks responsible for a rejected fanout."""
    import pcbnew
    from shapely.geometry import LineString,Point,box
    from route_targeted_closure import (
        pad_copper_shape,xy,POWER,ANALOG_REFERENCE,
    )
    result: list[dict[str,Any]]=[]
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode()==net_code or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            raw=pad_copper_shape(pad,pcbnew.F_Cu)
            gap=line.distance(raw)
            needed=.075+(.20 if pad.GetNetname() in POWER | ANALOG_REFERENCE
                          else .15)
            if gap < needed-1e-8:
                result.append({
                    "kind":"pad","ref":footprint.GetReference(),
                    "pad":pad.GetNumber(),"net":pad.GetNetname(),
                    "UUID":pad.m_Uuid.AsString(),
                    "distance_mm":round(gap,6),
                    "required_mm":round(needed,6),
                    "deficit_mm":round(needed-gap,6)})
    for tr in board.GetTracks():
        if tr.GetNetCode()==net_code:
            continue
        if not isinstance(tr,pcbnew.PCB_VIA) and tr.GetLayer()!=pcbnew.F_Cu:
            continue
        if isinstance(tr,pcbnew.PCB_VIA):
            copper=Point(xy(tr.GetPosition())).buffer(pcbnew.ToMM(tr.GetWidth())/2)
        elif isinstance(tr,pcbnew.PCB_ARC):
            b=tr.GetBoundingBox()
            copper=box(pcbnew.ToMM(b.GetX()),pcbnew.ToMM(b.GetY()),
                       pcbnew.ToMM(b.GetRight()),pcbnew.ToMM(b.GetBottom()))
        else:
            copper=LineString((xy(tr.GetStart()),xy(tr.GetEnd()))).buffer(
                pcbnew.ToMM(tr.GetWidth())/2)
        gap=line.distance(copper)
        needed=.075+(.20 if tr.GetNetname() in POWER | ANALOG_REFERENCE
                      else .15)
        if gap < needed-1e-8:
            result.append({
                "kind":"via" if isinstance(tr,pcbnew.PCB_VIA) else "track",
                "net":tr.GetNetname(),"UUID":tr.m_Uuid.AsString(),
                "distance_mm":round(gap,6),
                "required_mm":round(needed,6),
                "deficit_mm":round(needed-gap,6)})
    return sorted(result,key=lambda r:(-r["deficit_mm"],r["UUID"]))[:5]


def native_u4_fanout_preflight(
    board: Any, ports: tuple[tuple[float,float],...],
    nets: tuple[int,int,int],
    endpoints: tuple[tuple[tuple[float,float],
                           tuple[float,float]],...],
) -> tuple[tuple[tuple[tuple[float,float],...],...],
           tuple[int,...],tuple[float,float],dict[str,Any]]:
    """Select the first legal deterministic native F.Cu fanout, or reject."""
    import pcbnew
    from shapely.geometry import LineString,box
    from route_targeted_closure import obstacles,xy
    if len(nets)!=3 or len(set(nets))!=3:
        raise RuntimeError("U4 needs three distinct target nets")
    protected = [
        t for t in board.GetTracks()
        if any(t.m_Uuid.AsString().startswith(p) for p in CH027_PINS)]
    if (len(protected)!=2 or any(
        t.GetNetname()!="CH027_N_MUX"
        or t.GetLayer()!=pcbnew.F_Cu
        or isinstance(t,pcbnew.PCB_VIA) for t in protected)):
        raise RuntimeError("U4 protected CH027 native tracks changed")
    bounds=board.GetBoardEdgesBoundingBox()
    low=(pcbnew.ToMM(bounds.GetX())+.56,
         pcbnew.ToMM(bounds.GetY())+.56)
    high=(pcbnew.ToMM(bounds.GetRight())-.56,
          pcbnew.ToMM(bounds.GetBottom())-.56)
    failed=[]
    for lead_mm in (1.5,2.,2.5,3.):
        try:
            wires,sides,normal,diag=deterministic_u4_fanout_geometry(
                ports,endpoints,lead_mm=lead_mm)
            if any(not (low[0] <= x <= high[0] and
                        low[1] <= y <= high[1])
                   for wire in wires for x,y in wire):
                raise RuntimeError("Fanout outside protected board border")
            pts=[p for wire in wires for p in wire]
            region=box(min(p[0] for p in pts)-1.,
                       min(p[1] for p in pts)-1.,
                       max(p[0] for p in pts)+1.,
                       max(p[1] for p in pts)+1.)
            for i,wire in enumerate(wires):
                line=LineString(wire)
                for track in protected:
                    d=line.distance(LineString((
                        xy(track.GetStart()),xy(track.GetEnd()))))
                    min_d=(.15+pcbnew.ToMM(track.GetWidth()))/2+.15
                    if d < min_d-1e-8:
                        raise RuntimeError("CH027 protected copper clearance")
                shape,_=obstacles(board,nets[i],.15,.15,region,.65,
                                  (pcbnew.F_Cu,pcbnew.B_Cu))
                if line.relate_pattern(shape[0].buffer(-1e-9),"T********"):
                    blocking=_native_fanout_blockers(board,nets[i],line)
                    raise RuntimeError(
                        "agent="+str(i)+" blocked_by="+str(blocking)[:450]
                        if blocking else
                        "agent="+str(i)+" routing_domain_or_zone_blocked")
            diag["CH027_protected_UUIDs"]=[
                t.m_Uuid.AsString() for t in protected]
            diag["native_obstacle_preflight_passed"]=True
            return wires,sides,normal,diag
        except RuntimeError as exc:
            failed.append({"lead_mm":lead_mm,"reason":str(exc)[:480]})
    raise RuntimeError("No legal deterministic fanout: "+str(failed)[:2800])


def validate_fcu_three_paths(
    board: Any,nets: tuple[int,int,int],
    routes: list[list[tuple[int,float,float]]],
) -> dict[str,Any]:
    """No-restoration geometric gate; KiCad after full restitution is final."""
    import pcbnew
    from shapely.geometry import LineString,box
    from route_targeted_closure import obstacles
    if len(routes)!=3 or len(set(nets))!=3:
        raise RuntimeError("Complete three-net fanout required")
    if any(len(route)<2 or any(p[0]!=0 for p in route)
           for route in routes):
        raise RuntimeError("Non F.Cu point / via in target bundle")
    lines=[LineString([(x,y) for _,x,y in route]) for route in routes]
    gap=min(lines[i].distance(lines[j])
            for i in range(3) for j in range(i+1,3))
    if gap < .300-1e-8:
        raise RuntimeError("Triplet lines violate 0.300-mm clearance")
    for i,line in enumerate(lines):
        x0,y0,x1,y1=line.bounds
        shape,_=obstacles(board,nets[i],.15,.15,
                          box(x0-1.,y0-1.,x1+1.,y1+1.),.65,
                          (pcbnew.F_Cu,pcbnew.B_Cu))
        if line.relate_pattern(shape[0].buffer(-1e-9),"T********"):
            raise RuntimeError("Triplet crosses fixed native copper")
    return {"status":"three_FCu_paths_geometrically_preflighted_only",
            "minimum_centerline_mm":gap,
            "all_201_whitelist_victims_still_required":True,
            "native_DRC_still_required":True}

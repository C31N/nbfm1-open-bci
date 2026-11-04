#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic, fail-closed lateral U4 fanout proposals on disposable F.Cu.

Stage 1: isolated U4 pad escapes.
Stage 2: simultaneous lateral dog-leg around the exact immutable U3:7 pad.
Stage 3: consolidate into 1.5-mm parallel 0.300-mm centre-pitch copper.

The planner never edits the board, zones, vias, pads or protected tracks.
Native KiCad 8.0.9 DRC/restitution/parity/replay remain separate gates.
"""
from __future__ import annotations

import math
from typing import Any

Point = tuple[float, float]
Endpoints = tuple[tuple[Point, Point], ...]
Wires = tuple[tuple[Point, ...], ...]
U3_PAD7_UUID = "e37256fc-3b9f-435d-8042-f7d4c1147aca"


def build_u4_lateral_dogleg(
    ports: tuple[Point, ...], endpoints: Endpoints,
    obstacle_bounds: tuple[float, float, float, float],
    *, side: int, lateral_mm: float, escape_mm: float,
    dogleg_run_mm: float, taper_mm: float = 1.8,
    parallel_mm: float = 1.5, pitch_mm: float = .300,
) -> tuple[Wires, tuple[int, ...], Point, dict[str, Any]]:
    """Pure geometric candidate, ordered by each actual target net.

    The lateral shift is applied to all agents together, preserving order.
    A final monotone taper consolidates the original row pitch to 0.300 mm.
    The candidate is *unqualified* until checked against native KiCad copper.
    """
    from shapely.geometry import LineString, box

    if (len(ports) != 3 or len(endpoints) != 3
            or len(set(ports)) != 3
            or side not in (-1, 1)
            or not .15 <= escape_mm <= 1.2
            or not .45 <= dogleg_run_mm <= 6.0
            or not 1.0 <= taper_mm <= 3.5
            or not 1.5 <= parallel_mm <= 2.5
            or pitch_mm != .300
            or not .4 <= abs(lateral_mm) <= 9.5
            or side * lateral_mm <= 0):
        raise RuntimeError("Unreviewed U4 dog-leg geometry")
    spans = [max(p[a] for p in ports)-min(p[a] for p in ports)
             for a in (0, 1)]
    tangent = 0 if spans[0] >= spans[1] else 1
    normal_axis = 1-tangent
    if spans[tangent] < .600 or spans[normal_axis] > .065:
        raise RuntimeError("U4 pad row geometry mismatch")
    rank = sorted(range(3), key=lambda i: ports[i][tangent])
    if any(ports[b][tangent]-ports[a][tangent] < .300-1e-8
           for a,b in zip(rank,rank[1:])):
        raise RuntimeError("U4 native pad pitch below 0.300 mm")
    sides: list[int] = []
    other: list[Point] = []
    for i,port in enumerate(ports):
        dist = (math.dist(port,endpoints[i][0]),
                math.dist(port,endpoints[i][1]))
        pad_side = 0 if dist[0] <= dist[1] else 1
        if dist[pad_side] > 1.2:
            raise RuntimeError("Native target end not near U4 pin")
        sides.append(pad_side)
        other.append(endpoints[i][1-pad_side])
    center = tuple(sum(p[a] for p in ports)/3 for a in (0, 1))
    sign = (1. if sum(other[i][normal_axis]-ports[i][normal_axis]
                      for i in range(3)) > 0 else -1.)
    normal: Point = (sign, 0.) if normal_axis == 0 else (0., sign)
    axis_min = obstacle_bounds[tangent]
    axis_max = obstacle_bounds[tangent+2]
    # The entire row must be laterally outside the protected pad's
    # 0.225-mm minimum centreline-to-pad copper clearance.
    shifted = [p[tangent]+lateral_mm for p in ports]
    if side == 1 and min(shifted) <= axis_max+.30:
        raise RuntimeError("Right dog-leg does not clear U3 pad laterally")
    if side == -1 and max(shifted) >= axis_min-.30:
        raise RuntimeError("Left dog-leg does not clear U3 pad laterally")
    # U3 must be behind the consolidation stage in the outward direction.
    normal_corners = (obstacle_bounds[normal_axis],
                      obstacle_bounds[normal_axis+2])
    obstacle_far = max(sign*(v-center[normal_axis])
                       for v in normal_corners)
    bypass = max(escape_mm+dogleg_run_mm+.30, obstacle_far+.50)
    bundle_start = bypass+taper_mm
    tip_displacement = bundle_start+parallel_mm
    if any(sign*(p[normal_axis]-ports[i][normal_axis])
           <= tip_displacement+.30 for i,p in enumerate(other)):
        raise RuntimeError("Dog-leg tip extends beyond target-side endpoints")

    paths: list[tuple[Point, ...] | None] = [None,None,None]
    for r,i in enumerate(rank):
        p = list(ports[i])
        isolated = list(p)
        isolated[normal_axis] += sign*escape_mm
        elbow = list(isolated)
        elbow[tangent] += lateral_mm
        elbow[normal_axis] += sign*dogleg_run_mm
        past = list(elbow)
        past[normal_axis] = center[normal_axis]+sign*bypass
        consolidated = list(past)
        consolidated[tangent] = (
            center[tangent]+lateral_mm+(r-1)*pitch_mm)
        consolidated[normal_axis] = center[normal_axis]+sign*bundle_start
        tip = list(consolidated)
        tip[normal_axis] += sign*parallel_mm
        paths[i] = (ports[i],tuple(isolated),tuple(elbow),
                    tuple(past),tuple(consolidated),tuple(tip))
    if any(path is None for path in paths):
        raise RuntimeError("Three target fanouts not constructed")
    wires: Wires = tuple(path for path in paths if path is not None)
    lines = [LineString(path) for path in wires]
    distance = min(lines[i].distance(lines[j])
                   for i in range(3) for j in range(i+1,3))
    if distance < pitch_mm-1e-8:
        raise RuntimeError("Dog-leg three-net centreline conflict")
    u3 = box(*obstacle_bounds)
    obstacle_gap = min(line.distance(u3) for line in lines)
    if obstacle_gap < .225-1e-8:
        raise RuntimeError("Dog-leg U3:7 clearance below 0.225 mm")
    tips = sorted(p[-1][tangent] for p in wires)
    if (abs(tips[1]-tips[0]-pitch_mm)>1e-8
            or abs(tips[2]-tips[1]-pitch_mm)>1e-8):
        raise RuntimeError("Dog-leg bundle pitch not exactly 0.300 mm")
    return wires,tuple(sides),normal,{
        "status":"u4_lateral_dogleg_proposed_unverified",
        "stages":["isolated_escape","lateral_dogleg","parallel_bundle"],
        "fanout_paths_mm":wires,
        "pad_side":sides, "pad_rank":rank,
        "dogleg_side":side,
        "lateral_shift_mm":lateral_mm,
        "escape_length_mm":escape_mm,
        "dogleg_run_mm":dogleg_run_mm,
        "obstacle_far_mm":obstacle_far,
        "bypass_normal_mm":bypass,
        "transition_mm":bundle_start,
        "parallel_length_mm":parallel_mm,
        "tip_normal_displacement_mm":tip_displacement,
        "tip_pitch_mm":pitch_mm,
        "minimum_centerline_mm":distance,
        "u3_pad7_bbox_clearance_mm":obstacle_gap,
        "no_new_vias":True,
        "physical_DRC_still_required":True,
    }


def native_u4_lateral_preflight(
    board: Any, ports: tuple[Point, ...], nets: tuple[int,int,int],
    endpoints: Endpoints,
) -> tuple[Wires, tuple[int,...], Point, dict[str,Any]]:
    """Evaluate a finite deterministic candidate set against immutable copper.

    Raise a bounded diagnosis instead of routing through protected geometry.
    The U3 pad, CH027 segments, U4 pads and all other native F.Cu copper
    are treated as immutable. Do not infer DRC, parity or 136 acceptance.
    """
    import pcbnew
    from shapely.geometry import LineString, box
    from route_targeted_closure import obstacles, pad_copper_shape, xy
    from probe_block2_u4_corridors import CH027_PINS, _native_fanout_blockers

    if len(nets)!=3 or len(set(nets))!=3:
        raise RuntimeError("Three distinct U4 target nets required")
    footprints = [f for f in board.GetFootprints()
                  if f.GetReference()=="U3"]
    if len(footprints)!=1:
        raise RuntimeError("Protected U3 footprint missing or duplicated")
    hits = [p for p in footprints[0].Pads()
            if p.GetNumber()=="7" and p.m_Uuid.AsString()==U3_PAD7_UUID
            and p.GetNetname()=="CH018_P_MUX"
            and p.IsOnLayer(pcbnew.F_Cu)]
    if len(hits)!=1:
        raise RuntimeError("Protected U3 pin 7 UUID/net/geometry drift")
    u3_raw = pad_copper_shape(hits[0],pcbnew.F_Cu)
    u3_bounds = u3_raw.bounds
    protected = [tr for tr in board.GetTracks()
                 if any(tr.m_Uuid.AsString().startswith(uid)
                        for uid in CH027_PINS)]
    if (len(protected)!=2
            or {tr.m_Uuid.AsString()[:8] for tr in protected}
               != set(CH027_PINS)
            or any(tr.GetNetname()!="CH027_N_MUX"
                   or tr.GetLayer()!=pcbnew.F_Cu
                   or isinstance(tr,pcbnew.PCB_VIA)
                   for tr in protected)):
        raise RuntimeError("Protected CH027 F.Cu source changed")
    bounds=board.GetBoardEdgesBoundingBox()
    low=(pcbnew.ToMM(bounds.GetX())+.56,
         pcbnew.ToMM(bounds.GetY())+.56)
    high=(pcbnew.ToMM(bounds.GetRight())-.56,
          pcbnew.ToMM(bounds.GetBottom())-.56)
    span = [max(p[a] for p in ports)-min(p[a] for p in ports)
            for a in (0,1)]
    tangent = 0 if span[0]>=span[1] else 1
    min_t,max_t=min(p[tangent] for p in ports),max(p[tangent] for p in ports)
    shifts=(-max(.4,max_t-u3_bounds[tangent]+.35),
            max(.4,u3_bounds[tangent+2]-min_t+.35))
    candidates=[]
    rejected=[]
    reject_counts: dict[str,int]={}
    side_samples: dict[int,list[dict[str,Any]]]={-1:[],1:[]}
    for side,shift0 in ((-1,shifts[0]),(1,shifts[1])):
        for extra in (0.,.55,1.3,2.2):
            lateral=shift0+side*extra
            for escape in (.18,.36,.65,.90):
                for factor in (.36,.65):
                    dogleg_run=max(.45,abs(lateral)*factor)
                    try:
                        proposal=build_u4_lateral_dogleg(
                            ports,endpoints,u3_bounds,
                            side=side,lateral_mm=lateral,
                            escape_mm=escape,dogleg_run_mm=dogleg_run)
                    except RuntimeError as exc:
                        event={"side":side,"shift":round(lateral,3),
                               "escape":escape,"stage":"pure_geometry",
                               "reason":str(exc)[:95]}
                        rejected.append(event)
                        reject_counts["geometry"] = (
                            reject_counts.get("geometry",0)+1)
                        if len(side_samples[side])<3:
                            side_samples[side].append(event)
                        continue
                    candidates.append(proposal)
    if not candidates:
        raise RuntimeError(
            "No geometric dogleg: "+str(rejected[:8])[:1200])
    coords=[p for wires,_,_,_ in candidates
            for wire in wires for p in wire]
    window=box(min(p[0] for p in coords)-.9,
               min(p[1] for p in coords)-.9,
               max(p[0] for p in coords)+.9,
               max(p[1] for p in coords)+.9)
    # Each inflated fixed-copper geometry is computed ONCE per agent.
    fixed=[obstacles(board,nets[i],.15,.15,window,.65,
                     (pcbnew.F_Cu,pcbnew.B_Cu))[0][0].buffer(-1e-9)
           for i in range(3)]
    ch027=[
        (LineString((xy(tr.GetStart()),xy(tr.GetEnd()))),
         (.15+pcbnew.ToMM(tr.GetWidth()))/2+.15)
        for tr in protected]
    tested=0
    for wires,sides,normal,diag in candidates:
        tested+=1
        reason=None
        if any(not (low[0]<=x<=high[0] and low[1]<=y<=high[1])
               for wire in wires for x,y in wire):
            reason="board_edge"
        if reason is None:
            for i,wire in enumerate(wires):
                line=LineString(wire)
                if any(line.distance(shape)<minimum-1e-8
                       for shape,minimum in ch027):
                    reason="CH027_protected_copper"
                    break
                if line.relate_pattern(fixed[i],"T********"):
                    reason="native_FCu_obstacle"
                    break
        if reason is not None:
            side=diag["dogleg_side"]
            key=str(side)+":"+reason
            reject_counts[key]=reject_counts.get(key,0)+1
            if len(side_samples[side])<5:
                blockers=(
                    _native_fanout_blockers(board,nets[i],line)
                    if reason=="native_FCu_obstacle" else [])
                side_samples[side].append({
                    "side":side,
                    "shift":round(diag["lateral_shift_mm"],4),
                    "escape":diag["escape_length_mm"],
                    "stage":reason,
                    "agent":i if reason!="board_edge" else None,
                    "blocked_by":blockers[:2]})
            continue
        diag.update(
            u3_pin7_UUID=U3_PAD7_UUID,
            u3_pin7_bounds_mm=u3_bounds,
            CH027_protected_UUIDs=sorted(
                tr.m_Uuid.AsString() for tr in protected),
            tested_dogleg_candidates=tested,
            candidate_count=len(candidates),
            native_obstacle_preflight_passed=True,
            fixed_copper_unchanged=True,
        )
        return wires,sides,normal,diag
    import json
    summary={
        "candidate_count":len(candidates),
        "tested":tested,
        "U4_ports_mm":ports,
        "U3_pad7_UUID":U3_PAD7_UUID,
        "U3_pad7_bounds_mm":tuple(round(v,5) for v in u3_bounds),
        "CH027_segments":[{
            "UUID":tr.m_Uuid.AsString(),
            "start":xy(tr.GetStart()),"end":xy(tr.GetEnd()),
        } for tr in protected],
        "reject_counts":reject_counts,
        "left_samples":side_samples[-1],
        "right_samples":side_samples[1],
    }
    raise RuntimeError(
        "U4_lateral_dogleg_native_blocked: "
        +json.dumps(summary,separators=(",",":"),sort_keys=True)[:6000])

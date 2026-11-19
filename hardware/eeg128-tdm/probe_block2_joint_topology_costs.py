#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Pure topological and weighted-A* aids for native F.Cu mid-point routing.

NO topology filter is hard unless a separately certified monotone
corridor exists. A planar path may detour around the end of an obstacle,
so global projected order is not a mathematically valid pruning proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any,Callable,Sequence

Point=tuple[float,float]


@dataclass(frozen=True)
class WindowBox:
    xmin:float
    ymin:float
    xmax:float
    ymax:float

    def __post_init__(self)->None:
        if self.xmin>=self.xmax or self.ymin>=self.ymax:
            raise ValueError("Invalid local conflict window")

    def contains(self,p:Point)->bool:
        return self.xmin<=p[0]<=self.xmax and self.ymin<=p[1]<=self.ymax


class PlanarOrderFilter:
    """Crossing-order cost, hard only with explicit monotone certification."""

    def __init__(self,starts:Sequence[Point],goals:Sequence[Point],
                 axis:Point,*,tolerance_mm:float=.05,
                 certified_monotone_region:bool=False,
                 inversion_weight:float=.8)->None:
        if len(starts)!=3 or len(goals)!=3:
            raise ValueError("Exactly three planar tracks required")
        norm=math.hypot(*axis)
        if norm<=1e-12:
            raise ValueError("Ordering axis must be nonzero")
        self.axis=axis[0]/norm,axis[1]/norm
        self.tol=tolerance_mm
        self.weight=inversion_weight
        def proj(p:Point)->float:
            return p[0]*self.axis[0]+p[1]*self.axis[1]
        self.order=tuple(sorted(range(3),key=lambda i:(proj(starts[i]),i)))
        goal_order=tuple(sorted(range(3),key=lambda i:(proj(goals[i]),i)))
        self.hard=(certified_monotone_region and
                   self.order==goal_order)
        self.start_goal_order_matches=self.order==goal_order

    def evaluate(self,points:Sequence[Point])->tuple[bool,float]:
        if len(points)!=3:
            raise ValueError("Incomplete bundle")
        vals=[p[0]*self.axis[0]+p[1]*self.axis[1] for p in points]
        pen=sum(max(0.,vals[i]-vals[j]-self.tol)
                for i,j in zip(self.order,self.order[1:]))
        return (not (self.hard and pen>0.),
                self.weight*pen)


class WallHuggingCost:
    """Cost using already inflated, read-only native F.Cu copper shapes."""

    def __init__(self,clearance_to_buffered_copper:Callable[[int,Point],float],
                 *,hug_band_mm:float=.50,
                 hug_weight:float=.16)->None:
        if hug_band_mm<=0 or hug_weight<0:
            raise ValueError("Invalid soft wall cost")
        self.fn=clearance_to_buffered_copper
        self.band=hug_band_mm
        self.weight=hug_weight
        self.cache:dict[tuple[int,Point],float]={}

    def cost(self,agent:int,p:Point)->float:
        k=agent,p
        if k not in self.cache:
            # The underlying exact native copper masks already enforce
            # the clearance. This must not add .225 mm a second time.
            d=self.fn(agent,p)
            if not math.isfinite(d):
                # The obstacle union may legitimately be empty. That is
                # unobstructed open space, never invalid copper clearance.
                d=self.band
            self.cache[k]=self.weight*min(max(d,0.)/self.band,1.)
        return self.cache[k]


def octile_distance(a:Point,b:Point)->float:
    dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
    return max(dx,dy)+(math.sqrt(2.)-1.)*min(dx,dy)


class JointHeuristic:
    def __init__(self,goals:Sequence[Point],*,gate_point:Point|None=None,
                 gate_x_threshold:float|None=None,
                 corridor_capacity:int=1,congestion_weight:float=.4,
                 epsilon:float=1.2)->None:
        if len(goals)!=3 or not 1.<=epsilon<=1.3:
            raise ValueError("Unsupported three-net heuristic")
        self.goals=tuple(goals)
        self.gate_point=gate_point
        self.threshold=gate_x_threshold
        self.capacity=max(1,corridor_capacity)
        self.congestion=max(0.,congestion_weight)
        self.epsilon=epsilon

    def estimate(self,points:Sequence[Point])->float:
        h=0.
        approaching=0
        for i,p in enumerate(points):
            goal=self.goals[i]
            if (self.gate_point is not None and
                    self.threshold is not None and
                    p[0]<self.threshold<=goal[0]):
                # Only a HEURISTIC preference: no gate is forced.
                h+=octile_distance(p,self.gate_point)+octile_distance(
                    self.gate_point,goal)
                approaching+=1
            else:
                h+=octile_distance(p,goal)
        h+=self.congestion*max(0,approaching-self.capacity)
        return h*self.epsilon


def find_midpoint_connection(
    forward:dict[tuple[Point,Point,Point],float],
    backward:dict[tuple[Point,Point,Point],float],
    *,
    max_gap_mm:float=.5,
    exact_bridge_validate:Callable[
        [tuple[Point,Point,Point],tuple[Point,Point,Point]],bool],
)->tuple[Any,Any,float]|None:
    """Band candidate is returned ONLY after exact native bridge clearance.

    No simple distance-tolerance match can ever claim copper closure.
    """
    if not 0.<max_gap_mm<=.60:
        raise ValueError("Unreviewed midpoint tolerance")
    best=None
    for a,g_a in forward.items():
        for b,g_b in backward.items():
            sep=max(math.dist(p,q) for p,q in zip(a,b))
            if sep>max_gap_mm+1e-9 or not exact_bridge_validate(a,b):
                continue
            total=g_a+g_b+sep
            if best is None or total<best[2]:
                best=a,b,total
    return best


def conflict_window(center:Point=(48.145,35.750),
                    half_width_mm:float=2.5)->WindowBox:
    if not .5<=half_width_mm<=10.:
        raise ValueError("Unreviewed conflict region")
    return WindowBox(center[0]-half_width_mm,
                     center[1]-half_width_mm,
                     center[0]+half_width_mm,
                     center[1]+half_width_mm)

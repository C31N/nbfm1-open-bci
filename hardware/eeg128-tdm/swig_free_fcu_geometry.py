#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""SWIG-free exact planar gaps for straight F.Cu capsules, vias and simple pads.

Only supported primitive pairs are exact. This module does NOT polygonize
KiCad arcs, custom/rounded pads, zones or solder mask. For those shapes the
caller must retain native geometry and qualify any mixed-source measurement.
No board mutation, routing or fabrication operations are performed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

Point = tuple[float, float]


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, k: float) -> Vec2:
        return Vec2(self.x * k, self.y * k)

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def norm_sq(self) -> float:
        return self.dot(self)

    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def rotate(self, angle: float) -> Vec2:
        c, s = math.cos(angle), math.sin(angle)
        return Vec2(c * self.x - s * self.y, s * self.x + c * self.y)


@dataclass(frozen=True)
class CuPrimitive:
    kind: str  # TRACK, VIA, CIRCLE, RECT_PAD, OVAL_PAD
    a: Vec2
    b: Vec2
    radius_mm: float = 0.
    width_mm: float = 0.
    height_mm: float = 0.
    angle_rad: float = 0.

    def __post_init__(self) -> None:
        vals = (self.a.x, self.a.y, self.b.x, self.b.y,
                self.radius_mm, self.width_mm, self.height_mm,
                self.angle_rad)
        if not all(math.isfinite(v) for v in vals):
            raise ValueError("Nonfinite copper primitive")
        if self.radius_mm < 0. or self.width_mm < 0. or self.height_mm < 0.:
            raise ValueError("Negative copper dimensions")
        if self.kind not in ("TRACK", "VIA", "CIRCLE", "RECT_PAD", "OVAL_PAD"):
            raise ValueError("Unsupported copper primitive")
        if self.kind in ("RECT_PAD", "OVAL_PAD") and (
            self.width_mm <= 0. or self.height_mm <= 0.
        ):
            raise ValueError("Zero area pad")

    @property
    def bbox_mm(self) -> tuple[float,float,float,float]:
        if self.kind == "RECT_PAD":
            pts = _rect_corners(self)
            return (min(p.x for p in pts), min(p.y for p in pts),
                    max(p.x for p in pts), max(p.y for p in pts))
        a,b,r = _axis(self)
        return (min(a.x,b.x)-r,min(a.y,b.y)-r,
                max(a.x,b.x)+r,max(a.y,b.y)+r)


def _clamp(v: float, lo: float=0., hi: float=1.) -> float:
    return min(hi, max(lo,v))


def closest_point_on_segment(p: Vec2, a: Vec2, b: Vec2) -> tuple[Vec2,float]:
    d=b-a
    t=_clamp((p-a).dot(d)/d.norm_sq()) if d.norm_sq()>1e-24 else 0.
    return a+d*t,t


def closest_points_between_segments(
    p1:Vec2,q1:Vec2,p2:Vec2,q2:Vec2
)->tuple[Vec2,Vec2,float]:
    # Closest points for two finite 2-D segments, including degenerate axes.
    d1=q1-p1
    d2=q2-p2
    r=p1-p2
    a=d1.norm_sq()
    e=d2.norm_sq()
    f=d2.dot(r)
    if a<=1e-24 and e<=1e-24:
        return p1,p2,(p1-p2).norm()
    if a<=1e-24:
        s,t=0.,_clamp(f/e)
    else:
        c=d1.dot(r)
        if e<=1e-24:
            t,s=0.,_clamp(-c/a)
        else:
            b=d1.dot(d2)
            den=a*e-b*b
            s=_clamp((b*f-c*e)/den) if den>1e-24 else 0.
            t=(b*s+f)/e
            if t<0.:
                t,s=0.,_clamp(-c/a)
            elif t>1.:
                t,s=1.,_clamp((b-c)/a)
    x,y=p1+d1*s,p2+d2*t
    return x,y,(x-y).norm()


def _rect_corners(p:CuPrimitive)->tuple[Vec2,...]:
    w,h=p.width_mm/2.,p.height_mm/2.
    return tuple(p.a+v.rotate(p.angle_rad) for v in (
        Vec2(-w,-h),Vec2(w,-h),Vec2(w,h),Vec2(-w,h)))


def _rect_edges(p:CuPrimitive)->tuple[tuple[Vec2,Vec2],...]:
    q=_rect_corners(p)
    return tuple((q[i],q[(i+1)%4]) for i in range(4))


def _within_rect(p:Vec2,r:CuPrimitive)->bool:
    v=(p-r.a).rotate(-r.angle_rad)
    return (abs(v.x)<=r.width_mm/2.+1e-12 and
            abs(v.y)<=r.height_mm/2.+1e-12)


def _axis(p:CuPrimitive)->tuple[Vec2,Vec2,float]:
    if p.kind=="RECT_PAD":
        raise ValueError("Rectangle has no capsule axis")
    if p.kind=="OVAL_PAD":
        if p.width_mm>=p.height_mm:
            radius=p.height_mm/2.
            shift=Vec2((p.width_mm-p.height_mm)/2.,0.).rotate(p.angle_rad)
        else:
            radius=p.width_mm/2.
            shift=Vec2(0.,(p.height_mm-p.width_mm)/2.).rotate(p.angle_rad)
        return p.a-shift,p.a+shift,radius
    if p.kind in ("VIA","CIRCLE"):
        return p.a,p.a,p.radius_mm
    return p.a,p.b,p.radius_mm


def _segment_rectangle_closest(
    a:Vec2,b:Vec2,r:CuPrimitive
)->tuple[Vec2,Vec2,float]:
    if _within_rect(a,r):
        return a,a,0.
    if _within_rect(b,r):
        return b,b,0.
    best:tuple[Vec2,Vec2,float]|None=None
    for c,d in _rect_edges(r):
        pair=closest_points_between_segments(a,b,c,d)
        if best is None or pair[2]<best[2]:
            best=pair
    assert best is not None
    return best


def _rectangle_rectangle_closest(
    a:CuPrimitive,b:CuPrimitive
)->tuple[Vec2,Vec2,float]:
    for x in _rect_corners(a):
        if _within_rect(x,b):
            return x,x,0.
    for y in _rect_corners(b):
        if _within_rect(y,a):
            return y,y,0.
    best:tuple[Vec2,Vec2,float]|None=None
    for u,v in _rect_edges(a):
        for x,y in _rect_edges(b):
            pair=closest_points_between_segments(u,v,x,y)
            if best is None or pair[2]<best[2]:
                best=pair
    assert best is not None
    return best


def _unit(a:Vec2,b:Vec2)->Vec2:
    d=b-a
    if d.norm()<=1e-15:
        return Vec2(1.,0.)
    return d*(1./d.norm())


def primitive_distance(
    a:CuPrimitive,b:CuPrimitive
)->tuple[float,float,Vec2,Vec2]:
    """Centre-geometry gap and signed copper gap, with closest witnesses.

    Negative copper gaps mean geometric overlap. Only a nonnegative copper
    gap is a meaningful free-space opening. The returned scalar is exact for
    these shapes (up to floating-point accuracy); no sampled minimization.
    """
    ar=a.kind=="RECT_PAD"
    br=b.kind=="RECT_PAD"
    if ar and br:
        pa,pb,d=_rectangle_rectangle_closest(a,b)
        return d,d,pa,pb
    if ar or br:
        rect,caps=(a,b) if ar else (b,a)
        start,end,radius=_axis(caps)
        paxis,prect,d=_segment_rectangle_closest(start,end,rect)
        direction=_unit(paxis,prect)
        pcaps=paxis+direction*radius
        return ((d,d-radius,prect,pcaps) if ar else
                (d,d-radius,pcaps,prect))
    pa,pb,ra=_axis(a)
    qa,qb,rb=_axis(b)
    ca,cb,d=closest_points_between_segments(pa,pb,qa,qb)
    u=_unit(ca,cb)
    return d,d-(ra+rb),ca+u*ra,cb-u*rb


def compute_max_tracks(
    gap_mm:float,track_width_mm:float,clearance_mm:float
)->tuple[int,int]:
    if (not all(math.isfinite(v) for v in (
        gap_mm,track_width_mm,clearance_mm)) or
        track_width_mm<=0. or clearance_mm<0.):
        raise ValueError("Invalid routing dimensions")
    if gap_mm<=0.:
        return 0,0
    pitch=track_width_mm+clearance_mm
    return (max(0,math.floor((gap_mm-clearance_mm+1e-9)/pitch)),
            max(0,math.floor((gap_mm+1e-9)/pitch)))


def primitive_from_kicad(item:Any,kind:str,pcbnew:Any)->CuPrimitive|None:
    """Read-only extraction; unsupported pad shapes and arcs return None."""
    xy=lambda q:Vec2(pcbnew.ToMM(q.x),pcbnew.ToMM(q.y))
    if kind=="VIA":
        p=xy(item.GetPosition())
        return CuPrimitive(kind,p,p,pcbnew.ToMM(item.GetWidth())/2.)
    if kind=="TRACK":
        return CuPrimitive(kind,xy(item.GetStart()),xy(item.GetEnd()),
                           pcbnew.ToMM(item.GetWidth())/2.)
    if kind!="PAD":
        return None
    kind_id=item.GetShape()
    size=item.GetSize()
    w,h=pcbnew.ToMM(size.x),pcbnew.ToMM(size.y)
    p=xy(item.GetPosition())
    if kind_id==pcbnew.PAD_SHAPE_CIRCLE and abs(w-h)<1e-6:
        return CuPrimitive("CIRCLE",p,p,w/2.)
    if kind_id not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_OVAL):
        return None
    orientation=item.GetOrientation()
    angle=orientation.AsRadians() if hasattr(orientation,"AsRadians") else (
        math.radians(float(orientation)/10.))
    return CuPrimitive(
        "RECT_PAD" if kind_id==pcbnew.PAD_SHAPE_RECT else "OVAL_PAD",
        p,p,0.,w,h,angle)


def display_geometry(p:CuPrimitive)->Any:
    """Polygon only for ROI/bounding or mixed-source diagnostics; not exact."""
    from shapely.geometry import LineString, Point as ShapePoint,Polygon
    if p.kind=="RECT_PAD":
        return Polygon([(q.x,q.y) for q in _rect_corners(p)])
    a,b,r=_axis(p)
    geom=(ShapePoint(a.x,a.y) if a==b else
          LineString(((a.x,a.y),(b.x,b.y))))
    return geom.buffer(r,quad_segs=64)

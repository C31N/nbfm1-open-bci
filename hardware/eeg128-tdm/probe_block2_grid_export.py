#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reproducible compact diagnostic grid, never board or fabrication output.

A read-only, bit-packed sample of three native F.Cu macro masks enables
independent bounded three-net topological feasibility experiments. It MUST
not be interpreted as KiCad DRC authorization or as a manufacturable PCB.
"""
from __future__ import annotations

import base64
import hashlib
import zlib
from typing import Any


def export_sealed_midpoint_grid(
    masks:list[Any], xs:Any, ys:Any, start:list[Any], goal:list[Any],
    u4_sha:str,target_sha:str,
) -> dict[str,Any]:
    import numpy as np
    if len(masks)!=3 or len(start)!=3 or len(goal)!=3:
        raise RuntimeError("Three distinct target F.Cu masks required")
    shape=(len(ys),len(xs))
    if shape[0]<2 or shape[1]<2:
        raise RuntimeError("Invalid native grid")
    if any(tuple(mask.shape)!=shape for mask in masks):
        raise RuntimeError("Native midpoint mask shape mismatch")
    if any(anchor is None or len(anchor)!=2
           for anchor in start+goal):
        raise RuntimeError("Native midpoint anchor missing")
    entries=[]
    for i,mask in enumerate(masks):
        forbidden=np.asarray(mask,dtype=np.bool_)
        bits=np.packbits(forbidden.ravel(order="C"),bitorder="little")
        raw=bits.tobytes()
        entries.append({
            "agent":i,
            "forbidden_bitpack_zlib_base64":base64.b64encode(
                zlib.compress(raw,level=9)).decode("ascii"),
            "bitpack_sha256":hashlib.sha256(raw).hexdigest(),
            "forbidden_grid_points":int(np.count_nonzero(forbidden)),
            "start":list(start[i]),
            "goal":list(goal[i]),
        })
    return {
        "format":"F_Cu_macro_grid_3nets_diagnostic_v1",
        "grid_rows":shape[0],
        "grid_cols":shape[1],
        "x0_mm":float(xs[0]),
        "y0_mm":float(ys[0]),
        "grid_step_x_mm":float(xs[1]-xs[0]),
        "grid_step_y_mm":float(ys[1]-ys[0]),
        "minimum_centreline_distance_mm":.300,
        "u4_escape_sha256":u4_sha,
        "target_escape_sha256":target_sha,
        "agents":entries,
        "contains_no_original_PCB_footprints_or_manufacturing_files":True,
        "requires_exact_native_copper_and_DRC_validation":True,
        "accepted":False,
        "routing_completed":False,
        "fabrication_release":False,
    }


def decode_sealed_midpoint_grid(report:dict[str,Any]) -> list[Any]:
    import numpy as np
    if report.get("format")!="F_Cu_macro_grid_3nets_diagnostic_v1":
        raise RuntimeError("Unrecognized no-release raster")
    rows=report["grid_rows"]
    cols=report["grid_cols"]
    if not (10<=rows<=1000 and 10<=cols<=1000):
        raise RuntimeError("Unreviewed raster dimensions")
    masks=[]
    for agent in report["agents"]:
        packed=zlib.decompress(base64.b64decode(
            agent["forbidden_bitpack_zlib_base64"]))
        if hashlib.sha256(packed).hexdigest()!=agent["bitpack_sha256"]:
            raise RuntimeError("Midpoint grid SHA256 integrity failure")
        bits=np.unpackbits(np.frombuffer(packed,dtype=np.uint8),
                           bitorder="little")[:rows*cols]
        masks.append(bits.reshape((rows,cols)).astype(np.bool_))
    if len(masks)!=3:
        raise RuntimeError("Exactly three midpoint masks required")
    return masks

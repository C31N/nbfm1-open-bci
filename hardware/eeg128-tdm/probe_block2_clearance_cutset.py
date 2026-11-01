#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only, UUID-precise F.Cu cutset diagnosis on the native scratch board.

All reported objects are geometric *candidate* obstructions. A nearby UUID
does not prove that its relocation is legal or necessary. Never change DRC,
netclasses, copper, zones, layers or a production checkpoint here.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

TARGETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
TRACK_WIDTH_MM = .15
DESIGN_CLEARANCE_MM = .15
HYPOTHETICAL_CLEARANCE_MM = .10
POWER_CLEARANCE_MM = .505


def spacing_scenarios(centreline_mm: float) -> dict[str, Any]:
    """Hypothetical 0.10-mm check never becomes a router/DRC override."""
    if not math.isfinite(centreline_mm) or centreline_mm < 0:
        raise ValueError("Invalid measured centreline separation")
    out = {"measured_centreline_mm": round(centreline_mm, 6),
           "track_width_mm": TRACK_WIDTH_MM}
    for key, clearance in (
        ("enforced_0_15", DESIGN_CLEARANCE_MM),
        ("hypothetical_0_10_not_authorized", HYPOTHETICAL_CLEARANCE_MM),
    ):
        required = TRACK_WIDTH_MM + clearance
        out[key] = {
            "clearance_mm": clearance,
            "minimum_centreline_mm": round(required, 6),
            "shortfall_mm": round(max(0., required - centreline_mm), 6),
            "valid_under_current_rules": key == "enforced_0_15",
        }
    return out


def verify_design_rules(board_path: Path) -> dict[str, Any]:
    """Fail-closed guard: do not describe a hypothetical as real permission."""
    source = board_path.with_suffix(".kicad_pro")
    design = board_path.with_suffix(".kicad_dru")
    project = json.loads(source.read_text(encoding="utf-8"))
    classes = {c["name"]: c for c in project["net_settings"]["classes"]}
    analog = classes["TDM_ANALOG"]
    patterns = project["net_settings"]["netclass_patterns"]
    rules = design.read_text(encoding="utf-8")
    if (abs(float(analog["clearance"]) - DESIGN_CLEARANCE_MM) > 1e-9
            or abs(float(analog["track_width"]) - TRACK_WIDTH_MM) > 1e-9
            or not any(x["pattern"] == "CH*" and
                       x["netclass"] == "TDM_ANALOG" for x in patterns)
            or '(constraint clearance (min 0.15mm))' not in rules
            or '(constraint track_width (min 0.15mm))' not in rules):
        raise RuntimeError("Pinned A2 manufacturing rules drift; no relaxation")
    return {
        "netclass": "TDM_ANALOG",
        "netclass_clearance_mm": DESIGN_CLEARANCE_MM,
        "manufacturing_rule_clearance_mm": DESIGN_CLEARANCE_MM,
        "track_width_mm": TRACK_WIDTH_MM,
        "local_0_10_rule_enabled": False,
        "fabricator_0_10_capability_confirmed": False,
    }


def inspect_cutset(
    board: Any, references: dict[str, list[tuple[float, float]]],
    *, limit: int = 14,
) -> dict[str, Any]:
    """Identify nearby *fixed* KiCad pads/tracks/vias and their actual UUIDs.

    Must be called on the source-verified scratch board AFTER the 201 permitted
    rip-up victims have been removed. Native DRC remains the authority.
    """
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points, unary_union
    from shapely.strtree import STRtree
    from route_targeted_closure import pad_copper_shape, xy

    if set(references) != set(TARGETS):
        raise ValueError("Cutset requires exactly three full topology paths")
    if not 1 <= limit <= 25:
        raise ValueError("Unbounded cutset result")
    paths = {net: LineString(references[net]) for net in TARGETS}
    if any(not line.is_valid or line.is_empty for line in paths.values()):
        raise ValueError("Invalid reference path")
    gate = verify_design_rules(Path(board.GetFileName()))
    window = unary_union(list(paths.values())).buffer(1.35)
    geoms, meta = [], []

    def add(shape: Any, item: Any, kind: str,
            footprint: str = "", pad_number: str = "") -> None:
        if shape.is_empty or not shape.intersects(window):
            return
        identifier = item.m_Uuid.AsString()
        net = item.GetNetname()
        if not identifier:
            raise RuntimeError("Native copper object without UUID")
        geoms.append(shape)
        meta.append({
            "uuid": identifier,
            "kind": kind,
            "net": net,
            "footprint": footprint,
            "pad": pad_number,
            "fixed": True,
            "protected": (net in ("VCM", "MUX_EN", "CH038_P_MUX")
                          or net.startswith("CH0") and net not in TARGETS),
            "power_clearance_mm": (POWER_CLEARANCE_MM
                                   if net in ("3V3A", "3V3D", "5V_ISO",
                                              "VREG_1V1") else None),
        })

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            # Native copper pad polygon, not approximate pad-center distance.
            bounds = pad.GetBoundingBox()
            candidate = box(pcbnew.ToMM(bounds.GetX()),
                            pcbnew.ToMM(bounds.GetY()),
                            pcbnew.ToMM(bounds.GetRight()),
                            pcbnew.ToMM(bounds.GetBottom()))
            if candidate.intersects(window):
                add(pad_copper_shape(pad, pcbnew.F_Cu), pad, "pad",
                    fp.GetReference(), pad.GetNumber())
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            geometry = Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
            kind = "via"
        elif track.GetLayer() != pcbnew.F_Cu:
            continue
        elif isinstance(track, pcbnew.PCB_ARC):
            bounds = track.GetBoundingBox()
            geometry = box(pcbnew.ToMM(bounds.GetX()),
                           pcbnew.ToMM(bounds.GetY()),
                           pcbnew.ToMM(bounds.GetRight()),
                           pcbnew.ToMM(bounds.GetBottom()))
            kind = "arc_conservative_bbox"
        else:
            geometry = LineString((
                xy(track.GetStart()), xy(track.GetEnd()))).buffer(
                    pcbnew.ToMM(track.GetWidth()) / 2)
            kind = "track"
        add(geometry, track, kind)

    tree = STRtree(geoms) if geoms else None

    def nearby(line: Any, anchor: Any | None = None) -> list[dict[str, Any]]:
        if tree is None:
            return []
        region = line.buffer(.65) if anchor is None else anchor.buffer(1.10)
        found = []
        for index in tree.query(region):
            i = int(index)
            obj = meta[i]
            if obj["net"] in TARGETS:
                # Other target copper is immutable for this cutset, but
                # cannot be called a *fixed foreign-net* obstruction.
                continue
            dist = float(line.distance(geoms[i]))
            if dist > .65:
                continue
            found.append({
                **obj,
                "centreline_to_copper_mm": round(dist, 6),
                "required_centreline_mm": round(
                    TRACK_WIDTH_MM / 2 + (
                        POWER_CLEARANCE_MM if obj["power_clearance_mm"]
                        is not None else .20 if obj["net"] in
                        ("VCM", "DRL", "CMS1", "CMS2", "ADC_REFIN") else
                        DESIGN_CLEARANCE_MM), 6),
                "clearance_deficit_mm": round(max(
                    0., TRACK_WIDTH_MM / 2 + (
                        POWER_CLEARANCE_MM if obj["power_clearance_mm"]
                        is not None else .20 if obj["net"] in
                        ("VCM", "DRL", "CMS1", "CMS2", "ADC_REFIN") else
                        DESIGN_CLEARANCE_MM) - dist), 6),
            })
        # Bounding number of UUIDs is mandatory before external Gemini input.
        return sorted(found, key=lambda x: (
            -x["clearance_deficit_mm"], x["centreline_to_copper_mm"],
            x["uuid"]))[:limit]

    pairwise = []
    for a, b in itertools.combinations(TARGETS, 2):
        pa, pb = nearest_points(paths[a], paths[b])
        gap = float(paths[a].distance(paths[b]))
        around = pa.buffer(.75).union(pb.buffer(.75))
        pairwise.append({
            "nets": [a, b],
            "minimum_centreline_mm": round(gap, 6),
            "nearest_a_mm": [round(pa.x, 6), round(pa.y, 6)],
            "nearest_b_mm": [round(pb.x, 6), round(pb.y, 6)],
            "scenario": spacing_scenarios(gap),
            "fixed_copper_uuid_candidates": nearby(paths[a], around),
            "other_net_fixed_copper_uuid_candidates": nearby(paths[b], around),
            "candidate_uuid_is_not_proof_of_causality": True,
        })
    individual = {
        name: {"nearby_fixed_copper": nearby(path)}
        for name, path in paths.items()
    }
    return {
        "status": "read_only_native_cutset_candidates",
        "source": "KiCad 8 native scratch copper UUID + Shapely exact proximity",
        "native_DRC_pass": False,
        "no_via_added": True,
        "no_in1_used": True,
        "no_design_rule_changed": True,
        "rules": gate,
        "pairwise": pairwise,
        "per_target": individual,
        "fixed_copper_items_considered": len(meta),
        "cutset_completeness_proven": False,
    }

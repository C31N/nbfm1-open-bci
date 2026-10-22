#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only KiCad8 endpoint-to-power exact copper clearance check.

Original CH027_N_MUX F.Cu track endpoints are mandatory immutable
anchors for cooperative routing. A clearance of 0.505 mm measured
edge-to-edge to power F.Cu requires at least 0.580 mm centerline-to-power
when a new trace is 0.150 mm wide. This diagnostic does not route,
alter pads, vias, copper, or power zones, and cannot promote checkpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_fcu_blocker_uuids import (
    ARCHIVE_SHA256, BOARD_SHA256, MEMBERS,
)

CH027_UUID = "81777460-c80a-48c9-8608-bae0dd42ee2f"
POWER_PAD_UUID = "b6c0c126-07d4-49b7-9025-31d8fc547738"
EXPECTED_START = (37.6246, 47.5232)
EXPECTED_END = (33.1357, 47.5232)
CLEARANCE_MM = .505
TRACE_HALF_WIDTH_MM = .075
FLAGS = {
    "accepted": False,
    "fabrication_release": False,
    "routing_completed": False,
    "manufacturing_files": False,
    "independent_replay_verified": False,
    "source_pcb_modified": False,
}


def endpoint_clearance(raw_center_distance_mm: float) -> dict[str, Any]:
    if raw_center_distance_mm < 0:
        raise ValueError("Negative geometric distance")
    required_center = CLEARANCE_MM + TRACE_HALF_WIDTH_MM
    gap = raw_center_distance_mm - TRACE_HALF_WIDTH_MM
    return {
        "center_to_power_surface_mm": round(raw_center_distance_mm, 9),
        "new_trace_edge_to_power_surface_mm": round(gap, 9),
        "required_edge_to_power_mm": CLEARANCE_MM,
        "required_center_to_power_surface_mm": required_center,
        "margin_mm": round(raw_center_distance_mm - required_center, 9),
        "strict_power_clearance_possible_at_this_point": (
            raw_center_distance_mm + 1e-9 >= required_center
        ),
        "native_DRC_qualified": False,
    }



def alternate_native_anchor_inventory(board: Any, target: tuple[float, float],
                                      power_objects: list[dict[str, Any]]
                                      ) -> dict[str, Any]:
    """Sample original same-net copper touching the old immutable endpoint.

    Geometric contact, not native netlist/DRC proof. This finds candidates
    that do NOT need pads/vias relocated and clear all power shapes by 0.505.
    """
    import math
    import pcbnew
    from shapely.geometry import LineString, Point
    from route_targeted_closure import pad_copper_shape, routing_domain, xy

    origin = Point(target)
    domain = routing_domain(board, TRACE_HALF_WIDTH_MM, .25)
    touching = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if (pad.GetNetname() != "CH027_N_MUX"
                    or not pad.IsOnLayer(pcbnew.F_Cu)):
                continue
            geom = pad_copper_shape(pad, pcbnew.F_Cu)
            if geom.distance(origin) <= .000002:
                touching.append((pad.m_Uuid.AsString(), "pad",
                                 fp.GetReference()+"."+pad.GetNumber(),
                                 geom, None))
    for track in board.GetTracks():
        if (track.m_Uuid.AsString() == CH027_UUID
                or track.GetNetname() != "CH027_N_MUX"
                or track.GetLayer() != pcbnew.F_Cu
                or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
            continue
        axis = LineString([xy(track.GetStart()),xy(track.GetEnd())])
        geometry = axis.buffer(pcbnew.ToMM(track.GetWidth())/2)
        if geometry.distance(origin) <= .000002:
            touching.append((track.m_Uuid.AsString(), "track",
                             None, geometry, axis))
    candidates = []
    for uid, kind, ref, copper, axis in touching:
        samples = [origin]
        if axis is None:
            perimeter = copper.boundary
            n = min(300, max(8, int(math.ceil(perimeter.length/.08))))
            samples.extend(perimeter.interpolate(i/n, normalized=True)
                           for i in range(n))
            samples.append(copper.representative_point())
        else:
            n = min(300, max(8, int(math.ceil(axis.length/.08))))
            samples.extend(axis.interpolate(i/n, normalized=True)
                           for i in range(n+1))
        for point in samples:
            if (point.distance(origin) > 4.0
                    or not copper.buffer(.000002).covers(point)
                    or not domain.covers(point)):
                continue
            distance, nearest = min(
                ((point.distance(obj["copper"]), obj)
                 for obj in power_objects),
                key=lambda row: row[0])
            check = endpoint_clearance(distance)
            if not check["strict_power_clearance_possible_at_this_point"]:
                continue
            candidates.append({
                "on_original_connected_uuid": uid,
                "kind": kind, "ref": ref,
                "coordinate_mm": [round(point.x, 6),round(point.y,6)],
                "distance_to_original_endpoint_mm": round(
                    point.distance(origin),6),
                "nearest_power_uuid": nearest["uuid"],
                "nearest_power_net": nearest["net"],
                "min_power_gap_mm": check[
                    "new_trace_edge_to_power_surface_mm"],
                "strict_power_margin_mm": check["margin_mm"],
                "route_restituted_native_DRC": False,
            })
    candidates.sort(key=lambda x: (
        x["distance_to_original_endpoint_mm"],
        -x["strict_power_margin_mm"],x["on_original_connected_uuid"]))
    return {
        "same_net_contact_objects": [
            {"uuid":x[0],"kind":x[1],"ref":x[2]} for x in touching],
        "strict_505_candidate_count": len(candidates),
        "closest_safe_candidates": candidates[:20],
        "complete_native_connectivity_proven": False,
        "restoration_proven": False,
    }


def audit(board_path: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from route_targeted_closure import POWER, pad_copper_shape, xy

    board = pcbnew.LoadBoard(str(board_path))
    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    original = tracks.get(CH027_UUID)
    if (original is None or original.GetNetname() != "CH027_N_MUX"
            or original.GetLayer() != pcbnew.F_Cu
            or pcbnew.ToMM(original.GetWidth()) != .15):
        raise ValueError("CH027 native original identity mismatch")
    points = (xy(original.GetStart()), xy(original.GetEnd()))
    if (any(abs(a-b) > .00001 for x,y in zip(points,
             (EXPECTED_START,EXPECTED_END)) for a,b in zip(x,y))):
        raise ValueError("Original CH027 F.Cu endpoints changed")

    objects = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() not in POWER or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            objects.append({
                "uuid": pad.m_Uuid.AsString(), "net": pad.GetNetname(),
                "kind": "pad", "ref": fp.GetReference()+"."+pad.GetNumber(),
                "copper": pad_copper_shape(pad,pcbnew.F_Cu)})
    for t in board.GetTracks():
        if t.GetNetname() not in POWER:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            geometry = Point(xy(t.GetPosition())).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
            kind = "via"
        elif t.GetLayer() != pcbnew.F_Cu:
            continue
        elif isinstance(t, pcbnew.PCB_ARC):
            bounds = t.GetBoundingBox()
            geometry = box(pcbnew.ToMM(bounds.GetX()),
                           pcbnew.ToMM(bounds.GetY()),
                           pcbnew.ToMM(bounds.GetRight()),
                           pcbnew.ToMM(bounds.GetBottom()))
            kind = "arc_bounds_conservative"
        else:
            geometry = LineString((xy(t.GetStart()),xy(t.GetEnd()))).buffer(
                pcbnew.ToMM(t.GetWidth())/2)
            kind = "track"
        objects.append({
            "uuid": t.m_Uuid.AsString(), "net": t.GetNetname(),
            "kind": kind, "ref": None, "copper": geometry})

    pad = next((o for o in objects if o["uuid"] == POWER_PAD_UUID), None)
    if pad is None or pad["net"] != "3V3A" or pad["kind"] != "pad":
        raise ValueError("Pinned 3V3A target-adjacent pad missing")

    outputs = {}
    for label, coords in zip(("source","target"),points):
        point = Point(coords)
        close = sorted([
            {
                "uuid": item["uuid"], "net": item["net"],
                "kind": item["kind"], "ref": item["ref"],
                **endpoint_clearance(point.distance(item["copper"])),
            }
            for item in objects
        ], key=lambda i:(i["center_to_power_surface_mm"],i["uuid"]))
        outputs[label] = {
            "coordinate_mm": list(coords),
            "closest_power": close[:12],
            "power_objects_within_1mm": sum(
                i["center_to_power_surface_mm"] < 1 for i in close),
            "all_power_objects_clear_at_endpoint": all(
                i["strict_power_clearance_possible_at_this_point"]
                for i in close),
            "pinned_3v3a_pad": next(
                i for i in close if i["uuid"] == POWER_PAD_UUID),
        }
    alternative = alternate_native_anchor_inventory(
        board, EXPECTED_END, objects)
    return {
        **FLAGS, "status": "read_only_endpoint_power_clearance_probe",
        "alternative_target_anchor_inventory": alternative,
        "native_DRC_run": False, "baseline_airwires": 139,
        "target_airwires": 136, "native_kicad_version": pcbnew.Version(),
        "CH027_track_uuid": CH027_UUID,
        "3V3A_pad_uuid": POWER_PAD_UUID,
        "power_network_objects_checked": len(objects),
        "endpoints": outputs,
        "fixed_endpoints_meet_required_505_power_clearance": all(
            o["all_power_objects_clear_at_endpoint"]
            for o in outputs.values()),
        "L3_loss_mm2": None, "L3_gain_mm2": None,
        "manufacturing_export_invoked": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Wrong pinned immutable 139 checkpoint archive")
    with tempfile.TemporaryDirectory(prefix="ch027-power-endpoint-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(args.archive) as archive:
            if sorted(archive.namelist()) != sorted(MEMBERS):
                raise ValueError("Unexpected source archive entries")
            for name in MEMBERS:
                (root/name).write_bytes(archive.read(name))
        pcb = root/MEMBERS[0]
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != BOARD_SHA256:
            raise RuntimeError("Pinned KiCad board hash mismatch")
        result = audit(pcb)
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != BOARD_SHA256:
            raise RuntimeError("Read-only audit modified native PCB")
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("Source 139 ZIP modified")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({
        "status": result["status"],
        "all_power_clear": result[
            "fixed_endpoints_meet_required_505_power_clearance"],
        "source_pad_gap": result["endpoints"]["source"][
            "pinned_3v3a_pad"]["new_trace_edge_to_power_surface_mm"],
        "target_pad_gap": result["endpoints"]["target"][
            "pinned_3v3a_pad"]["new_trace_edge_to_power_surface_mm"],
        "safe_alternative_anchors": result[
            "alternative_target_anchor_inventory"][
                "strict_505_candidate_count"],
        "accepted": False,
    }),flush=True)


if __name__ == "__main__":
    main()

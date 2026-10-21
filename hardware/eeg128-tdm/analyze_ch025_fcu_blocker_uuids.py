#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""UUID-precise read-only F.Cu cut inventory on the immutable 139 checkpoint.

All four existing CH025 via pairs are analysed. Candidate 0.15-0.25 mm
interior doglegs are geometry models only: no tracks, pads, zones, or
footprints are mutated or persisted. Never infer native connectivity,
power-plane parity, or release qualification from this inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_l3_native_refill import TARGET_UUID, ZONE_UUID
from analyze_ch025_l3_precision_mask import PROBE_28_CH022_LAYERS

ARCHIVE_SHA256 = "f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b"
BOARD_SHA256 = "f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea"
ALLOWED_FILES = ("eeg128-tdm.kicad_pcb", "eeg128-tdm.kicad_pro",
                 "eeg128-tdm.kicad_dru")
PROTECTED_PREFIXES = (
    "VCM", "CH017_N", "CH019_P", "CH024_P", "CH026_P",
    "3V3", "5V", "VREG", "AGND", "GND", "ISO_GND", "DRL",
)
MICRO_MM = (0.150, 0.200, 0.250)
FLAGS = dict(accepted=False, routing_completed=False,
             fabrication_release=False, manufacturing_files=False,
             copper_changed=False, native_qualification=False)


def protected_net(name: str) -> bool:
    """A conservative net-prefix blacklist; uncertain names are not moved."""
    return name.startswith(PROTECTED_PREFIXES)


def micro_dogleg(start: tuple[float, float], end: tuple[float, float],
                 shift_mm: float) -> list[tuple[float, float]]:
    """Interior offset with fixed solder/via endpoints; no isolated stubs."""
    import math
    length = math.dist(start, end)
    if length < 1.0 or abs(shift_mm) not in MICRO_MM:
        raise ValueError("Non-qualifying segment/offset")
    normal = (-(end[1] - start[1]) / length,
              (end[0] - start[0]) / length)
    def sample(t: float, offset: float) -> tuple[float, float]:
        return (start[0] + t * (end[0] - start[0]) + normal[0] * offset,
                start[1] + t * (end[1] - start[1]) + normal[1] * offset)
    return [start, sample(.25, shift_mm),
            sample(.75, shift_mm), end]


def footprint_and_track_inventory(board: Any) -> dict[str, Any]:
    from route_targeted_closure import xy
    tracks = {
        t.m_Uuid.AsString(): (
            t.GetNetCode(), t.GetNetname(), t.GetLayer(),
            xy(t.GetStart()), xy(t.GetEnd()), t.GetWidth(),
            type(t).__name__)
        for t in board.GetTracks()
    }
    footprints = {
        fp.GetReference(): (
            fp.m_Uuid.AsString(), xy(fp.GetPosition()),
            tuple(sorted((p.m_Uuid.AsString(), p.GetNetname(),
                          xy(p.GetPosition())) for p in fp.Pads())))
        for fp in board.GetFootprints()
    }
    zones = {z.m_Uuid.AsString(): (
        z.GetNetname(), tuple(sorted(z.GetLayerSet().FmtBin().split())))
        for z in board.Zones()}
    return dict(tracks=tracks, footprints=footprints, zones=zones)


def native_shapes(board: Any, window: Any) -> list[dict[str, Any]]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from route_targeted_closure import pad_copper_shape, xy
    result: list[dict[str, Any]] = []
    for t in board.GetTracks():
        if t.GetNetname() == "CH025_N_MUX":
            continue
        is_via = isinstance(t, pcbnew.PCB_VIA)
        if not is_via and t.GetLayer() != pcbnew.F_Cu:
            continue
        if is_via:
            shape = Point(xy(t.GetPosition())).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
        elif isinstance(t, pcbnew.PCB_ARC):
            bounds = t.GetBoundingBox()
            shape = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                        pcbnew.ToMM(bounds.GetRight()),
                        pcbnew.ToMM(bounds.GetBottom()))
        else:
            shape = LineString([xy(t.GetStart()), xy(t.GetEnd())]).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
        if not shape.intersects(window):
            continue
        immutable = is_via or isinstance(t, pcbnew.PCB_ARC) or protected_net(t.GetNetname())
        result.append(dict(uuid=t.m_Uuid.AsString(), name=t.GetNetname(),
                           kind="via" if is_via else "arc" if isinstance(t, pcbnew.PCB_ARC)
                           else "track", layer="F.Cu" if not is_via else "THROUGH",
                           immutable=immutable, geometry=shape, native_object=t))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == "CH025_N_MUX" or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            shape = pad_copper_shape(pad, pcbnew.F_Cu)
            if shape.intersects(window):
                result.append(dict(uuid=pad.m_Uuid.AsString(),
                                   name=pad.GetNetname(), kind="pad",
                                   reference=fp.GetReference() + "." + pad.GetNumber(),
                                   layer="F.Cu", immutable=True,
                                   geometry=shape, native_object=pad))
    return result


def geometry_candidate(board: Any, track: Any, move: float,
                       domain: Any, reserved_ch022: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from route_targeted_closure import obstacles, xy
    from probe_ch025_fcu_l3_exact import power_fcu_obstacles

    start, end = xy(track.GetStart()), xy(track.GetEnd())
    proposed = micro_dogleg(start, end, move)
    line = LineString(proposed)
    window = line.buffer(2.0)
    by_layer, _ = obstacles(board, track.GetNetCode(),
                            pcbnew.ToMM(track.GetWidth()), .15,
                            window, .60, (pcbnew.F_Cu, pcbnew.B_Cu))
    forbidden = unary_union([by_layer[0], power_fcu_obstacles(board),
                             reserved_ch022])
    passed = domain.covers(line) and not line.intersects(forbidden)
    return dict(move_mm=move, dogleg_xy_mm=[
        [round(x, 6), round(y, 6)] for x, y in proposed],
        geometric_candidate=passed,
        native_DRC_required=True, neighbor_restitution_required=True)


def scan(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points, unary_union
    from escape_mesh_505 import polygons
    from probe_ch025_fcu_l3_exact import power_fcu_obstacles
    from route_targeted_closure import obstacles, routing_domain, xy
    from analyze_ch025_existing_via_anchor import connected_existing_vias
    from analyze_ch025_l3_native_refill import filled

    before = footprint_and_track_inventory(board)
    zones = [z for z in board.Zones()
             if z.m_Uuid.AsString() == ZONE_UUID
             and z.GetNetname() == "3V3A"
             and z.IsOnLayer(pcbnew.In2_Cu)]
    cuts = [t for t in board.GetTracks()
            if t.m_Uuid.AsString() == TARGET_UUID]
    if len(zones) != 1 or len(cuts) != 1:
        raise ValueError("Exact reviewed 3V3A zone or CH025 track unavailable")
    cut = cuts[0]
    if cut.GetNetname() != "CH025_N_MUX" or cut.GetLayer() != pcbnew.In2_Cu:
        raise ValueError("CH025 cut identity not verified")
    if sorted((xy(cut.GetStart()), xy(cut.GetEnd()))) != sorted(
        ((44.505, 25.129999), (44.505, 39.129999))):
        raise ValueError("CH025 cut endpoints changed")
    power = filled(zones[0])
    netcode = board.FindNet("CH025_N_MUX").GetNetCode()
    source = connected_existing_vias(board, xy(cut.GetStart()), netcode, power, 4)
    target = connected_existing_vias(board, xy(cut.GetEnd()), netcode, power, 4)
    if not source["via_candidates"] or not target["via_candidates"]:
        raise ValueError("Existing electrically connected via pairs missing")
    domain = routing_domain(board, .075, .25)
    via_centres = [Point(a[1:]).buffer(.505) for a, b in
                   zip(PROBE_28_CH022_LAYERS, PROBE_28_CH022_LAYERS[1:])
                   if a[0] != b[0]]
    reserved_ch022 = unary_union(via_centres)
    rows: list[dict[str, Any]] = []
    power_fcu = power_fcu_obstacles(board)
    for src in source["via_candidates"]:
        for dst in target["via_candidates"]:
            a, b = tuple(src["coordinate_mm"]), tuple(dst["coordinate_mm"])
            region = box(min(a[0], b[0]) - 10, min(a[1], b[1]) - 10,
                         max(a[0], b[0]) + 10, max(a[1], b[1]) + 10).intersection(domain)
            by_layer, _ = obstacles(board, netcode, .15, .15,
                                    region, .60, (pcbnew.F_Cu, pcbnew.B_Cu))
            free = region.difference(unary_union(
                [by_layer[0], power_fcu])).buffer(-.000005)
            parts = polygons(free)
            s_part = next((p for p in parts if p.covers(Point(a))), None)
            t_part = next((p for p in parts if p.covers(Point(b))), None)
            record: dict[str, Any] = dict(
                source_uuid=src["uuid"], target_uuid=dst["uuid"],
                source_mm=list(a), target_mm=list(b),
                source_FCu_component_exists=s_part is not None,
                target_FCu_component_exists=t_part is not None,
                same_FCu_component=False, nearest_gap_mm=None,
                obstructing_objects=[], micro_proposals=[])
            if s_part is None or t_part is None:
                record["status"] = "FCu_anchor_unavailable_or_too_conservative"
                rows.append(record)
                continue
            if s_part.equals(t_part):
                record["same_FCu_component"] = True
                record["status"] = "FCu_component_connected_mesh_unresolved"
                rows.append(record)
                continue
            p, q = nearest_points(s_part, t_part)
            gap = LineString([p, q])
            record["nearest_gap_mm"] = round(gap.length, 6)
            window = gap.buffer(1.25)
            local = native_shapes(board, window)
            local.sort(key=lambda x: (x["geometry"].distance(gap),
                                      x["kind"], x["uuid"]))
            seen_uuids: set[str] = set()
            for item in local:
                if item["uuid"] in seen_uuids or len(seen_uuids) >= 35:
                    continue
                seen_uuids.add(item["uuid"])
                distance = float(item["geometry"].distance(gap))
                record["obstructing_objects"].append(
                    dict(uuid=item["uuid"], net=item["name"],
                         kind=item["kind"], layer=item["layer"],
                         distance_to_cut_mm=round(distance, 6),
                         immutable=item["immutable"],
                         reference=item.get("reference")))
                if item["immutable"] or item["kind"] != "track":
                    continue
                track = item["native_object"]
                width = pcbnew.ToMM(track.GetWidth())
                if width > .250 or LineString(
                    [xy(track.GetStart()), xy(track.GetEnd())]).length < 1.0:
                    continue
                for m in MICRO_MM:
                    for sign in (-1, 1):
                        try:
                            candidate = geometry_candidate(
                                board, track, sign * m, domain, reserved_ch022)
                        except ValueError:
                            continue
                        if candidate["geometric_candidate"]:
                            record["micro_proposals"].append(
                                dict(uuid=item["uuid"], net=item["name"],
                                     width_mm=width, **candidate))
            record["status"] = ("local_uuid_gap_inventoried_model_only"
                                if record["obstructing_objects"]
                                else "gap_unexplained_by_local_uuid_window")
            rows.append(record)
    if footprint_and_track_inventory(board) != before:
        raise RuntimeError("Read-only scan modified protected board")
    return {**FLAGS, "status": "FCu_UUID_inventory_model_only",
            "baseline_airwires": 139, "via_pairs": len(rows),
            "L3_zone_uuid": ZONE_UUID,
            "power_clearance_mm": .505, "edge_clearance_mm": .25,
            "F_Cu_only": True, "In1_Cu_used": False,
            "CH022_multihop_protected_vias": len(via_centres),
            "pairs": rows,
            "micro_proposal_count": sum(len(x["micro_proposals"]) for x in rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    archive_path = args.archive.resolve()
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Wrong immutable 139 checkpoint ZIP SHA-256")
    with tempfile.TemporaryDirectory(prefix="ch025-fcu-uuid-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(archive_path) as zipf:
            if sorted(zipf.namelist()) != sorted(ALLOWED_FILES):
                raise SystemExit("Unexpected checkpoint archive members")
            for name in ALLOWED_FILES:
                (root / name).write_bytes(zipf.read(name))
        board_path = root / ALLOWED_FILES[0]
        if hashlib.sha256(board_path.read_bytes()).hexdigest() != BOARD_SHA256:
            raise SystemExit("Wrong immutable 139 PCB SHA-256")
        import pcbnew
        if not pcbnew.Version().startswith("8.0.9"):
            raise SystemExit("Native KiCad 8.0.9 required")
        board = pcbnew.LoadBoard(str(board_path))
        original_sha = hashlib.sha256(board_path.read_bytes()).hexdigest()
        report = scan(board)
        if hashlib.sha256(board_path.read_bytes()).hexdigest() != original_sha:
            raise RuntimeError("Archive-derived PCB was written during survey")
        report["source_pcb_sha256"] = original_sha
        report["source_archive_sha256"] = ARCHIVE_SHA256
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "pairs": report["via_pairs"],
            "micro_proposal_count": report["micro_proposal_count"],
            **FLAGS,
        }))


if __name__ == "__main__":
    main()

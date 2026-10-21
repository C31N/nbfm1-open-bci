#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only F.Cu obstacle UUID inventory for CH025 on the locked 139 PCB.

Bounds the analysis to 4 reviewed via pairs, seven candidate centerlines
per pair, and polygon-indexed foreign-net copper. Blocker intersections
are conservative direct-corridor evidence, not minimum cut sets or an
electrically restored route. No board is modified or saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ARCHIVE_SHA256 = "f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b"
BOARD_SHA256 = "f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea"
MEMBERS = ("eeg128-tdm.kicad_pcb", "eeg128-tdm.kicad_pro", "eeg128-tdm.kicad_dru")
CH025 = "CH025_N_MUX"
CH022 = "CH022_N_ELECTRODE"
CUT = "748cc9c4-2d8f-4ec6-9714-133d79d4c7cb"
ZONE = "06a28b70-5141-41e4-bdb1-c8324bc06fcb"
START_VIAS = {
    "6040bdea-9da3-44af-9e52-227de6f931c8": (49.455, 16.479999),
    "c9831d96-6bbb-4308-9c5d-e72b6ccfbdac": (49.450, 14.900),
}
END_VIAS = {
    "c51e9b29-e51a-45cf-8047-3dd4484ec17e": (36.105, 48.850),
    "dbdd22b2-65d2-47f7-aaf7-bae5ec14caa8": (43.405, 52.179999),
}
PROTECTED_PREFIXES = ("VCM", "CH017_N", "CH019_P", "CH024_P", "CH026_P",
                      "3V3", "5V", "VREG", "AGND", "GND", "ISO_GND", "DRL")
MICRO_MM = (0.150, 0.200, 0.250)
FLAGS = dict(accepted=False, routing_completed=False,
             fabrication_release=False, manufacturing_files=False,
             copper_changed=False, native_qualification=False)


def protected_net(name: str) -> bool:
    return name.startswith(PROTECTED_PREFIXES)


def micro_dogleg(start: tuple[float, float], end: tuple[float, float],
                 shift_mm: float) -> list[tuple[float, float]]:
    length = math.dist(start, end)
    if length < 1.0 or abs(shift_mm) not in MICRO_MM:
        raise ValueError("Micro-offset outside reviewed bounds")
    nx = -(end[1] - start[1]) / length
    ny = (end[0] - start[0]) / length
    return [start,
            (start[0] + (end[0] - start[0]) * .25 + nx * shift_mm,
             start[1] + (end[1] - start[1]) * .25 + ny * shift_mm),
            (start[0] + (end[0] - start[0]) * .75 + nx * shift_mm,
             start[1] + (end[1] - start[1]) * .75 + ny * shift_mm),
            end]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copper_shapes(board: Any) -> tuple[list[Any], list[dict[str, Any]]]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from route_targeted_closure import pad_copper_shape, xy

    geometries: list[Any] = []
    entries: list[dict[str, Any]] = []

    def add(uuid: str, net: str, kind: str, shape: Any,
            movable: bool, reference: str | None = None,
            width_mm: float | None = None) -> None:
        clearance = .505 if protected_net(net) and net.startswith(
            ("3V3", "5V", "VREG", "AGND", "GND", "ISO_GND")
        ) else .150
        geometries.append(shape.buffer(clearance + .075))
        entries.append(dict(uuid=uuid, net=net, kind=kind,
                            protected=not movable, width_mm=width_mm,
                            reference=reference))

    for track in board.GetTracks():
        net = track.GetNetname()
        if net == CH025:
            continue
        via = isinstance(track, pcbnew.PCB_VIA)
        if not via and track.GetLayer() != pcbnew.F_Cu:
            continue
        is_arc = isinstance(track, pcbnew.PCB_ARC)
        if via:
            shape = Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
        elif is_arc:
            bb = track.GetBoundingBox()
            shape = box(pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                        pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
        else:
            shape = LineString((xy(track.GetStart()), xy(track.GetEnd()))).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
        width = pcbnew.ToMM(track.GetWidth())
        movable = (not via and not is_arc and not protected_net(net)
                   and width <= .250
                   and math.dist(xy(track.GetStart()), xy(track.GetEnd())) >= 1)
        add(track.m_Uuid.AsString(), net,
            "via" if via else "arc" if is_arc else "track",
            shape, movable, width_mm=width)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not pad.IsOnLayer(pcbnew.F_Cu) or pad.GetNetname() == CH025:
                continue
            shape = pad_copper_shape(pad, pcbnew.F_Cu)
            add(pad.m_Uuid.AsString(), pad.GetNetname(), "pad",
                shape, False, reference=fp.GetReference() + "." + pad.GetNumber())
    return geometries, entries


def scan(board: Any) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    from route_targeted_closure import routing_domain, xy

    vias = {track.m_Uuid.AsString(): track for track in board.GetTracks()
            if isinstance(track, pcbnew.PCB_VIA)}
    for uid, expected in {**START_VIAS, **END_VIAS}.items():
        track = vias.get(uid)
        if track is None or track.GetNetname() != CH025:
            raise ValueError("Pinned CH025 via UUID missing or changed: " + uid)
        if math.dist(xy(track.GetPosition()), expected) > .001:
            raise ValueError("Pinned CH025 via position changed: " + uid)
    cuts = [track for track in board.GetTracks()
            if track.m_Uuid.AsString() == CUT]
    zones = [z for z in board.Zones() if z.m_Uuid.AsString() == ZONE
             and z.GetNetname() == "3V3A"
             and z.IsOnLayer(pcbnew.In2_Cu)]
    if len(cuts) != 1 or cuts[0].GetNetname() != CH025 or len(zones) != 1:
        raise ValueError("Locked CH025 cut or 3V3A zone changed")
    shapes, entries = copper_shapes(board)
    index = STRtree(shapes)
    domain = routing_domain(board, .075, .25)
    pairs: list[dict[str, Any]] = []
    for start_uuid, a in START_VIAS.items():
        for end_uuid, b in END_VIAS.items():
            options: list[dict[str, Any]] = []
            offsets = (0.0, -.150, .150, -.200, .200, -.250, .250)
            for offset in offsets:
                points = [a, b] if offset == 0 else micro_dogleg(a, b, offset)
                line = LineString(points)
                hit_ids = [int(i) for i in index.query(line, predicate="intersects")]
                blockers = [entries[i] for i in hit_ids]
                blockers.sort(key=lambda row: (row["protected"], row["kind"],
                                              row["uuid"]), reverse=True)
                options.append(dict(
                    offset_mm=offset,
                    edge_clearance_satisfied=bool(domain.covers(line)),
                    blocking_uuid_count=len(blockers),
                    protected_uuid_count=sum(row["protected"] for row in blockers),
                    blocker_uuids=[row["uuid"] for row in blockers[:100]],
                    blockers=blockers[:100],
                    truncated=len(blockers) > 100))
            options.sort(key=lambda opt: (
                not opt["edge_clearance_satisfied"],
                opt["protected_uuid_count"],
                opt["blocking_uuid_count"],
                abs(opt["offset_mm"])))
            minimum = options[0]
            selectable = [row for row in minimum["blockers"]
                          if not row["protected"] and row["kind"] == "track"]
            pairs.append(dict(
                source_uuid=start_uuid, target_uuid=end_uuid,
                source_mm=list(a), target_mm=list(b),
                ranked_direct_corridors=options,
                best_direct_corridor_offset_mm=minimum["offset_mm"],
                movable_signal_track_uuids=[row["uuid"] for row in selectable],
                allowed_neighbor_micro_offsets_mm=list(MICRO_MM),
                native_route_proved=False,
                all_neighbors_restituted=False))
    return {**FLAGS, "status": "bounded_native_geometry_UUID_inventory_only",
            "baseline_airwires": 139,
            "source": "reviewed SHA-256 139-airwire PCB",
            "F_Cu_only": True, "In1_Cu_used": False,
            "power_clearance_mm": .505, "edge_clearance_mm": .25,
            "CH022_multihop_preserved_unmodified": True,
            "L3_loss_mm2": None, "L3_gain_mm2": None,
            "via_pairs": len(pairs),
            "sampled_direct_corridors": sum(len(row["ranked_direct_corridors"])
                                            for row in pairs),
            "qualification_note": "Direct-corridor polygon intersections are"
            " not topological minimum cut sets. A moved neighbor must be"
            " separately DRC-qualified and fully reconnected.",
            "pairs": pairs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    if sha(archive) != ARCHIVE_SHA256:
        raise SystemExit("Wrong 139 checkpoint archive SHA-256")
    with tempfile.TemporaryDirectory(prefix="ch025-fcu-uuid-") as work:
        root = Path(work)
        with zipfile.ZipFile(archive) as source:
            if sorted(source.namelist()) != sorted(MEMBERS):
                raise SystemExit("Wrong checkpoint archive members")
            for name in MEMBERS:
                (root / name).write_bytes(source.read(name))
        pcb = root / MEMBERS[0]
        if sha(pcb) != BOARD_SHA256:
            raise SystemExit("Wrong 139 checkpoint PCB SHA-256")
        import pcbnew
        if not pcbnew.Version().startswith("8.0.9"):
            raise SystemExit("Native KiCad 8.0.9 required")
        board = pcbnew.LoadBoard(str(pcb))
        result = scan(board)
        if sha(pcb) != BOARD_SHA256 or sha(archive) != ARCHIVE_SHA256:
            raise RuntimeError("Read-only input changed")
        result["source_pcb_sha256"] = BOARD_SHA256
        result["source_archive_sha256"] = ARCHIVE_SHA256
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({
            "status": result["status"], "via_pairs": result["via_pairs"],
            "corridors": result["sampled_direct_corridors"], **FLAGS,
        }))


if __name__ == "__main__":
    main()

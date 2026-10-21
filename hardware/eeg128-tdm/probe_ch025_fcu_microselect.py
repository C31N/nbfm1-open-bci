#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed native CH025 F.Cu micro-selection on the SHA-pinned 139 archive.

No board/footprint/pad/via/zone source changes. Check all 9 reviewed neighbor
UUIDs at +/-0.150/0.200/0.250 mm using end-fixed doglegs and physical
obstacles. Only individually legal corridor-clearing candidates are eligible
for scratch-only KiCad 8.0.9 DRC and neighbor net-regression checks. Reports
are diagnostic only; joint CH022/L3/136 acceptance is out of scope.
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

from analyze_ch025_fcu_blocker_uuids import (
    ARCHIVE_SHA256, BOARD_SHA256, MEMBERS, MICRO_MM, FLAGS,
    CH025, copper_shapes, micro_dogleg, protected_net,
)

EXPECTED_START = "c9831d96-6bbb-4308-9c5d-e72b6ccfbdac"
EXPECTED_END = "c51e9b29-e51a-45cf-8047-3dd4484ec17e"
EXPECTED_OFFSET = -.150
NO_FAB = ("*.gbr", "*.drl", "*.pos", "*.gbrjob")


def choose(inventory: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Minimize movable blockers, then immutable blockers, then all contacts."""
    if (inventory.get("source_archive_sha256") != ARCHIVE_SHA256
            or inventory.get("source_pcb_sha256") != BOARD_SHA256
            or inventory.get("via_pairs") != 4
            or inventory.get("sampled_direct_corridors") != 28):
        raise ValueError("Unverified native UUID inventory")
    rows = [(p, r) for p in inventory["pairs"]
            for r in p["ranked_direct_corridors"]
            if r["edge_clearance_satisfied"]]
    if len(rows) != 28:
        raise ValueError("Noncanonical via/route shortlist")
    p, r = min(rows, key=lambda row: (
        row[1]["blocking_uuid_count"] - row[1]["protected_uuid_count"],
        row[1]["protected_uuid_count"], row[1]["blocking_uuid_count"],
        abs(row[1]["offset_mm"])))
    if (p["source_uuid"], p["target_uuid"], r["offset_mm"]) != (
            EXPECTED_START, EXPECTED_END, EXPECTED_OFFSET):
        raise ValueError("Best reviewed corridor identity changed")
    if (r["blocking_uuid_count"], r["protected_uuid_count"]) != (28, 19):
        raise ValueError("Verified 28/19 corridor evidence changed")
    if len(r["blockers"]) != r["blocking_uuid_count"]:
        raise ValueError("Truncated blocker report")
    return p, r


def scan(board: Any, inventory: dict[str, Any], max_native: int,
         workspace: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, Point, box
    from shapely.strtree import STRtree
    from route_targeted_closure import metrics, native, routing_domain, xy, make_track
    from native_connectivity import regressed_nets
    from analyze_ch025_l3_precision_mask import PROBE_28_CH022_LAYERS

    pair, option = choose(inventory)
    track_by_uuid = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    candidates = [b for b in option["blockers"]
                  if b["kind"] == "track" and not b["protected"]]
    if len(candidates) != 9 or len({b["uuid"] for b in candidates}) != 9:
        raise ValueError("Reviewed nine-track candidate identity changed")
    for item in candidates:
        track = track_by_uuid.get(item["uuid"])
        if (track is None or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
                or track.GetLayer() != pcbnew.F_Cu
                or track.GetNetname() != item["net"]
                or protected_net(track.GetNetname())
                or pcbnew.ToMM(track.GetWidth()) != .15):
            raise ValueError("Foreign candidate changed: " + item["uuid"])

    corridor_points = micro_dogleg(
        tuple(pair["source_mm"]), tuple(pair["target_mm"]),
        EXPECTED_OFFSET)
    corridor = LineString(corridor_points)
    edge = routing_domain(board, .075, .25)
    geometries, items = copper_shapes(board)
    tree = STRtree(geometries)
    reserved = [Point(a[1:]).buffer(.505) for a, b in
                zip(PROBE_28_CH022_LAYERS, PROBE_28_CH022_LAYERS[1:])
                if a[0] != b[0]]
    rows: list[dict[str, Any]] = []
    native_proposals: list[tuple[int, int, int]] = []
    for item in candidates:
        track = track_by_uuid[item["uuid"]]
        start, end = xy(track.GetStart()), xy(track.GetEnd())
        for size in MICRO_MM:
            for sign in (-1, 1):
                delta = sign * size
                proposed = micro_dogleg(start, end, delta)
                moved = LineString(proposed)
                collided = []
                for ix in tree.query(moved, predicate="intersects"):
                    peer = items[int(ix)]
                    if peer["uuid"] == item["uuid"] or peer["net"] == item["net"]:
                        continue
                    # VCM clearance is treated at least as strict as power.
                    obstacle = geometries[int(ix)]
                    if peer["net"].startswith("VCM"):
                        obstacle = obstacle.buffer(.355)
                    if moved.intersects(obstacle):
                        collided.append(dict(uuid=peer["uuid"],
                                             net=peer["net"], kind=peer["kind"]))
                ch022_conflict = any(moved.buffer(.225).intersects(p)
                                     for p in reserved)
                old_crosses = bool(corridor.intersects(
                    LineString([start, end]).buffer(.225)))
                new_crosses = bool(corridor.intersects(moved.buffer(.225)))
                within = bool(edge.covers(moved))
                eligible = (within and not collided and not ch022_conflict
                            and old_crosses and not new_crosses)
                row = dict(uuid=item["uuid"], net=item["net"],
                           shift_mm=delta, shifted_points_mm=[
                               [round(v, 6) for v in p] for p in proposed],
                           edge_clearance=within,
                           foreign_obstacles=collided[:20],
                           foreign_collision_count=len(collided),
                           CH022_via_window_preserved=not ch022_conflict,
                           current_direct_crossover=old_crosses,
                           clears_direct_corridor=new_crosses is False,
                           isolated_geometry_eligible=eligible,
                           native_DRC_passed=False,
                           all_neighbor_nets_restituted=False)
                rows.append(row)
                if eligible:
                    native_proposals.append((len(rows)-1,
                                             len(native_proposals),
                                             len(collided)))
    # Local topological test of *only* the nine signal obstacles virtually
    # removed, leaving all protected vias/pads/VCM intact. No board mutation.
    topologies = []
    movable = {b["uuid"] for b in candidates}
    for margin in (3.0, 6.0, 10.0):
        from shapely.ops import unary_union
        a, b = pair["source_mm"], pair["target_mm"]
        region = box(min(a[0], b[0])-margin, min(a[1], b[1])-margin,
                     max(a[0], b[0])+margin, max(a[1], b[1])+margin).intersection(edge)
        near = [int(i) for i in tree.query(region)]
        blocked = unary_union([
            geometries[i].intersection(region) for i in near
            if items[i]["uuid"] not in movable and
            items[i]["net"] != CH025
        ])
        patches = region.difference(blocked).buffer(-.000005)
        starts = [p for p in _polygons(patches) if p.covers(Point(a))]
        targets = [p for p in _polygons(patches) if p.covers(Point(b))]
        same = bool(starts and targets and starts[0].equals(targets[0]))
        topologies.append(dict(margin_mm=margin,
                               virtual_nine_removed=True,
                               FCu_component_connected=same,
                               qualified_route=False))
    baseline_drc = None
    attempted = 0
    for ix, _, _ in native_proposals[:max_native]:
        trial = rows[ix]
        with tempfile.TemporaryDirectory(prefix="ch025-micro-drc-", dir=workspace) as folder:
            root = Path(folder)
            for name in MEMBERS:
                (root / name).write_bytes((workspace/name).read_bytes())
            board_path = root / MEMBERS[0]
            sample = pcbnew.LoadBoard(str(board_path))
            target = next(t for t in sample.GetTracks()
                          if t.m_Uuid.AsString() == trial["uuid"])
            netcode = target.GetNetCode()
            sample.Remove(target)
            for left, right in zip(trial["shifted_points_mm"],
                                   trial["shifted_points_mm"][1:]):
                make_track(sample, tuple(left), tuple(right), netcode, .15,
                           pcbnew.F_Cu)
            pcbnew.SaveBoard(str(board_path), sample)
            # Native helper restores original reviewed .kicad_pro before DRC.
            report = native(board_path, root / "native.json")
            trial["native_metrics"] = metrics(report)
            if baseline_drc is None:
                # Separately obtain the unchanged baseline, once.
                orig = workspace / MEMBERS[0]
                baseline_drc = native(orig, workspace / "baseline.json")
            regression = regressed_nets(baseline_drc, report)
            trial["regressed_nets"] = regression
            attempted += 1
            trial["native_DRC_passed"] = metrics(report) == dict(
                violations=0, warnings=0, unconnected=139)
            trial["all_neighbor_nets_restituted"] = not regression
    best = min(rows, key=lambda r: (
        not r["isolated_geometry_eligible"],
        r["foreign_collision_count"],
        not r["clears_direct_corridor"],
        abs(r["shift_mm"])))
    return {**FLAGS, "status": "FCu_microselect_screened_not_closed",
            "accepted": False, "source_archive_sha256": ARCHIVE_SHA256,
            "source_pcb_sha256": BOARD_SHA256,
            "baseline_airwires": 139, "target_airwires": 136,
            "selected_pair": dict(source_uuid=pair["source_uuid"],
                                  target_uuid=pair["target_uuid"],
                                  CH025_offset_mm=option["offset_mm"],
                                  direct_blockers=28,
                                  fixed_blockers=19,
                                  movable_blockers=9),
            "tested_displacements": len(rows),
            "geometry_eligible_count": len(native_proposals),
            "native_trials": attempted, "native_drc_qualified": False,
            "protected_other_tracks_changed": False,
            "In1_Cu_used": False, "L3_loss_mm2": None,
            "L3_gain_mm2": None, "all_neighbors_restituted": False,
            "geometrically_best": best,
            "virtual_topology": topologies,
            "displacements": rows}


def _polygons(shape: Any) -> list[Any]:
    if shape.geom_type == "Polygon":
        return [shape]
    return [p for g in getattr(shape, "geoms", ()) for p in _polygons(g)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-native", type=int, default=2)
    args = parser.parse_args()
    if not 0 <= args.max_native <= 4:
        raise SystemExit("Bound native trial budget to 0..4")
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Wrong immutable 139 ZIP")
    inventory = json.loads(args.inventory.read_text())
    with tempfile.TemporaryDirectory(prefix="ch025-micro-") as folder:
        work = Path(folder)
        with zipfile.ZipFile(args.archive) as archive:
            if sorted(archive.namelist()) != sorted(MEMBERS):
                raise SystemExit("Unexpected ZIP entries")
            for name in MEMBERS:
                (work / name).write_bytes(archive.read(name))
        pcb = work / MEMBERS[0]
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != BOARD_SHA256:
            raise SystemExit("139 source PCB checksum mismatch")
        import pcbnew
        if not pcbnew.Version().startswith("8.0.9"):
            raise SystemExit("Native KiCad 8.0.9 required")
        result = scan(pcbnew.LoadBoard(str(pcb)), inventory, args.max_native, work)
        if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise RuntimeError("Changed pinned source archive")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({k: result[k] for k in
                          ("status", "tested_displacements",
                           "geometry_eligible_count", "native_trials",
                           "accepted", "fabrication_release")}))


if __name__ == "__main__":
    main()

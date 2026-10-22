#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed cooperative F.Cu eight-net routing on SHA-pinned 139 PCB.

BPS: bounded best-priority permutations, with native-obstacle shortest-path
mesh as the local search primitive (the latter is Dijkstra, not A*).
The old 16-point CH025 line is NOT pinned. Every selected neighbor track,
its original start/end coordinates and original net assignment are protected
by endpoint and board-UUID checks. No new pads/vias, B.Cu, or In1.Cu copper.
All routes are scratch-only. Failed orders are discarded without promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from analyze_ch025_fcu_blocker_uuids import (
    ARCHIVE_SHA256, BOARD_SHA256, MEMBERS, protected_net,
)
from probe_ch025_neighbor_restitution7 import NEIGHBORS, UNCHANGED
from probe_ch025_fcu_l3_exact import (
    CUT, NET, OTHER, ZONE, track_inventory, power_fcu_obstacles,
    trial_l3_mask,
)
from analyze_ch025_l3_precision_mask import (
    PROBE_28_CH022_LAYERS, exact_native_difference,
)

SRC_VIA = "c9831d96-6bbb-4308-9c5d-e72b6ccfbdac"
DST_VIA = "c51e9b29-e51a-45cf-8047-3dd4484ec17e"
SRC = (49.45, 14.90)
DST = (36.105, 48.85)
NATIVE_WINDOW_MM = (3.0, 6.0, 10.0)
FLAGS = dict(
    accepted=False, routing_completed=False,
    fabrication_release=False, manufacturing_files=False,
    checkpoint_promoted=False, independent_replay_verified=False,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_locked_plan() -> None:
    if (len(NEIGHBORS) != 7 or len(UNCHANGED) != 2
            or set(NEIGHBORS.values()) != {
                "MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3", "MUX_EN",
                "CH027_N_MUX", "CH030_P_MUX",
            }):
        raise ValueError("Seven-neighbor identity mismatch")
    if any(protected_net(net) for net in NEIGHBORS.values()):
        raise ValueError("Protected copper selected for ripup")
    if SRC != (49.45, 14.90) or DST != (36.105, 48.85):
        raise ValueError("Unreviewed CH025 via anchors")


def order_schedules() -> list[tuple[str, ...]]:
    """Four deterministic priority permutations; every net exactly once."""
    mux = ("MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3", "MUX_EN")
    analog = ("CH027_N_MUX", "CH030_P_MUX")
    schedules = [
        (NET, *analog, *mux),
        (*analog, *mux, NET),
        ("MUX_S1", "MUX_EN", NET, "CH027_N_MUX",
         "CH030_P_MUX", "MUX_S0", "MUX_S2", "MUX_S3"),
        ("CH027_N_MUX", "MUX_S0", "MUX_S1", "CH030_P_MUX",
         NET, "MUX_S2", "MUX_S3", "MUX_EN"),
    ]
    target = {NET, *NEIGHBORS.values()}
    if len(schedules) != 4 or any(set(s) != target or len(s) != 8
                                   for s in schedules):
        raise RuntimeError("BPS permutations do not cover all eight nets")
    return schedules


def unchanged_fingerprints(board: Any) -> dict[str, Any]:
    from route_targeted_closure import xy
    return {
        "vias": sorted(
            (t.m_Uuid.AsString(), t.GetNetname(), xy(t.GetPosition()),
             t.GetWidth(), t.GetDrillValue())
            for t in board.GetTracks() if type(t).__name__ == "PCB_VIA"
        ),
        "pads": sorted(
            (p.m_Uuid.AsString(), p.GetNetname(), xy(p.GetPosition()))
            for fp in board.GetFootprints() for p in fp.Pads()
        ),
        "zones": sorted(
            (z.m_Uuid.AsString(), z.GetNetname(), z.GetLayerSet().FmtBin())
            for z in board.Zones()
        ),
    }


def pinned_items(board: Any) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    import pcbnew
    from route_targeted_closure import xy

    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    long = tracks.get(CUT)
    if (long is None or long.GetNetname() != NET or
            long.GetLayer() != pcbnew.In2_Cu):
        raise ValueError("Original CH025 In2.Cu track not found")
    via = {
        key: tracks.get(key) for key in (SRC_VIA, DST_VIA)
    }
    if any(v is None or not isinstance(v, pcbnew.PCB_VIA)
           or v.GetNetname() != NET for v in via.values()):
        raise ValueError("Native CH025 via anchors changed")
    for key, pos in ((SRC_VIA, SRC), (DST_VIA, DST)):
        if math.dist(xy(via[key].GetPosition()), pos) > .001:
            raise ValueError("Original via coordinate changed")
    items: dict[str, Any] = {NET: long}
    for uid, net in NEIGHBORS.items():
        t = tracks.get(uid)
        if (t is None or t.GetNetname() != net or
                t.GetLayer() != pcbnew.F_Cu or
                isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)) or
                pcbnew.ToMM(t.GetWidth()) != .15):
            raise ValueError("Unexpected movable neighbor UUID: " + uid)
        items[net] = t
    if len(items) != 8:
        raise ValueError("Duplicate selected nets")
    for uid, net in UNCHANGED.items():
        t = tracks.get(uid)
        if t is None or t.GetNetname() != net:
            raise ValueError("Protected untouched MUX_S2 or CH028 track lost")
    zone = next((z for z in board.Zones()
                 if z.m_Uuid.AsString() == ZONE and
                 z.GetNetname() == "3V3A" and z.IsOnLayer(pcbnew.In2_Cu)),
                None)
    if zone is None:
        raise ValueError("L3 3V3A reference polygon changed")
    return items, zone, via


def candidate_route(board: Any, name: str, segment: Any,
                    power: Any, power_obstacles: Any,
                    via_guard: Any, margin: float) -> Any | None:
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from shapely.ops import unary_union
    from escape_mesh_505 import mesh_route
    from route_targeted_closure import xy, routing_domain

    start, end = ((SRC, DST) if name == NET else
                  (xy(segment.GetStart()), xy(segment.GetEnd())))
    region = box(min(start[0], end[0]) - margin,
                 min(start[1], end[1]) - margin,
                 max(start[0], end[0]) + margin,
                 max(start[1], end[1]) + margin)
    domain = routing_domain(board, .075, .25)
    if not domain.covers(Point(start)) or not domain.covers(Point(end)):
        return None
    region = region.intersection(domain)
    if region.is_empty:
        return None
    route = mesh_route(
        board, start, end, board.FindNet(name).GetNetCode(),
        (pcbnew.F_Cu, pcbnew.B_Cu), power, region,
        start_layer=0, goal_layer=0, allow_vias=False,
        extra_obstacles=[
            unary_union([power_obstacles, via_guard]),
            GeometryCollection(),
        ])
    if (route is None or len(route) < 2
            or any(v[0] != 0 for v in route)
            or math.dist(route[0][1:], start) > .000002
            or math.dist(route[-1][1:], end) > .000002):
        return None
    return route


def attempt(work: Path, schedule: tuple[str, ...],
            max_margin: float) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from escape_mesh_505 import add_mesh_path
    from analyze_ch025_l3_native_refill import filled
    from native_connectivity import airwire_counts, regressed_nets
    from route_targeted_closure import metrics, native

    pcbfile = work / MEMBERS[0]
    board = pcbnew.LoadBoard(str(pcbfile))
    before = track_inventory(board)
    fingerprints = unchanged_fingerprints(board)
    originals, zone, _ = pinned_items(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    original_l3 = pcbnew.SHAPE_POLY_SET(
        zone.GetFilledPolysList(pcbnew.In2_Cu))
    power = filled(zone)
    selected = {t.m_Uuid.AsString() for t in originals.values()}
    for track in originals.values():
        board.Remove(track)
    # Protected and otherwise existing objects are never removed.
    for uid, item in before.items():
        if uid not in selected and track_inventory(board).get(uid) != item:
            raise RuntimeError("Foreign copper UUID modified by ripup")
    guarded = [
        Point(a[1:]).buffer(.505)
        for a, b in zip(PROBE_28_CH022_LAYERS, PROBE_28_CH022_LAYERS[1:])
        if a[0] != b[0]
    ]
    guard = unary_union(guarded)
    fixed_power = power_fcu_obstacles(board)
    report: dict[str, Any] = {
        **FLAGS, "status": "cooperative_bps_started",
        "order": list(schedule), "connected": [],
        "failure": None,
        "native_DRC": None, "native_parity_pass": False,
        "L3_loss_mm2": None, "L3_gain_mm2": None,
    }
    for name in schedule:
        segment = originals[name]
        rows: list[dict[str, Any]] = []
        path = None
        for margin in NATIVE_WINDOW_MM:
            if margin > max_margin:
                continue
            path = candidate_route(board, name, segment, power,
                                   fixed_power, guard, margin)
            rows.append(dict(margin_mm=margin, route_found=path is not None))
            if path is not None:
                break
        if path is None:
            report["status"] = "unroutable_next_net"
            report["failure"] = dict(net=name, trials=rows)
            return report
        add_mesh_path(board, path, board.FindNet(name).GetNetCode(),
                      (pcbnew.F_Cu, pcbnew.B_Cu))
        report["connected"].append({
            "net": name, "points": len(path), "path": path,
            "trials": rows,
        })
    if len(report["connected"]) != 8:
        raise RuntimeError("Incomplete eight-net order")
    report["eight_geometry_proposed"] = True
    after = track_inventory(board)
    for uid, old in before.items():
        if uid not in selected and after.get(uid) != old:
            raise RuntimeError("Protected original track changed: " + uid)
    if unchanged_fingerprints(board) != fingerprints:
        raise RuntimeError("Pad, via or zone fingerprint changed")

    ch022 = list(PROBE_28_CH022_LAYERS)
    if len(ch022) != 23 or sum(a[0] != b[0]
                               for a, b in zip(ch022, ch022[1:])) != 4:
        raise RuntimeError("CH022 path geometry unverified")
    add_mesh_path(board, ch022, board.FindNet(OTHER).GetNetCode(),
                  (pcbnew.B_Cu, pcbnew.In2_Cu))
    report["CH022_geometry_proposed"] = True
    mask, measure = trial_l3_mask(board, zone, original_l3)
    report["mask_probe_status"] = measure["status"]
    report["mask_probe_trials"] = measure.get("trials", [])
    if not measure["native_exact"]:
        report["status"] = "L3_directional_delta_gate_failed"
        return report
    result = exact_native_difference(
        original_l3,
        pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.In2_Cu)))
    if not result["native_both_empty"]:
        raise RuntimeError("3V3A zone delta is not exactly zero")
    report["L3_loss_mm2"] = 0.0
    report["L3_gain_mm2"] = 0.0
    if mask is not None and not mask.IsRuleArea():
        raise RuntimeError("Invalid temporary L3 precision keepout")

    # No board or export outside the disposable root. Project snapshots stay
    # isolated; the checked-in PCB and 139 source ZIP are immutable.
    pcbnew.SaveBoard(str(pcbfile), board)
    baseline = native(work / "baseline" / MEMBERS[0],
                      work / "baseline-native.json")
    candidate = native(pcbfile, work / "candidate-native.json")
    report["native_DRC"] = metrics(candidate)
    report["regressed_nets"] = regressed_nets(baseline, candidate)
    old_counts, new_counts = airwire_counts(baseline), airwire_counts(candidate)
    report["eight_net_airwires_before"] = {
        name: old_counts[name] for name in schedule
    }
    report["eight_net_airwires_after"] = {
        name: new_counts[name] for name in schedule
    }
    if (metrics(baseline) != dict(violations=0, warnings=0, unconnected=139)
            or metrics(candidate) !=
            dict(violations=0, warnings=0, unconnected=136)
            or report["regressed_nets"]
            or any(new_counts[n] > old_counts[n] for n in schedule)):
        report["status"] = "native_136_DRC_or_neighbor_regression_failed"
        return report
    report["native_DRC_qualified"] = True
    parity = work / "schematic-parity.json"
    cmd = subprocess.run([
        "kicad-cli", "pcb", "drc", "--schematic-parity",
        "--format", "json", "--severity-all",
        "--all-track-errors", "--output", str(parity), str(pcbfile),
    ], capture_output=True, text=True, check=False)
    if cmd.returncode == 0 and parity.exists():
        data = json.loads(parity.read_text(encoding="utf-8"))
        report["native_parity_pass"] = (
            not data.get("violations") and not data.get("unconnected_items")
            and not data.get("schematic_parity"))
    report["status"] = ("qualified_geometry_pending_independent_replay"
                        if report["native_parity_pass"]
                        else "native_schematic_parity_failed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-orders", type=int, choices=(1, 2, 3, 4),
                        default=4)
    parser.add_argument("--max-margin", type=float, choices=(3.0, 6.0, 10.0),
                        default=6.0)
    args = parser.parse_args()
    assert_locked_plan()
    if digest(args.archive) != ARCHIVE_SHA256:
        raise SystemExit("Pinned immutable checkpoint ZIP SHA-256 mismatch")
    reports = []
    for order in order_schedules()[:args.max_orders]:
        with tempfile.TemporaryDirectory(prefix="ch025-cooperative8-") as d:
            work = Path(d)
            with zipfile.ZipFile(args.archive) as archive:
                if sorted(archive.namelist()) != sorted(MEMBERS):
                    raise RuntimeError("Unexpected 139 PCB archive members")
                for name in MEMBERS:
                    (work / name).write_bytes(archive.read(name))
            if digest(work / MEMBERS[0]) != BOARD_SHA256:
                raise RuntimeError("Immutable 139 PCB member hash mismatch")
            import pcbnew
            if not pcbnew.Version().startswith("8.0.9"):
                raise RuntimeError("KiCad 8.0.9 required for native geometry")
            (work / "baseline").mkdir()
            for name in MEMBERS:
                shutil.copy2(work / name, work / "baseline" / name)
            report = attempt(work, order, args.max_margin)
            reports.append(report)
            print(json.dumps({
                "order": report["order"],
                "status": report["status"],
                "eight_connected": len(report["connected"]),
                "blocked_by": (report["failure"] or {}).get("net"),
            }), flush=True)
            if report["status"] == "qualified_geometry_pending_independent_replay":
                break
    if digest(args.archive) != ARCHIVE_SHA256:
        raise RuntimeError("Pinned source archive changed after probe")
    result = {
        **FLAGS, "status": reports[-1]["status"],
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_pcb_sha256": BOARD_SHA256,
        "baseline_airwires": 139, "target_airwires": 136,
        "orders": reports, "orders_tried": len(reports),
        "F_Cu_only": True, "In1_Cu_used": False,
        "L3_gate_required": True,
        "manufacturing_export_invoked": False,
        "checkpoint_replaced": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "result": result["status"], "orders": result["orders_tried"],
        "accepted": False, "manufacturing_files": False,
    }), flush=True)


if __name__ == "__main__":
    main()

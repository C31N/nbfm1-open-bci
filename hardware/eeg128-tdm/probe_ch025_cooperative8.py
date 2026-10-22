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
import time
import sys
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
# Native geometry survey: original CH027 target is only 0.2807 mm from
# 3V3A U4.24. This existing unchanged CH027 via copper boundary offers
# 0.6895 mm local power clearance; final DRC/parity/replay remain mandatory.
CH027_ALT_VIA = "1c642f97-035a-4f4e-a6d9-81ebabc1ab2f"
CH027_ALT_TARGET = (32.475001, 47.760892)
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
                    via_guard: Any, margin: float,
                    unplaced: list[tuple[str, Any]],
                    bias: float, deadline: float
                    ) -> tuple[Any | None, dict[str, Any]]:
    """Bounded A* search with F.Cu congestion costs and exact polygon checking.

    Protect remaining terminal corridors by soft costs, never by moving pads
    or other immutable copper. A* is speculative; native KiCad DRC remains
    mandatory. Reject an entire raster route if any segment misses the exact
    geometric free space, including 0.505-mm power clearance and CH022 vias.
    """
    import pcbnew
    import time
    from shapely.geometry import GeometryCollection, LineString, Point, box
    from shapely.ops import unary_union
    from route_targeted_closure import (
        obstacles, routing_domain, search, xy,
    )

    start, end = ((SRC, DST) if name == NET else
                  (xy(segment.GetStart()), CH027_ALT_TARGET)
                  if name == "CH027_N_MUX" else
                  (xy(segment.GetStart()), xy(segment.GetEnd())))
    row: dict[str, Any] = {
        "margin_mm": margin, "mode": "astar_025_priority_cost",
        "priority_penalty": bias, "found": False,
        "reason": "not_attempted",
    }
    if time.monotonic() >= deadline:
        row["reason"] = "order_time_budget_exhausted"
        return None, row
    domain = routing_domain(board, .075, .25)
    if not domain.covers(Point(start)) or not domain.covers(Point(end)):
        row["reason"] = "source_or_target_outside_board_domain"
        return None, row
    region = box(min(start[0], end[0]) - margin,
                 min(start[1], end[1]) - margin,
                 max(start[0], end[0]) + margin,
                 max(start[1], end[1]) + margin).intersection(domain)
    if region.is_empty:
        row["reason"] = "empty_legal_region"
        return None, row
    future = []
    for future_name, foreign in unplaced:
        if future_name == name:
            continue
        a, b = ((SRC, DST) if future_name == NET else
                (xy(foreign.GetStart()), CH027_ALT_TARGET)
                if future_name == "CH027_N_MUX" else
                (xy(foreign.GetStart()), xy(foreign.GetEnd())))
        future.append(LineString([a, b]).buffer(.55))
    future_reserved = unary_union(future) if future else GeometryCollection()
    guard = unary_union([power_obstacles, via_guard.buffer(.075)])
    # Grid A* soft costs never override the final hard geometry rules.
    raster_mm = .15 if margin <= 3.0 else .20
    row["grid_mm"] = raster_mm
    route = search(
        board, start, end, board.FindNet(name).GetNetCode(),
        .15, .15, both_layers=False, margin=margin,
        step=raster_mm, max_nodes=18000,
        deadline=min(deadline, time.monotonic() + 8.0),
        start_layer=0, goal_layer=0,
        layers=(pcbnew.F_Cu, pcbnew.B_Cu),
        cost_regions=((0, guard, 250.0), (0, future_reserved, bias)),
    )
    if not route or any(point[0] != 0 for point in route):
        row["reason"] = "astar_no_layer0_solution_under_budget"
        return None, row
    if (math.dist(route[0][1:], start) > .000002
            or math.dist(route[-1][1:], end) > .000002):
        row["reason"] = "original_net_endpoints_not_preserved"
        return None, row
    blocked = obstacles(
        board, board.FindNet(name).GetNetCode(),
        .15, .15, region, .60,
        (pcbnew.F_Cu, pcbnew.B_Cu),
    )[0][0]
    free = region.difference(unary_union([blocked, guard])).buffer(-.000005)
    coords = [(float(v[1]), float(v[2])) for v in route]
    path = [coords[0]]
    i = 0
    # Farthest-visible pruning produces a bounded number of native tracks;
    # no outside-layer detours, corner cuts, or zero-length segments.
    while i < len(coords)-1:
        found = None
        for j in range(len(coords)-1, i, -1):
            if free.covers(LineString([coords[i], coords[j]])):
                found = j
                break
        if found is None:
            row["reason"] = "astar_raster_or_anchor_hits_fcu_obstacles"
            return None, row
        path.append(coords[found])
        i = found
        if len(path) > 300:
            row["reason"] = "path_complexity_limit"
            return None, row
    route = [(0, round(x, 6), round(y, 6)) for x, y in path]
    if (not domain.covers(LineString([v[1:] for v in route]))
            or any(not free.covers(LineString([a[1:], b[1:]]))
                   for a, b in zip(route, route[1:]))):
        row["reason"] = "nanometre_rounding_changed_clearance"
        return None, row
    row["found"] = True
    row["reason"] = "geometric_proposal_requires_native_DRC"
    row["vertices"] = len(route)
    row["length_mm"] = round(sum(
        math.dist(a[1:], b[1:]) for a,b in zip(route, route[1:])), 6)
    return route, row



def terminal_fixed_neighbors(board: Any, name: str,
                             segment: Any) -> dict[str, Any]:
    """Read-only nearest blocker coordinates for failed F.Cu endpoints."""
    import pcbnew
    from shapely.geometry import Point, LineString
    from analyze_ch025_fcu_blocker_uuids import copper_shapes
    from route_targeted_closure import xy
    shapes, entries = copper_shapes(board)
    if name != NET:
        for t in board.GetTracks():
            if t.GetNetname() == NET and t.GetLayer() == pcbnew.F_Cu:
                shape = LineString([xy(t.GetStart()), xy(t.GetEnd())]).buffer(
                    pcbnew.ToMM(t.GetWidth()) / 2 + .225)
                shapes.append(shape)
                entries.append({"net": NET, "uuid": t.m_Uuid.AsString(),
                                "kind": "track", "protected": False})
    pts = ((SRC, DST) if name == NET else
           (xy(segment.GetStart()), CH027_ALT_TARGET)
           if name == "CH027_N_MUX" else
           (xy(segment.GetStart()), xy(segment.GetEnd())))
    near = {}
    for label, point in zip(("source", "target"), pts):
        origin = Point(point)
        candidates = []
        for shape, obj in zip(shapes, entries):
            if obj["net"] == name:
                continue
            distance = shape.distance(origin)
            if distance <= 2.0:
                candidates.append({
                    "uuid": obj["uuid"], "net": obj["net"],
                    "kind": obj["kind"], "protected": obj["protected"],
                    "clearance_expanded_distance_mm": round(distance, 6),
                })
        candidates.sort(key=lambda o: (
            o["clearance_expanded_distance_mm"], o["uuid"]))
        near[label] = {"coordinate_mm": list(point),
                       "foreign_obstacles_within_2mm": len(candidates),
                       "nearest": candidates[:8]}
    return near


def _write_child_progress(path: Path | None, report: dict[str, Any]) -> None:
    """Atomically retain native geometry diagnostics before expensive A*."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(path.suffix + ".tmp")
    staged.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    staged.replace(path)


def attempt(work: Path, schedule: tuple[str, ...],
            max_margin: float, bias: float,
            order_time_budget: float = 65.0,
            progress_path: Path | None = None) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from escape_mesh_505 import add_mesh_path
    from analyze_ch025_l3_native_refill import filled
    from native_connectivity import airwire_counts, regressed_nets
    from route_targeted_closure import metrics, native, xy

    report: dict[str, Any] = {
        **FLAGS, "status": "loading_immutable_board",
        "order": list(schedule), "connected": [],
        "failure": None, "native_DRC": None,
        "native_parity_pass": False,
        "L3_loss_mm2": None, "L3_gain_mm2": None,
        "phase_trace": [], "native_DRC_qualified": False,
    }
    began = time.monotonic()
    def stage(name: str) -> None:
        report["status"] = name
        report["phase_trace"].append({
            "phase": name,
            "elapsed_s": round(time.monotonic() - began, 3),
        })
        _write_child_progress(progress_path, report)

    stage("loading_immutable_board")
    pcbfile = work / MEMBERS[0]
    board = pcbnew.LoadBoard(str(pcbfile))
    stage("board_loaded_snapshot_original_copper")
    before = track_inventory(board)
    fingerprints = unchanged_fingerprints(board)
    originals, zone, _ = pinned_items(board)
    # Use an existing native saved fill ONLY for preliminary geometry.
    # Independent native baseline refill remains a mandatory release gate.
    existing_native = pcbnew.SHAPE_POLY_SET(
        zone.GetFilledPolysList(pcbnew.In2_Cu))
    report["saved_zone_fill_outlines"] = existing_native.OutlineCount()
    stage("saved_zone_fill_checked")
    if existing_native.OutlineCount() == 0:
        stage("refreshing_missing_saved_zone_fill")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        existing_native = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        if existing_native.OutlineCount() == 0:
            raise ValueError("No baseline native power fill available")
    power = filled(zone)
    stage("baseline_power_geometry_ready")
    selected = {t.m_Uuid.AsString() for t in originals.values()}
    for track in originals.values():
        board.Remove(track)
    # Build the comparison map ONCE after ripup. The former per-UUID full
    # track_inventory(board) caused O(N^2) SWIG reads and four probe timeouts
    # BEFORE the first A* candidate search. Never weaken this protection.
    after_ripup = track_inventory(board)
    for uid, item in before.items():
        if uid not in selected and after_ripup.get(uid) != item:
            raise RuntimeError("Foreign copper UUID modified by ripup: " + uid)
    if len(before) - len(after_ripup) != len(selected):
        raise RuntimeError("Unexpected count of removed selected copper")
    stage("protected_original_copper_locked")
    guarded = [
        Point(a[1:]).buffer(.505)
        for a, b in zip(PROBE_28_CH022_LAYERS, PROBE_28_CH022_LAYERS[1:])
        if a[0] != b[0]
    ]
    guard = unary_union(guarded)
    fixed_power = power_fcu_obstacles(board)
    stage("power_fcu_obstacles_ready")
    via = next((t for t in board.GetTracks()
                if t.m_Uuid.AsString() == CH027_ALT_VIA
                and isinstance(t, pcbnew.PCB_VIA)
                and t.GetNetname() == "CH027_N_MUX"),None)
    if via is None:
        raise RuntimeError("Native immutable CH027 anchor via missing")
    via_center = xy(via.GetPosition())
    via_radius = pcbnew.ToMM(via.GetWidth()) / 2
    if abs(math.dist(via_center,CH027_ALT_TARGET)-via_radius) > .005:
        raise RuntimeError("Alternate CH027 target not on native via contour")
    if fixed_power.distance(Point(CH027_ALT_TARGET)) <= .000005:
        raise RuntimeError("Alternate CH027 target violates 0.505 power hard exclusion")
    report["CH027_alternate_native_via_anchor"] = {
        "uuid": CH027_ALT_VIA,
        "coordinate_mm": list(CH027_ALT_TARGET),
        "existing_via_unmoved": True,
        "power_clearance_geometrically_prequalified": True,
        "restoration_native_DRC_proven": False,
    }
    stage("CH027_safe_alternate_via_anchor_locked")
    order_deadline = time.monotonic() + order_time_budget
    stage("cooperative_bps_started")
    for name in schedule:
        segment = originals[name]
        endpoint_a, endpoint_b = (
            (SRC, DST) if name == NET
            else (xy(segment.GetStart()), CH027_ALT_TARGET)
            if name == "CH027_N_MUX"
            else (xy(segment.GetStart()), xy(segment.GetEnd()))
        )
        rows: list[dict[str, Any]] = []
        path = None
        # UUID and endpoint evidence is written before A* so the parent
        # can recover it even if this child exceeds its hard wall-clock cap.
        stage("diagnosing_" + name)
        diagnosis = terminal_fixed_neighbors(board, name, segment)
        report["status"] = "evaluating_single_net"
        report["failure"] = {
            "net": name, "source_mm": list(endpoint_a),
            "target_mm": list(endpoint_b), "terminal_distance_mm": round(
                math.dist(endpoint_a, endpoint_b), 6),
            "local_endpoint_obstacles": diagnosis, "trials": rows,
        }
        _write_child_progress(progress_path, report)
        for margin in NATIVE_WINDOW_MM:
            if margin > max_margin:
                continue
            rows.append({"margin_mm": margin,
                         "status": "native_astar_attempt_in_progress"})
            _write_child_progress(progress_path, report)
            pending = [(n, originals[n]) for n in schedule
                       if n not in {v["net"] for v in report["connected"]}]
            path, detail = candidate_route(
                board, name, segment, power, fixed_power, guard,
                margin, pending, bias, order_deadline)
            rows[-1] = detail
            _write_child_progress(progress_path, report)
            if path is not None:
                break
            if time.monotonic() >= order_deadline:
                report["status"] = "bounded_order_budget_exhausted"
                _write_child_progress(progress_path, report)
                return report
        if path is None:
            report["status"] = "unroutable_next_net"
            _write_child_progress(progress_path, report)
            return report
        add_mesh_path(board, path, board.FindNet(name).GetNetCode(),
                      (pcbnew.F_Cu, pcbnew.B_Cu))
        report["connected"].append({
            "net": name, "points": len(path), "path": path,
            "trials": rows,
        })
        report["failure"] = None
        report["status"] = "partial_net_routes_only"
        _write_child_progress(progress_path, report)
    if len(report["connected"]) != 8:
        raise RuntimeError("Incomplete eight-net order")
    report["eight_geometry_proposed"] = True
    report["status"] = "eight_geometric_routes_require_native_gates"
    _write_child_progress(progress_path, report)
    after = track_inventory(board)
    for uid, old in before.items():
        if uid not in selected and after.get(uid) != old:
            raise RuntimeError("Protected original track changed: " + uid)
    if unchanged_fingerprints(board) != fingerprints:
        raise RuntimeError("Pad, via or zone fingerprint changed")

    # Independently refill an unmodified baseline before the first L3
    # acceptance test. Saved fill has no release authority.
    stage("native_refill_independent_baseline_before_L3_gate")
    reference_board = pcbnew.LoadBoard(
        str(work / "baseline" / MEMBERS[0]))
    reference_zone = next(
        (z for z in reference_board.Zones()
         if z.m_Uuid.AsString() == ZONE and
         z.GetNetname() == "3V3A"
         and z.IsOnLayer(pcbnew.In2_Cu)), None)
    if reference_zone is None:
        raise RuntimeError("Independent native baseline zone missing")
    pcbnew.ZONE_FILLER(reference_board).Fill(reference_board.Zones())
    original_l3 = pcbnew.SHAPE_POLY_SET(
        reference_zone.GetFilledPolysList(pcbnew.In2_Cu))
    if original_l3.OutlineCount() == 0:
        raise RuntimeError("Independent native power refill empty")
    stage("native_original_power_refill_ready")
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


def one_order(archive_path: Path, index: int,
              max_margin: float, order_budget: float,
              progress_path: Path | None = None) -> dict[str, Any]:
    """Execute one KiCad SWIG BOARD lifecycle in an isolated child process."""
    _write_child_progress(progress_path, {
        **FLAGS, "status": "child_started_before_archive_extraction",
        "order": list(order_schedules()[index]), "connected": [],
        "failure": {"net": None},
        "phase_trace": [{"phase": "child_started_before_archive_extraction",
                         "elapsed_s": 0.0}],
        "native_DRC": None, "native_DRC_qualified": False,
        "L3_loss_mm2": None, "L3_gain_mm2": None,
    })
    with tempfile.TemporaryDirectory(prefix="ch025-single-order-") as d:
        work = Path(d)
        with zipfile.ZipFile(archive_path) as archive:
            if sorted(archive.namelist()) != sorted(MEMBERS):
                raise RuntimeError("Unexpected 139 PCB archive members")
            for name in MEMBERS:
                (work / name).write_bytes(archive.read(name))
        if digest(work / MEMBERS[0]) != BOARD_SHA256:
            raise RuntimeError("Immutable 139 PCB member hash mismatch")
        _write_child_progress(progress_path, {
            **FLAGS, "status": "archive_verified_pre_pcbnew",
            "order": list(order_schedules()[index]), "connected": [],
            "failure": {"net": None},
            "phase_trace": [{"phase": "archive_verified_pre_pcbnew",
                             "elapsed_s": 0.0}],
            "native_DRC": None, "native_DRC_qualified": False,
            "L3_loss_mm2": None, "L3_gain_mm2": None,
        })
        import pcbnew
        if not pcbnew.Version().startswith("8.0.9"):
            raise RuntimeError("KiCad 8.0.9 required")
        (work / "baseline").mkdir()
        for name in MEMBERS:
            shutil.copy2(work / name, work / "baseline" / name)
        return attempt(work, order_schedules()[index], max_margin,
                       bias=(.15, .75, 1.5, 3.0)[index],
                       order_time_budget=order_budget,
                       progress_path=progress_path)


def write_evidence(path: Path, reports: list[dict[str, Any]]) -> None:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(result, indent=2) + "\n",
                      encoding="utf-8")
    staged.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-orders", type=int, choices=(1, 2, 3, 4),
                        default=4)
    parser.add_argument("--max-margin", type=float,
                        choices=(3.0, 6.0, 10.0), default=6.0)
    parser.add_argument("--single-order", type=int,
                        choices=(0, 1, 2, 3), default=None)
    parser.add_argument("--order-budget", type=float, default=65.0)
    args = parser.parse_args()
    assert_locked_plan()
    if not (10.0 <= args.order_budget <= 180.0):
        raise ValueError("Strict per-order time budget required")
    if digest(args.archive) != ARCHIVE_SHA256:
        raise SystemExit("Pinned immutable checkpoint ZIP SHA-256 mismatch")
    if args.single_order is not None:
        report = one_order(args.archive, args.single_order,
                           args.max_margin, args.order_budget,
                           progress_path=args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "single_order": args.single_order,
            "status": report["status"],
            "eight_connected": len(report["connected"]),
            "blocker": (report["failure"] or {}).get("net"),
        }), flush=True)
        return

    reports = []
    for index in range(args.max_orders):
        with tempfile.TemporaryDirectory(prefix="cooperative-order-child-") as d:
            individual = Path(d) / "result.json"
            cmd = [sys.executable, str(Path(__file__).resolve()),
                   "--archive", str(args.archive.resolve()),
                   "--output", str(individual),
                   "--max-margin", str(args.max_margin),
                   "--single-order", str(index),
                   "--order-budget", str(args.order_budget)]
            try:
                proc = subprocess.run(cmd, capture_output=True,
                                      text=True, timeout=args.order_budget + 12,
                                      check=False)
                if proc.returncode == 0 and individual.is_file():
                    report = json.loads(individual.read_text(
                        encoding="utf-8"))
                    if (report["order"] != list(order_schedules()[index])
                            or report["fabrication_release"] is not False
                            or report["accepted"] is not False):
                        raise RuntimeError("Untrusted child report")
                else:
                    report = {
                        **FLAGS, "status": "isolated_order_process_failed",
                        "order": list(order_schedules()[index]),
                        "connected": [], "failure": {
                            "net": None,
                            "child_exit_code": proc.returncode,
                            "stderr_tail": proc.stderr[-1200:],
                        },
                        "native_DRC": None,
                        "L3_loss_mm2": None, "L3_gain_mm2": None,
                    }
                if proc.stdout:
                    print(proc.stdout[-1500:], flush=True)
            except subprocess.TimeoutExpired:
                # The child checkpoints before every expensive A* trial.
                # Never mistake partial paths for electrical net restitution.
                recovered = None
                if individual.is_file():
                    try:
                        candidate = json.loads(individual.read_text(
                            encoding="utf-8"))
                        if (candidate.get("order") ==
                                list(order_schedules()[index]) and
                                all(candidate.get(k) is False for k in FLAGS)):
                            recovered = candidate
                    except (OSError, ValueError, TypeError):
                        recovered = None
                report = recovered if recovered is not None else {
                    **FLAGS, "order": list(order_schedules()[index]),
                    "connected": [], "failure": {"net": None},
                    "native_DRC": None, "L3_loss_mm2": None,
                    "L3_gain_mm2": None,
                }
                report["status"] = "isolated_order_timeout_partial_evidence"
                report["native_DRC_qualified"] = False
                report["native_parity_pass"] = False
                report["L3_loss_mm2"] = None
                report["L3_gain_mm2"] = None
                report["independent_replay_verified"] = False
                report.setdefault("failure", {})
                if report["failure"] is None:
                    report["failure"] = {"net": None}
                report["failure"]["time_budget_s"] = (
                    args.order_budget + 12)
                report["failure"]["partial_evidence_recovered"] = (
                    recovered is not None)
        reports.append(report)
        write_evidence(args.output, reports)
        print(json.dumps({
            "order_index": index, "status": report["status"],
            "connected": len(report["connected"]),
            "blocking_net": (report["failure"] or {}).get("net"),
            "accepted": False,
        }), flush=True)
        if report["status"] == "qualified_geometry_pending_independent_replay":
            break
    if digest(args.archive) != ARCHIVE_SHA256:
        raise RuntimeError("Pinned source archive changed after probe")
    write_evidence(args.output, reports)
    print(json.dumps({
        "result": reports[-1]["status"], "orders": len(reports),
        "accepted": False, "fabrication_release": False,
    }), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed F.Cu-only CH025 plus CH022/L3 joint native probe.

This is a scratch-board diagnostic, NOT a checkpoint or manufacturing writer.
The original board and every foreign-net UUID are immutable. In1.Cu AGND
is strictly excluded. Only a full native gate may justify later promotion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

NET = "CH025_N_MUX"
OTHER = "CH022_N_ELECTRODE"
ZONE = "06a28b70-5141-41e4-bdb1-c8324bc06fcb"
CUT = "748cc9c4-2d8f-4ec6-9714-133d79d4c7cb"
L3_MASK_OFFSETS_MM = (-0.100, -0.050, -0.025, 0.0, 0.025, 0.050)
FLAGS = dict(accepted=False, routing_completed=False,
             fabrication_release=False, manufacturing_files=False,
             independent_replay_verified=False, checkpoint_promoted=False)


def track_inventory(board):
    from route_targeted_closure import xy
    return {
        t.m_Uuid.AsString(): (t.GetNetname(), t.GetLayer(),
                              xy(t.GetStart()), xy(t.GetEnd()),
                              t.GetWidth(), type(t).__name__)
        for t in board.GetTracks()
    }


def protected_unchanged(before, after):
    """Only CH025's pinned cut and new CH022/CH025 copper may differ."""
    return all(after.get(uid) == properties for uid, properties in before.items()
               if uid != CUT)


def power_fcu_obstacles(board):
    """Enforce 0.505 mm *copper-to-copper* on F.Cu around power nets."""
    import pcbnew
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    from route_targeted_closure import POWER, pad_copper_shape, xy

    shapes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in POWER and pad.IsOnLayer(pcbnew.F_Cu):
                shapes.append(pad_copper_shape(pad, pcbnew.F_Cu).buffer(.505 + .075))
    for t in board.GetTracks():
        if t.GetNetname() not in POWER:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            geometry = Point(xy(t.GetPosition())).buffer(
                pcbnew.ToMM(t.GetWidth()) / 2)
        elif t.GetLayer() != pcbnew.F_Cu:
            continue
        elif isinstance(t, pcbnew.PCB_ARC):
            # Unsupported arcs are a hard exclusion, never a straight chord.
            bbox = t.GetBoundingBox()
            from shapely.geometry import box
            geometry = box(pcbnew.ToMM(bbox.GetX()), pcbnew.ToMM(bbox.GetY()),
                           pcbnew.ToMM(bbox.GetRight()),
                           pcbnew.ToMM(bbox.GetBottom()))
        else:
            geometry = LineString(
                [xy(t.GetStart()), xy(t.GetEnd())]).buffer(
                    pcbnew.ToMM(t.GetWidth()) / 2)
        shapes.append(geometry.buffer(.505 + .075))
    return unary_union(shapes)


def route_fcu(board, source, target, power):
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from analyze_ch025_existing_via_anchor import connected_existing_vias
    from route_targeted_closure import routing_domain
    from escape_mesh_505 import mesh_route

    code = board.FindNet(NET).GetNetCode()
    upstream = connected_existing_vias(board, source, code, power, max_candidates=4)
    downstream = connected_existing_vias(board, target, code, power, max_candidates=4)
    report = dict(source=upstream, target=downstream, attempts=[],
                  new_vias=False, layer="F.Cu", In1_Cu_used=False)
    if (upstream["unknown_arc_count"] or downstream["unknown_arc_count"]
            or not upstream["via_candidates"] or not downstream["via_candidates"]):
        report["status"] = "missing_verified_retained_via_anchor"
        return None, report
    domain = routing_domain(board, .075, .25)
    power_copper = power_fcu_obstacles(board)
    for s in upstream["via_candidates"]:
        for t in downstream["via_candidates"]:
            a, b = tuple(s["coordinate_mm"]), tuple(t["coordinate_mm"])
            if s["uuid"] == t["uuid"]:
                continue
            if not domain.covers(Point(a)) or not domain.covers(Point(b)):
                continue
            for margin in (3.0, 6.0, 10.0):
                corridor = box(min(a[0], b[0]) - margin,
                               min(a[1], b[1]) - margin,
                               max(a[0], b[0]) + margin,
                               max(a[1], b[1]) + margin).intersection(domain)
                attempt = dict(source_uuid=s["uuid"], target_uuid=t["uuid"],
                               margin_mm=margin, source_mm=list(a),
                               target_mm=list(b), path_found=False)
                report["attempts"].append(attempt)
                # B.Cu is only a dummy second layer to use the existing mesh
                # solver. With allow_vias=False and start/goal layer 0, every
                # accepted vertex must be F.Cu. No B.Cu detour is admissible.
                route = mesh_route(
                    board, a, b, code, (pcbnew.F_Cu, pcbnew.B_Cu),
                    power, corridor, start_layer=0, goal_layer=0,
                    allow_vias=False,
                    extra_obstacles=[power_copper, GeometryCollection()])
                if (route and len(route) >= 2 and
                        route[0] == (0, *a) and route[-1] == (0, *b)
                        and all(v[0] == 0 for v in route)):
                    attempt["path_found"] = True
                    attempt["vertices"] = len(route)
                    report["status"] = "FCu_retained_via_geometry_unqualified"
                    return route, report
    report["status"] = "FCu_retained_via_geometry_not_found"
    return None, report


def poly_as_shapely(polys):
    from shapely.geometry import Polygon, GeometryCollection
    from shapely.ops import unary_union
    from route_targeted_closure import xy
    shapes = []
    for i in range(polys.OutlineCount()):
        outer = polys.Outline(i)
        if outer.PointCount() < 3:
            continue
        holes = []
        for h in range(polys.HoleCount(i)):
            chain = polys.Hole(i, h)
            holes.append([xy(chain.CPoint(k)) for k in range(chain.PointCount())])
        shape = Polygon(
            [xy(outer.CPoint(k)) for k in range(outer.PointCount())], holes)
        if not shape.is_valid:
            raise ValueError("Invalid native gain polygon; cannot build mask")
        shapes.append(shape)
    return unary_union(shapes) if shapes else GeometryCollection()


def trial_l3_mask(board, zone, baseline):
    import pcbnew
    from analyze_ch025_l3_precision_mask import (
        exact_native_difference, native_gain_compatibility)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    changed = pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.In2_Cu))
    initial = exact_native_difference(baseline, changed)
    report = dict(pre_loss_mm2=initial["loss_native_mm2"],
                  pre_gain_mm2=initial["gain_native_mm2"],
                  trials=[], mask_applied=False, native_exact=False)
    if initial["loss_native_outlines"]:
        report["status"] = "L3_loss_cannot_be_repaired_by_keepout"
        return None, report
    if initial["native_both_empty"]:
        report["status"] = "L3_exact_without_keepout"
        report["native_exact"] = True
        return None, report
    gained = initial["gain_polyset"]
    if gained.OutlineCount() > 20 or gained.VertexCount() > 1200:
        report["status"] = "native_gain_too_complex_for_rule_area"
        return None, report
    for offset in L3_MASK_OFFSETS_MM:
        mask = pcbnew.SHAPE_POLY_SET(gained)
        if offset:
            mask.Inflate(pcbnew.FromMM(offset),
                         pcbnew.SHAPE_POLY_SET.ROUND_ALL_CORNERS,
                         pcbnew.FromMM(.001))
        if not mask.OutlineCount() or mask.VertexCount() > 1500:
            continue
        compatible = native_gain_compatibility(poly_as_shapely(mask))
        row = dict(offset_mm=offset, CH022_corridor=compatible,
                   loss_mm2=None, gain_mm2=None, native_exact=False)
        report["trials"].append(row)
        if not compatible["protects_reviewed_CH022_in2_corridor"]:
            row["status"] = "CH022_corridor_intersection"
            continue
        rule = pcbnew.ZONE(board)
        rule.SetLayer(pcbnew.In2_Cu)
        rule.SetIsRuleArea(True)
        rule.SetDoNotAllowCopperPour(True)
        rule.SetDoNotAllowTracks(False)
        rule.SetDoNotAllowVias(False)
        rule.SetDoNotAllowPads(False)
        rule.SetDoNotAllowFootprints(False)
        rule.SetOutline(mask)
        board.Add(rule)
        try:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            filled = pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.In2_Cu))
            delta = exact_native_difference(baseline, filled)
            row.update(loss_mm2=delta["loss_native_mm2"],
                       gain_mm2=delta["gain_native_mm2"],
                       native_exact=delta["native_both_empty"])
            if delta["native_both_empty"]:
                report["status"] = "L3_native_polygon_exact_trial"
                report["native_exact"] = True
                report["mask_applied"] = True
                return rule, report
        finally:
            if not report["native_exact"]:
                board.Remove(rule)
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    report["status"] = "L3_exact_mask_not_found"
    return None, report


def run(source_path, output_path):
    import pcbnew
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    from analyze_ch025_l3_precision_mask import (
        PROBE_28_CH022_LAYERS, exact_native_difference)
    from analyze_ch025_l3_native_refill import filled
    from escape_mesh_505 import add_mesh_path
    from route_targeted_closure import xy, metrics, native
    from native_connectivity import regressed_nets

    result = {**FLAGS, "status": "started", "baseline_commit": "8c4f5d2d",
              "F_Cu_only": True, "In1_Cu_AGND_preserved": True,
              "L3_gate_exact": False, "native_DRC_qualified": False,
              "native_parity_qualified": False, "candidate_replay_qualified": False}
    # The tracked primary .kicad_pcb is the historical 499-airwire design.
    # Load ONLY the byte-reviewed 139-airwire *engineering* checkpoint.
    if source_path.suffix != ".zip":
        raise ValueError("A pinned 139 engineering ZIP, not the primary PCB, is mandatory")
    archive_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if archive_hash != "f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b":
        raise ValueError("Wrong immutable 139 checkpoint ZIP SHA-256")
    result["baseline_archive_sha256"] = archive_hash
    with tempfile.TemporaryDirectory(prefix="ch025-fcu-") as d:
        root = Path(d)
        scratch = root / "eeg128-tdm.kicad_pcb"
        members = ("eeg128-tdm.kicad_pcb", "eeg128-tdm.kicad_pro",
                   "eeg128-tdm.kicad_dru")
        with zipfile.ZipFile(source_path) as archive:
            if sorted(archive.namelist()) != sorted(members):
                raise ValueError("Wrong 139 checkpoint ZIP member inventory")
            for name in members:
                (root / name).write_bytes(archive.read(name))
        pcb_sha = hashlib.sha256(scratch.read_bytes()).hexdigest()
        if pcb_sha != "f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea":
            raise ValueError("Wrong 139 checkpoint PCB member SHA-256")
        result["source_pcb_sha256"] = pcb_sha
        original_project = scratch.with_suffix(".kicad_pro").read_bytes()
        baseline_drc = native(scratch, root / "drc-before.json")
        result["initial_drc"] = metrics(baseline_drc)
        if metrics(baseline_drc) != dict(violations=0, warnings=0, unconnected=139):
            result["status"] = "pinned_139_native_baseline_mismatch"
            return result
        board = pcbnew.LoadBoard(str(scratch))
        zones = [z for z in board.Zones()
                 if z.m_Uuid.AsString() == ZONE and z.GetNetname() == "3V3A"
                 and z.IsOnLayer(pcbnew.In2_Cu)]
        cuts = [t for t in board.GetTracks() if t.m_Uuid.AsString() == CUT]
        if len(zones) != 1 or len(cuts) != 1:
            result["status"] = "pinned_zone_or_cut_UUID_mismatch"
            return result
        zone, cut = zones[0], cuts[0]
        source, target = xy(cut.GetStart()), xy(cut.GetEnd())
        if (cut.GetNetname() != NET or cut.GetLayer() != pcbnew.In2_Cu
                or sorted((source, target)) !=
                sorted(((44.505, 25.129999), (44.505, 39.129999)))):
            result["status"] = "pinned_cut_geometry_mismatch"
            return result
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        original_native = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        baseline_tracks = track_inventory(board)
        power = filled(zone)
        board.Remove(cut)
        keepout = None
        try:
            # A fixed geometry proof is NOT an accepted CH022 track: add only
            # in this scratch-board trial, then let native DRC arbitrate.
            ch022 = board.FindNet(OTHER).GetNetCode()
            path = list(PROBE_28_CH022_LAYERS)
            if len(path) != 23 or sum(a[0] != b[0] for a, b in zip(path, path[1:])) != 4:
                raise ValueError("Unreviewed CH022 multihop geometry")
            in2 = [LineString([a[1:], b[1:]]).buffer(.075)
                   for a, b in zip(path, path[1:])
                   if a[0] == b[0] == 1]
            via = [Point(a[1:]).buffer(.505)
                   for a, b in zip(path, path[1:]) if a[0] != b[0]]
            if unary_union(in2 + via).intersects(power):
                result["status"] = "CH022_route_violates_505_L3_power"
                return result
            add_mesh_path(board, path, ch022, (pcbnew.B_Cu, pcbnew.In2_Cu))
            proposed, diagnostic = route_fcu(board, source, target, power)
            result["CH025_FCu"] = diagnostic
            if proposed is None:
                result["status"] = diagnostic["status"]
                return result
            add_mesh_path(board, proposed, board.FindNet(NET).GetNetCode(),
                          (pcbnew.F_Cu, pcbnew.B_Cu))
            result["CH022_waypoints"] = len(path)
            result["CH025_fcu_vertices"] = len(proposed)
            if not protected_unchanged(baseline_tracks, track_inventory(board)):
                raise RuntimeError("Protected existing copper changed")
            keepout, mask_report = trial_l3_mask(board, zone, original_native)
            result["L3_mask"] = mask_report
            if not mask_report["native_exact"]:
                result["status"] = mask_report["status"]
                return result
            result["L3_gate_exact"] = True
            pcbnew.SaveBoard(str(scratch), board)
            # SaveBoard may regenerate project defaults, so restore source
            # netclasses before any native DRC and after the temporary save.
            scratch.with_suffix(".kicad_pro").write_bytes(original_project)
            native_after = native(scratch, root / "drc-after.json")
            result["after_drc"] = metrics(native_after)
            result["regressed_nets"] = regressed_nets(baseline_drc, native_after)
            if (metrics(native_after) != dict(violations=0, warnings=0, unconnected=136)
                    or result["regressed_nets"]):
                result["status"] = "joint_native_DRC_or_136_gate_failed"
                return result
            result["native_DRC_qualified"] = True
            result["status"] = "native_136_geometry_pending_parity_and_byte_replay"
            # Intentionally no acceptance: independent schematic parity and
            # byte-identical replay must be demonstrated on a separate run.
            return result
        finally:
            if keepout is not None:
                board.Remove(keepout)
            for t in list(board.GetTracks()):
                if t.m_Uuid.AsString() not in baseline_tracks:
                    if t.GetNetname() not in (NET, OTHER):
                        raise RuntimeError("Unexpected foreign-net trial copper")
                    board.Remove(t)
            board.Add(cut)
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            if track_inventory(board) != baseline_tracks:
                raise RuntimeError("Native copper rollback mismatch")
            restored = pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu))
            if not exact_native_difference(original_native, restored)["native_both_empty"]:
                raise RuntimeError("L3 polygon rollback mismatch")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != archive_hash:
        raise RuntimeError("Source checkpoint ZIP was modified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {**FLAGS, "status": "diagnostic_exception"}
    try:
        result = run(args.board.resolve(), args.output.resolve())
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:1000]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, default=str))
    if result["status"] == "diagnostic_exception":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

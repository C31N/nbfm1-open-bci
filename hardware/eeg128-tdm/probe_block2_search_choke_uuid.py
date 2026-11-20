#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only top-state F.Cu choke and source139 UUID correlation.

The router's scratch-native gates are the classification authority. UUIDs
from the pinned source are only corroborating witnesses: 201 cut victims and
replaced CH038 segments are excluded, and unmatched masks remain unknown.
This probe cannot certify a three-route min-cut or a fabrication release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Sequence

from swig_free_fcu_geometry import (
    CuPrimitive, Vec2, native_polygon_to_primitive_distance,
    primitive_distance,
)

TRACK_RADIUS_MM = .075
COPPER_CLEARANCE_MM = .150
CENTRE_TO_OBSTACLE_SURFACE_MM = .225
CENTRELINE_PAIR_PITCH_MM = .300
NETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")


def _round(value: float) -> float:
    return round(float(value), 6)


def rank_fcu_witnesses(
    objects: Sequence[Any], net: str,
    a: tuple[float, float], b: tuple[float, float],
    cut_uuids: set[str], *, limit: int = 4,
) -> list[dict[str, Any]]:
    """Exact primitive-to-primitive gaps, otherwise qualified approximation."""
    step = CuPrimitive("TRACK", Vec2(*a), Vec2(*b), TRACK_RADIUS_MM)
    rows: list[dict[str, Any]] = []
    for obj in objects:
        if obj.uid in cut_uuids or obj.net == net:
            continue
        try:
            if obj.primitive is not None:
                _, gap, p, q = primitive_distance(step, obj.primitive)
                method = "exact_primitive_pair"
            elif obj.polygonization == "SHAPE_POLY_SET_native_0.0001mm":
                _, gap, q, p = native_polygon_to_primitive_distance(
                    obj.geometry, step)
                method = "native_polygon_0.0001mm_vs_exact_primitive"
            else:
                from shapely.geometry import LineString
                from shapely.ops import nearest_points
                segment = LineString((a, b))
                # Display copper geometry is approximate: do not label exact.
                p0, q0 = nearest_points(segment, obj.geometry)
                gap = segment.distance(obj.geometry) - TRACK_RADIUS_MM
                p, q = Vec2(p0.x, p0.y), Vec2(q0.x, q0.y)
                method = "unqualified_display_polygon_estimate"
        except (ValueError, TypeError, AttributeError, NotImplementedError):
            continue
        rows.append({
            "uuid": obj.uid,
            "net": obj.net,
            "kind": obj.kind,
            "name": obj.name,
            "layer": "F.Cu",
            "source_geometry": obj.polygonization,
            "measurement_method": method,
            "new_trace_copper_gap_mm": _round(gap),
            "new_centreline_to_obstacle_surface_mm": _round(
                gap + TRACK_RADIUS_MM),
            "new_trace_required_copper_clearance_mm": COPPER_CLEARANCE_MM,
            "hard_clearance_deficit_mm": _round(
                max(0., COPPER_CLEARANCE_MM - gap)),
            "nearest_new_trace_copper_xy_mm": [_round(p.x), _round(p.y)],
            "nearest_obstacle_copper_xy_mm": [_round(q.x), _round(q.y)],
            "provenance": "source139_unchanged_uuid_reference",
        })
    rows.sort(key=lambda row: (
        row["new_trace_copper_gap_mm"], row["uuid"]))
    return rows[:limit]


def correlate_states(
    states: Sequence[dict[str, Any]], objects: Sequence[Any],
    cut_uuids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    annotated: list[dict[str, Any]] = []
    blockers: dict[str, dict[str, Any]] = {}
    for state in states:
        probes: list[dict[str, Any]] = []
        for probe in state["direction_probes"]:
            report = dict(probe)
            witnesses = rank_fcu_witnesses(
                objects, report["net"],
                tuple(report["from_mm"]), tuple(report["to_mm"]),
                cut_uuids)
            report["nearest_source139_fcu_uuids"] = witnesses
            hard_fixed = report["classification"] in (
                "HARD_NATIVE_MASK_OR_ROI",
                "HARD_NATIVE_FIXED_COPPER_SEGMENT")
            qualified = [
                obj for obj in witnesses
                if obj["measurement_method"] !=
                "unqualified_display_polygon_estimate"
                and obj["new_trace_copper_gap_mm"] <
                COPPER_CLEARANCE_MM - 1e-8
            ]
            # Native scratch mask is authoritative; individual source
            # board UUID proximity alone is NOT proof of its cause.
            report["uuid_attribution"] = (
                "SOURCE139_UUID_POSSIBLE_NOT_SCRATCH_CERTIFIED"
                if hard_fixed and qualified
                else "NATIVE_MASK_WITHOUT_MATCHED_SOURCE_UUID"
                if hard_fixed else "PAIR_OR_SEARCH_RULE_NOT_FIXED_COPPER"
                if report["classification"] != "NATIVE_PRECHECK_CLEAR"
                else "NO_NATIVE_HARD_BLOCK_IN_THIS_DIRECTION")
            probes.append(report)
            if hard_fixed:
                for obj in qualified[:2]:
                    key = obj["uuid"]
                    if key not in blockers:
                        blockers[key] = {**obj, "occurrences": 0,
                                         "net_direction_examples": []}
                    blockers[key]["occurrences"] += 1
                    examples = blockers[key]["net_direction_examples"]
                    if len(examples) < 3:
                        examples.append({
                            "sample_role": state["sample_role"],
                            "route_net": report["net"],
                            "direction_index": report["heading_index"],
                        })
        annotated.append({
            "sample_role": state["sample_role"],
            "progress_from_third_bind_root_mm":
                state["progress_from_third_bind_root_mm"],
            "remaining_target_distance_sum_mm":
                state["remaining_target_distance_sum_mm"],
            "heads": state["heads"],
            "direction_probes": probes,
        })
    ranked = sorted(blockers.values(), key=lambda x: (
        -x["occurrences"], x["new_trace_copper_gap_mm"], x["uuid"]))
    return annotated, ranked[:30]


def _load_states(candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    worker = candidate.get("child_diagnostic") or {}
    if not candidate.get("source_unchanged") or candidate.get("new_vias_added") != 0:
        raise RuntimeError("Pinned source or via integrity not established")
    for flag in ("accepted", "routing_completed", "fabrication_release"):
        if candidate.get(flag) is not False or worker.get(flag) is not False:
            raise RuntimeError("Candidate is not a read-only no-release diagnostic")
    victims = set(worker.get("cut_whitelist_UUIDs", []))
    replaced = set(worker.get("CH038_cut_UUIDs", []))
    if len(victims) != 201 or len(replaced) != 2:
        raise RuntimeError("Missing exact scratch cut provenance")
    cbs = (worker.get("rubber_guided_CBS3_diagnostic")
           or worker.get("cbs_three_diagnostic") or {})
    hybrid = cbs.get("hybrid_corridor_diagnostic") or {}
    partial = hybrid.get("partial_free_diagnostic") or {}
    states = partial.get("three_net_choke_states", [])
    if partial and not states:
        raise RuntimeError("Partial-free search ran without top-state evidence")
    for state in states:
        heads = state.get("heads", [])
        probes = state.get("direction_probes", [])
        if [item.get("net") for item in heads] != list(NETS):
            raise RuntimeError("Three-net head identity/order mismatch")
        if len(probes) != 24:
            raise RuntimeError("Each snapshot must contain 3 x 8 native probes")
        if any(not item.get("route_grid") for item in heads):
            raise RuntimeError("Missing native trace history")
    return states, victims | replaced


def analyze(candidate_path: Path, archive_path: Path) -> dict[str, Any]:
    import pcbnew
    from probe_block2_isolated_s1s2 import pinned_source_copy
    from probe_block2_native_fcu_bottleneck import collect

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Require pinned KiCad 8.0.9")
    candidate = json.loads(candidate_path.read_text())
    states, removed_uuids = _load_states(candidate)
    coords = [
        point
        for state in states
        for head in state["heads"]
        for point in [head["xy_mm"]]
    ]
    for state in states:
        coords.extend(p["to_mm"] for p in state["direction_probes"])
    center = ((min(p[0] for p in coords) + max(p[0] for p in coords)) / 2.,
              (min(p[1] for p in coords) + max(p[1] for p in coords)) / 2.)
    half_span = max(
        max(abs(p[0]-center[0]) for p in coords),
        max(abs(p[1]-center[1]) for p in coords),
    ) + 1.0

    archive_hash_before = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="block2-choke-readonly-") as td:
        board_path = pinned_source_copy(archive_path, Path(td))
        pcb_hash_before = hashlib.sha256(board_path.read_bytes()).hexdigest()
        board = pcbnew.LoadBoard(str(board_path))
        all_fcu, warnings = collect(board, center, half_span, pcbnew)
        included = [o for o in all_fcu if o.uid not in removed_uuids]
        report_states, blocker_rows = correlate_states(
            states, included, removed_uuids)
        pcb_hash_after = hashlib.sha256(board_path.read_bytes()).hexdigest()
        if pcb_hash_before != pcb_hash_after:
            raise RuntimeError("Read-only UUID inspection mutated source")
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != archive_hash_before:
        raise RuntimeError("Pinned 139 archive mutated")

    classifications: dict[str, int] = {}
    for state in report_states:
        for probe in state["direction_probes"]:
            key = probe["classification"]
            classifications[key] = classifications.get(key, 0) + 1
    return {
        "schema": "block2_three_net_choke_uuid_readonly_v1",
        "status": "LOCAL_SCRATCH_MASK_AND_SOURCE139_UUID_WITNESS",
        "kicad_version": pcbnew.Version(),
        "reference_board_sha256": pcb_hash_before,
        "source_archive_sha256": archive_hash_before,
        "source_board_unchanged": True,
        "analysis_is_native_scratch_mask_with_original_uuid_reference": True,
        "uuid_attribution_not_equivalent_to_scratch_geometry_proof": True,
        "victim_uuids_removed_from_witness_model": 201,
        "replaced_CH038_uuids_excluded": 2,
        "native_local_unroutability_proven": False,
        "global_three_route_cut_proven": False,
        "roi_center_mm": [_round(v) for v in center],
        "roi_half_span_mm": _round(half_span),
        "trace_width_mm": TRACK_RADIUS_MM * 2,
        "copper_clearance_mm": COPPER_CLEARANCE_MM,
        "trace_centre_to_obstacle_surface_required_mm":
            CENTRE_TO_OBSTACLE_SURFACE_MM,
        "three_net_centreline_pitch_mm": CENTRELINE_PAIR_PITCH_MM,
        "reference_fcu_obstacles_examined": len(included),
        "unqualified_reference_geometry_warnings": warnings,
        "sample_count": len(report_states),
        "direction_classifications": dict(sorted(classifications.items())),
        "top_reference_fcu_uuid_witnesses": blocker_rows,
        "top_three_net_states": report_states,
        "layer_scope": "F.Cu only; In1.Cu and L3 are not new F.Cu blockers",
        "no_new_vias": True,
        "no_zone_fill_performed": True,
        "restoration_not_attempted": True,
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    result = analyze(args.candidate, args.archive)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("THREE_NET_CHOKE_SUMMARY=" + json.dumps({
        "status": result["status"],
        "sample_count": result["sample_count"],
        "direction_classifications": result["direction_classifications"],
        "uuid_candidates": result["top_reference_fcu_uuid_witnesses"][:8],
        "states": [
            {
                "role": state["sample_role"],
                "progress_mm": state["progress_from_third_bind_root_mm"],
                "heads": [
                    {k: h[k] for k in (
                        "net", "xy_mm", "heading_index", "heading_grid",
                        "edt_native_mask_mm")}
                    for h in state["heads"]
                ],
            } for state in result["top_three_net_states"]
        ],
        "global_three_route_cut_proven": False,
        "accepted": False, "routing_completed": False,
        "fabrication_release": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail-closed, NO-ROUTE F.Cu upper-bound screen for native Block2 N28/N29/N30.

Temporarily remove EVERY eligible Block2 F.Cu signal track from a throwaway
scratch PCB text (never a manufacturing output). If this geometry is divided,
any subset of the current whitelist is also divided (under the pinned
clearance/domain model). NO candidate PCB is saved and no manufacturing
output is generated. A positive topology result is NOT routing success:
restitution, native DRC, exact L3, schematic parity and replay still gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from native_connectivity import airwire_counts
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_ch025_fcu_l3_exact import power_fcu_obstacles, track_inventory
from probe_block2_deep_fcu_multinet import (
    LOCK, movable, native_open_positions,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from probe_real_mux_fcu_block2_ripup import same_free_component
from route_targeted_closure import metrics, native, routing_domain, xy

TARGETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
# Both polarities of these already-closed channels are kept intact.
PRESERVE_CHANNELS = ("CH022_", "CH025_", "CH027_")


def upperbound_movable(net: str) -> bool:
    return movable(net) and not net.startswith(PRESERVE_CHANNELS)


def strip_track_segments_by_uuid(text: str, uuids: set[str]) -> str:
    """Remove only exact top-level (segment ...) expressions, never vias/zones.

    A fresh KiCad parse avoids invalidated SWIG containers after hundreds
    of pcbnew.Board.Remove() calls. Fail closed on missing/duplicate UUIDs.
    """
    spans: list[tuple[int, int, str]] = []
    found: set[str] = set()
    for match in re.finditer(r"(?m)^[ \t]*\(segment\b", text):
        start = match.start()
        begin = text.index("(", start, match.end())
        depth = 0
        in_string = False
        escaped = False
        end = None
        for pos in range(begin, len(text)):
            char = text[pos]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    break
                if depth < 0:
                    raise RuntimeError("Invalid KiCad segment nesting")
        if end is None:
            raise RuntimeError("Unterminated KiCad segment")
        body = text[begin:end]
        uid = re.search(r'\(uuid\s+"([^"]+)"\)', body)
        if uid is None or uid.group(1) not in uuids:
            continue
        if uid.group(1) in found:
            raise RuntimeError("Duplicate track UUID in native PCB")
        found.add(uid.group(1))
        if end < len(text) and text[end] == "\n":
            end += 1
        spans.append((start, end, uid.group(1)))
    if found != uuids:
        raise RuntimeError("UUID-precise scratch removal mismatch: " +
                           repr(sorted(uuids - found)))
    for start, end, _ in reversed(spans):
        text = text[:start] + text[end:]
    return text


def run(candidate: Path, output: Path) -> dict:
    import pcbnew
    from shapely.geometry import box, LineString

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Native KiCad 8.0.9 required")
    source_digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    report = {
        **LOCK,
        "status": "started", "target_nets": list(TARGETS),
        "upperbound_only_not_routing_qualified": True,
        "saved_candidate_PCB": False, "native_candidate_DRC_pass": False,
        "all_eligible_FCu_removed": False,
        "source_unchanged": False, "immutable_tracks_unchanged": False,
        "protected_footprints_unchanged": False,
        "via_UUID_set_unchanged": False,
        "baseline_DRC": None, "all_movable_removed_topology": {},
        "immutable_near_airwire": [],
    }
    def persist(stage: str) -> None:
        report["last_completed_stage"] = stage
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")

    persist("source_archive_preflight")
    with tempfile.TemporaryDirectory(prefix="block2-fixed-cut-upperbound-") as work:
        root = Path(work)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}:
                raise RuntimeError("Unexpected 139 source archive content")
            meta = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if meta.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("Pinned original archive SHA drift")
            for flag in ("accepted", "routing_completed", "fabrication_release",
                         "routing_replay_byteidentical_verified"):
                if meta.get(flag) is not False:
                    raise RuntimeError("Original release flag not locked: " + flag)
            for member in MEMBERS:
                (root / member).write_bytes(z.read(member))
        pcb = root / MEMBERS[0]
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("Pinned MUX_EN candidate PCB SHA mismatch")
        baseline = native(pcb, root / "baseline.json")
        report["baseline_DRC"] = metrics(baseline)
        if report["baseline_DRC"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("Native baseline not 139/0/0")
        endpoints = native_open_positions(baseline)
        if any(airwire_counts(baseline).get(n, 0) != 1 for n in TARGETS):
            raise RuntimeError("Unexpected open target connectivity")
        board = pcbnew.LoadBoard(str(pcb))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        via_uuids = {
            item.m_Uuid.AsString() for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)}
        all_xy = [p for pair in endpoints.values() for p in pair]
        bbox = box(min(p[0] for p in all_xy) - 2.5,
                   min(p[1] for p in all_xy) - 2.5,
                   max(p[0] for p in all_xy) + 2.5,
                   max(p[1] for p in all_xy) + 2.5)
        region = routing_domain(board, .075, .25).intersection(bbox)
        if region.is_empty:
            raise RuntimeError("Empty routing domain")
        guard = power_fcu_obstacles(board)
        report["full_eight_net_bbox_mm"] = list(bbox.bounds)
        report["before_topology"] = {
            net: same_free_component(
                board, endpoints[net][0], endpoints[net][1],
                board.FindNet(net).GetNetCode(), region, guard)
            for net in TARGETS}
        native_lines = {
            net: LineString(endpoints[net]) for net in TARGETS}
        # SWIG GetNet() may become invalid after board.Remove(); pin net codes.
        target_codes = {
            net: board.FindNet(net).GetNetCode() for net in TARGETS}
        removed = []
        unmovable = []
        for item in list(board.GetTracks()):
            if isinstance(item, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)):
                continue
            if item.GetLayer() != pcbnew.F_Cu:
                continue
            segment = LineString((xy(item.GetStart()), xy(item.GetEnd())))
            if not segment.intersects(bbox):
                continue
            uid, net = item.m_Uuid.AsString(), item.GetNetname()
            if upperbound_movable(net):
                removed.append({"uuid": uid, "net": net})
                # Record only; original KiCad SWIG board is never mutated.
            else:
                distances = {
                    name: round(segment.distance(line), 6)
                    for name, line in native_lines.items()}
                unmovable.append({
                    "uuid": uid, "net": net, "distance_mm": distances,
                    "start_mm": list(xy(item.GetStart())),
                    "end_mm": list(xy(item.GetEnd()))})
        report["eligible_removed_count"] = len(removed)
        report["removed_UUIDs"] = [r["uuid"] for r in removed]
        report["all_eligible_FCu_removed"] = bool(removed)
        report["protected_channels"] = list(PRESERVE_CHANNELS)
        report["immutable_FCu_inventory_count"] = len(unmovable)
        report["immutable_near_airwire"] = sorted(
            [v for v in unmovable
             if v["net"] not in TARGETS
             and min(v["distance_mm"].values()) <= 2.5],
            key=lambda v: (min(v["distance_mm"].values()), v["net"],
                           v["uuid"]))
        # Parse a new scratch KiCad PCB, avoiding SWIG invalidation after
        # removing 201+ tracks from a live pcbnew BOARD instance.
        scratch = root / "fixed-cut-unqualified-scratch.kicad_pcb"
        original_pcb_text = pcb.read_text(encoding="utf-8")
        scratch.write_text(strip_track_segments_by_uuid(
            original_pcb_text, set(report["removed_UUIDs"])),
            encoding="utf-8")
        board = pcbnew.LoadBoard(str(scratch))
        if board is None:
            raise RuntimeError("Unable to reload scratch KiCad board")
        report["scratch_segment_removal_verified"] = (
            len(original) - len(track_inventory(board)) == len(removed))
        if not report["scratch_segment_removal_verified"]:
            raise RuntimeError("Scratch copper inventory mismatch")
        persist("all_whitelisted_FCu_tracks_temporarily_removed")
        report["all_movable_removed_topology"] = {
            net: same_free_component(
                board, endpoints[net][0], endpoints[net][1],
                target_codes[net], region, guard)
            for net in TARGETS}
        report["fixed_only_partitioned_targets"] = [
            net for net in TARGETS
            if not report["all_movable_removed_topology"][net]["same_component"]]
        report["immutable_tracks_unchanged"] = all(
            track_inventory(board).get(uid) == signature
            for uid, signature in original.items()
            if uid not in set(report["removed_UUIDs"]))
        report["protected_footprints_unchanged"] = (
            unchanged_fingerprints(board) == protected)
        report["via_UUID_set_unchanged"] = ({
            item.m_Uuid.AsString() for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)} == via_uuids)
        if not (report["all_eligible_FCu_removed"]
                and report["immutable_tracks_unchanged"]
                and report["protected_footprints_unchanged"]
                and report["via_UUID_set_unchanged"]):
            raise RuntimeError("Protected copper was changed in upperbound")
        # Discard scratch board with TemporaryDirectory; original SHA pinned.
        # This is deliberately NOT a qualified or retained candidate PCB.
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != PINNED_CANDIDATE_SHA:
            raise RuntimeError("Source PCB changed during upperbound")
        persist("fixed_copper_only_FCu_topology_recorded")
    report["source_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == source_digest)
    if not report["source_unchanged"]:
        raise RuntimeError("Source archive modified")
    report["status"] = "fixed_cut_upperbound_diagnostic_complete_no_release"
    persist("completed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    d = run(options.candidate, options.output)
    print(json.dumps({
        "status": d["status"],
        "fixed_only_partitioned_targets": d["fixed_only_partitioned_targets"],
        "all_allowed_removed": d["eligible_removed_count"],
        "accepted": False, "fabrication_release": False,
    }))


if __name__ == "__main__":
    main()

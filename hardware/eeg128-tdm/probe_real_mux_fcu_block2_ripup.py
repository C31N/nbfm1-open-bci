#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Native real Block2 F.Cu ripup trials, protected-copper rollback only.

Eight real missing MUX connections have ZERO same-net through-vias. New
vias are prohibited, so search selectively for legal F.Cu component cuts.
Only reviewed Block2 signal TRACK UUIDs may be removed, temporarily.
Each removed signal MUST reconnect (or its original copper must be
restituted), with native KiCad 8.0.9 0/0 DRC, 138 connected airwires,
exact 3V3A, unchanged In1 and zero regressions before a trial qualifies.
Never promote a 139->138 single-net candidate to accepted 136.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
import zipfile

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, MEMBERS
from analyze_ch025_l3_precision_mask import exact_native_difference
from escape_mesh_505 import polygons
from native_connectivity import airwire_counts, regressed_nets
from probe_ch025_cooperative8 import unchanged_fingerprints
from probe_ch025_fcu_l3_exact import (
    ZONE, track_inventory, power_fcu_obstacles,
)
from probe_ch025_neutral_via_sites import (
    every_zero, polygon_delta, polygon_snapshot,
)
from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
from route_targeted_closure import (
    add_path, metrics, native, obstacles, routing_domain, search, xy,
)
NETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
IMMUTABLE_NETS = frozenset({
    "VCM", "AGND", "3V3A", "MUX_EN",
    "CH022_N_ELECTRODE", "CH025_N_MUX", "CH027_N_MUX",
})
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "In1_Cu_used": False,
    "new_vias_added": 0,
}
def movable(net: str) -> bool:
    return (
        bool(re.fullmatch(r"CH0(?:1[6-9]|2[0-9]|3[01])_[NP]_MUX", net))
        or net in ("MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3")
    ) and net not in IMMUTABLE_NETS

def same_free_component(
        board: Any, source: tuple[float,float],
        target: tuple[float,float], code: int,
        region: Any, guard: Any) -> dict[str, Any]:
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    import pcbnew
    walls, _ = obstacles(board, code, .15, .15, region, .65,
                         (pcbnew.F_Cu, pcbnew.B_Cu))
    shapes = polygons(region.difference(unary_union([
        walls[0], guard])).buffer(-.000005))
    tree = STRtree(shapes)
    def idx(pos: tuple[float,float]) -> int | None:
        point = Point(pos)
        return next((int(i) for i in tree.query(point)
                     if shapes[int(i)].covers(point)), None)
    left, right = idx(source), idx(target)
    return {
        "component_count": len(shapes),
        "source_component": left, "target_component": right,
        "same_component": left is not None and left == right,
    }

def run(candidate: Path, net: str, output: Path) -> dict[str, Any]:
    import pcbnew
    from shapely.geometry import LineString, box

    if net not in NETS:
        raise ValueError("Not a verified open native Block2 net")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Expected KiCad 8.0.9")
    report: dict[str, Any] = {
        **NO_RELEASE, "status": "not_started", "net": net,
        "native_baseline": None, "victim_inventory": [],
        "ripup_trials": [], "any_qualified_single_airwire": False,
        "all_originals_restituted": False,
        "native_In1_exact": False, "native_L3_exact": False,
        "input_archive_unchanged": False,
    }
    def write(stage: str) -> None:
        report["last_stage"] = stage
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")

    input_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    write("native_preflight")
    with tempfile.TemporaryDirectory(prefix="real-block2-micro-fcu-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(candidate) as z:
            if set(z.namelist()) != (
                    set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}):
                raise RuntimeError("Unexpected source ZIP layout")
            metadata = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if metadata.get("source_archive_sha256") != ARCHIVE_SHA256:
                raise RuntimeError("139 engineering source SHA mismatch")
            for key in ("accepted", "routing_completed",
                        "fabrication_release",
                        "routing_replay_byteidentical_verified"):
                if metadata.get(key) is not False:
                    raise RuntimeError("Invalid source acceptance metadata")
            for member in MEMBERS:
                (root / member).write_bytes(z.read(member))
        pcb = root / MEMBERS[0]
        if hashlib.sha256(pcb.read_bytes()).hexdigest() != (
                PINNED_CANDIDATE_SHA):
            raise RuntimeError("Pinned MUX_EN PCB SHA mismatch")
        baseline = native(pcb, root / "baseline.json")
        report["native_baseline"] = metrics(baseline)
        if report["native_baseline"] != {
                "violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("Source baseline no longer 139/0/0")
        if airwire_counts(baseline).get(net, 0) != 1:
            raise RuntimeError("Target net not a single open native airwire")
        rows = [row for row in baseline["unconnected_items"]
                if any("[" + net + "]" in i.get("description", "")
                       for i in row.get("items", []))]
        if len(rows) != 1 or len(rows[0]["items"]) != 2:
            raise RuntimeError("Unreviewed native endpoint layout")
        anchors = [(
            float(x["pos"]["x"]), float(x["pos"]["y"]))
            for x in rows[0]["items"]]
        board = pcbnew.LoadBoard(str(pcb))
        original = track_inventory(board)
        protected = unchanged_fingerprints(board)
        original_vias = {x.m_Uuid.AsString() for x in board.GetTracks()
                         if isinstance(x, pcbnew.PCB_VIA)}
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        zone = next((z for z in board.Zones()
                     if z.m_Uuid.AsString() == ZONE
                     and z.GetNetname() == "3V3A"
                     and z.IsOnLayer(pcbnew.In2_Cu)), None)
        if zone is None:
            raise RuntimeError("Original protected 3V3A zone missing")
        baseline_L3 = pcbnew.SHAPE_POLY_SET(
            zone.GetFilledPolysList(pcbnew.In2_Cu))
        baseline_In1 = polygon_snapshot(board, pcbnew.In1_Cu)
        code = board.FindNet(net).GetNetCode()
        region = routing_domain(board, .075, .25).intersection(box(
            min(x[0] for x in anchors) - 3.5,
            min(x[1] for x in anchors) - 3.5,
            max(x[0] for x in anchors) + 3.5,
            max(x[1] for x in anchors) + 3.5))
        guard = power_fcu_obstacles(board)
        direct = LineString(anchors)
        source_tracks = {item.m_Uuid.AsString(): item
                         for item in board.GetTracks()}
        victims: list[tuple[float, str]] = []
        for uid, track in source_tracks.items():
            if (isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
                    or track.GetLayer() != pcbnew.F_Cu
                    or not movable(track.GetNetname())
                    or track.GetNetname() == net):
                continue
            segment = LineString((
                xy(track.GetStart()), xy(track.GetEnd())))
            dist = float(direct.distance(segment))
            # A local 0.65-mm swath of the missing wire is searched first;
            # the exact UUID still needs to pass restitution and DRC.
            if dist <= .65 and segment.intersects(region):
                victims.append((dist, uid))
        victims.sort(key=lambda x: (x[0], x[1]))
        report["victim_inventory"] = [
            {"uuid": uid, "net": source_tracks[uid].GetNetname(),
             "distance_to_airwire_mm": round(dist, 9),
             "layer": "F.Cu", "eligible_only_if_100pct_restituted": True}
            for dist, uid in victims[:25]]
        selection = [uid for _, uid in victims[:4]]
        combinations = [(uid,) for uid in selection]
        combinations += list(itertools.combinations(selection, 2))[:6]
        # The first trial cohort proved 30 singleton/pair cuts cannot
        # open FCu. Four S-bus obstacles cross all three native MUX
        # airwires. Trial triples/quadruple ONLY on the exact reviewed
        # UUID of each Block2 S0/S1/S2/S3 track, then fully rollback.
        bus = {
            name: next((uid for _, uid in victims
                        if source_tracks[uid].GetNetname() == name), None)
            for name in ("MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3")
        }
        report["cooperative_bus_quads"] = bus
        for group in (
                ("MUX_S0", "MUX_S1", "MUX_S2"),
                ("MUX_S0", "MUX_S1", "MUX_S3"),
                ("MUX_S0", "MUX_S2", "MUX_S3"),
                ("MUX_S1", "MUX_S2", "MUX_S3"),
                ("MUX_S0", "MUX_S1", "MUX_S2", "MUX_S3")):
            if all(bus[name] is not None for name in group):
                combinations.append(tuple(bus[name] for name in group))
        # On CH028/29 there are two nearby MUX_S2 tracks. Their own
        # cooperative four-S cuts are distinct and worth checking.
        s2_alternates = [
            uid for _, uid in victims
            if source_tracks[uid].GetNetname() == "MUX_S2"]
        if (len(s2_alternates) >= 2
                and all(bus[name] is not None for name in (
                    "MUX_S0", "MUX_S1", "MUX_S3"))):
            combinations.append((
                bus["MUX_S0"], bus["MUX_S1"],
                s2_alternates[1], bus["MUX_S3"]))
        combinations = list(dict.fromkeys(combinations))
        report["selected_trial_count"] = len(combinations)
        report["source_net_existing_vias"] = [
            item.m_Uuid.AsString() for item in board.GetTracks()
            if isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetname() == net]
        if report["source_net_existing_vias"]:
            raise RuntimeError("Unexpected via on known zero-via target")
        report["base_FCu_topology"] = same_free_component(
            board, anchors[0], anchors[1], code, region, guard)
        write("original_Block2_victim_UUID_inventory")
        for n, subset in enumerate(combinations):
            row: dict[str, Any] = {
                "case": n, "victim_UUIDs": list(subset),
                "victim_nets": [
                    source_tracks[uid].GetNetname() for uid in subset],
                "originals_restituted": False,
                "candidate_native_DRC_pass": False,
                "all_victim_nets_reconnected": False,
                "new_via_count": 0, "no_new_vias": True,
                "In1_Cu_modified": False,
                "L3_exact_loss_gain_zero": False,
                "accepted": False, "fabrication_release": False,
            }
            report["ripup_trials"].append(row)
            for uid in subset:
                board.Remove(source_tracks[uid])
            before_new = {t.m_Uuid.AsString() for t in board.GetTracks()}
            try:
                report["active_trial_index"] = n
                write("selected_original_Block2_copper_removed")
                row["FCu_topology"] = same_free_component(
                    board, anchors[0], anchors[1], code, region, guard)
                write("selected_FCu_component_screen_complete")
                if row["FCu_topology"]["same_component"]:
                    proposal = search(
                        board, anchors[0], anchors[1], code,
                        .15, .15, False, 4.0, step=.20,
                        max_nodes=35000, deadline=time.monotonic()+25,
                        start_layer=0, goal_layer=0,
                        layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                    row["target_proposal_found"] = (
                        proposal is not None and len(proposal) >= 2
                        and all(point[0] == 0 for point in proposal))
                    if row["target_proposal_found"]:
                        add_path(board, proposal, code, .15,
                                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        success = True
                        for uid in subset:
                            victim = source_tracks[uid]
                            victim_code = victim.GetNetCode()
                            attempt = search(
                                board, xy(victim.GetStart()),
                                xy(victim.GetEnd()), victim_code,
                                .15, .15, False, 2.5, step=.18,
                                max_nodes=25000,
                                deadline=time.monotonic()+15,
                                start_layer=0, goal_layer=0,
                                layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                            if (attempt is None or len(attempt) < 2
                                    or any(p[0] != 0 for p in attempt)):
                                success = False
                                row["victim_restitution_failed_UUID"] = uid
                                break
                            add_path(board, attempt, victim_code, .15,
                                     layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                        row["all_victim_nets_reconnected"] = success
                        write("native_Block2_victim_restitution_screen")
                        if success:
                            if any(
                                    track_inventory(board).get(uid) != val
                                    for uid, val in original.items()
                                    if uid not in subset):
                                raise RuntimeError(
                                    "Unselected original track changed")
                            if unchanged_fingerprints(board) != protected:
                                raise RuntimeError(
                                    "Protected via/pad/zone changed")
                            if {item.m_Uuid.AsString()
                                for item in board.GetTracks()
                                if isinstance(item, pcbnew.PCB_VIA)
                                } != original_vias:
                                raise RuntimeError("New via prohibited")
                            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                            delta = exact_native_difference(
                                baseline_L3,
                                pcbnew.SHAPE_POLY_SET(
                                    zone.GetFilledPolysList(pcbnew.In2_Cu)))
                            row["L3_exact_loss_gain_zero"] = (
                                delta["native_both_empty"])
                            row["L3_loss_mm2"] = delta["loss_native_mm2"]
                            row["L3_gain_mm2"] = delta["gain_native_mm2"]
                            row["In1_Cu_modified"] = not every_zero(
                                polygon_delta(
                                    baseline_In1,
                                    polygon_snapshot(board, pcbnew.In1_Cu)))
                            if (row["L3_exact_loss_gain_zero"]
                                    and not row["In1_Cu_modified"]):
                                scratch_dir = root / f"scratch-{n}"
                                scratch_dir.mkdir()
                                for name in MEMBERS[1:]:
                                    shutil.copyfile(root / name,
                                                    scratch_dir / name)
                                scratch = scratch_dir / MEMBERS[0]
                                pcbnew.SaveBoard(str(scratch), board)
                                post = native(
                                    scratch, root / f"post-{n}.json")
                                row["native_post_DRC"] = metrics(post)
                                row["native_target_open"] = (
                                    airwire_counts(post).get(net, 0))
                                row["regressed_nets"] = regressed_nets(
                                    baseline, post)
                                row["candidate_native_DRC_pass"] = (
                                    row["native_post_DRC"] ==
                                    {"violations": 0, "warnings": 0,
                                     "unconnected": 138}
                                    and row["native_target_open"] == 0
                                    and not row["regressed_nets"])
                                write("native_post_route_DRC_examined")
                                report["any_qualified_single_airwire"] |= (
                                    row["candidate_native_DRC_pass"])
            finally:
                for item in list(board.GetTracks()):
                    if item.m_Uuid.AsString() not in before_new:
                        board.Remove(item)
                for uid in subset:
                    board.Add(source_tracks[uid])
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                row["originals_restituted"] = (
                    track_inventory(board) == original
                    and unchanged_fingerprints(board) == protected)
                row["rollback_L3_exact"] = exact_native_difference(
                    baseline_L3,
                    pcbnew.SHAPE_POLY_SET(
                        zone.GetFilledPolysList(pcbnew.In2_Cu))
                )["native_both_empty"]
                row["rollback_In1_exact"] = every_zero(polygon_delta(
                    baseline_In1,
                    polygon_snapshot(board, pcbnew.In1_Cu)))
                if not (row["originals_restituted"]
                        and row["rollback_L3_exact"]
                        and row["rollback_In1_exact"]):
                    raise RuntimeError("Original copper/zone rollback failed")
                write("all_originals_restored_after_trial")
        report["all_originals_restituted"] = (
            track_inventory(board) == original
            and unchanged_fingerprints(board) == protected)
        report["native_In1_exact"] = every_zero(polygon_delta(
            baseline_In1, polygon_snapshot(board, pcbnew.In1_Cu)))
        report["native_L3_exact"] = exact_native_difference(
            baseline_L3, pcbnew.SHAPE_POLY_SET(
                zone.GetFilledPolysList(pcbnew.In2_Cu)))["native_both_empty"]
        if not (report["all_originals_restituted"]
                and report["native_In1_exact"] and report["native_L3_exact"]):
            raise RuntimeError("Final native protected rollback failed")
        report["status"] = (
            "isolated_FCu_ripup_138_candidate_no_release"
            if report["any_qualified_single_airwire"]
            else "micro_ripup_explored_no_qualified_native_candidate")
    report["input_archive_unchanged"] = (
        hashlib.sha256(candidate.read_bytes()).hexdigest() == input_hash)
    write("complete")
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--net", choices=NETS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = run(args.candidate, args.net, args.output)
    print(json.dumps({
        "net": data["net"], "status": data["status"],
        "trials": len(data["ripup_trials"]),
        "candidate_138_qualified": data["any_qualified_single_airwire"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

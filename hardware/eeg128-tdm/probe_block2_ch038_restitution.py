#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Isolated CH038_P_MUX F.Cu-only restitution prerequisite, NO RELEASE.

Only the two UUID-verified CH038 segments may be displaced. Other original
copper is immutable. Search is in one disposable KiCad child; native DRC
on its scratch PCB is performed in a DIFFERENT subprocess. Even a green
139/0/0 result never qualifies CH028/29/30 or fabrication. No new vias.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from probe_block2_isolated_s1s2 import (
    EXPECTED_BASELINE, pinned_source_copy, sha,
)
from probe_block2_fcu_fixed_cut_upperbound import (
    CH038_EXPLORATORY_UUIDS, strip_track_segments_by_uuid,
)

EXPECTED_UUIDS = tuple(sorted(CH038_EXPLORATORY_UUIDS))
NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "new_vias_added": 0,
}

def isolated_drc(board: Path, report: Path) -> dict:
    """Use one fresh KiCad process for each DRC; no shared C++ objects."""
    command = (
        "import sys,json;"
        "from pathlib import Path;"
        "sys.path.insert(0,sys.argv[1]);"
        "from route_targeted_closure import native,metrics;"
        "print(json.dumps(metrics(native(Path(sys.argv[2]),Path(sys.argv[3])))))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", command,
         str(Path(__file__).resolve().parent), str(board), str(report)],
        capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0:
        raise RuntimeError("Isolated DRC process failed: " + proc.stderr[-1100:])
    return json.loads(proc.stdout.strip().splitlines()[-1])

def route_child(source: Path, native_baseline: Path, output: Path) -> dict:
    import pcbnew
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from probe_block2_deep_fcu_multinet import native_open_positions
    from probe_ch025_cooperative8 import unchanged_fingerprints
    from probe_ch025_fcu_l3_exact import track_inventory
    from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
    from route_targeted_closure import add_path, search, xy

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    if sha(source) != PINNED_CANDIDATE_SHA:
        raise RuntimeError("Original 139 MUX_EN PCB SHA changed")
    original = pcbnew.LoadBoard(str(source))
    initial_tracks = track_inventory(original)
    protected = unchanged_fingerprints(original)
    initial_vias = {
        t.m_Uuid.AsString() for t in original.GetTracks()
        if isinstance(t, pcbnew.PCB_VIA)
    }
    tracks = {t.m_Uuid.AsString(): t for t in original.GetTracks()}
    if any(uid not in tracks for uid in EXPECTED_UUIDS):
        raise RuntimeError("Missing UUID-precise CH038 source tracks")
    selected = [tracks[uid] for uid in EXPECTED_UUIDS]
    if any(t.GetNetname() != "CH038_P_MUX"
           or t.GetLayer() != pcbnew.F_Cu
           or isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
           for t in selected):
        raise RuntimeError("CH038 F.Cu UUID/net/layer mismatch")

    positions = native_open_positions(json.loads(native_baseline.read_text()))
    from probe_block2_fcu_fixed_cut_upperbound import TARGETS
    cost = unary_union([
        LineString(positions[n]).buffer(.34) for n in TARGETS
    ])
    # Retain all 201 otherwise movable nets in this prerequisite trial.
    # Only CH038 is displaced; a successful 139/0/0 replacement is a
    # necessary but NOT sufficient condition for simultaneous target routing.
    candidate_dir = source.parent / "CH038_PROBE_ONLY"
    candidate_dir.mkdir(exist_ok=False)
    candidate = candidate_dir / source.name
    candidate.write_text(strip_track_segments_by_uuid(
        source.read_text(encoding="utf-8"), set(EXPECTED_UUIDS)),
        encoding="utf-8")
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copyfile(source.with_suffix(ext), candidate.with_suffix(ext))
    probe = pcbnew.LoadBoard(str(candidate))
    if probe is None:
        raise RuntimeError("Cannot load isolated CH038 scratch PCB")
    if any(t.m_Uuid.AsString() in EXPECTED_UUIDS
           for t in probe.GetTracks()):
        raise RuntimeError("Original CH038 tracks were not removed")
    code = probe.FindNet("CH038_P_MUX").GetNetCode()
    report = {
        **NO_RELEASE,
        "status": "CH038_restitution_search_started",
        "only_CH038_two_UUIDs_removed": list(EXPECTED_UUIDS),
        "other_201_original_tracks_preserved": True,
        "scratch_candidate_saved": False,
        "ch038_both_replacements_found": False,
        "target_airwire_lane_penalty": 40.0,
        "attempts": [],
    }
    def persist() -> None:
        output.write_text(json.dumps(report, indent=2) + "\n")
    persist()
    for source_track in selected:
        uid = source_track.m_Uuid.AsString()
        start, end = xy(source_track.GetStart()), xy(source_track.GetEnd())
        found = None
        for step, limit, seconds in ((.22, 30000, 17), (.16, 57000, 24)):
            t0 = time.monotonic()
            path = search(
                probe, start, end, code, .15, .15, False, 7.0,
                step=step, max_nodes=limit,
                deadline=t0 + seconds,
                start_layer=0, goal_layer=0,
                layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                cost_regions=((0, cost, 40.0),))
            report["attempts"].append({
                "uuid": uid, "step_mm": step,
                "path_found": bool(path),
                "duration_seconds": round(time.monotonic()-t0, 2),
            })
            persist()
            if path is not None and len(path) >= 2 and all(n[0] == 0 for n in path):
                found = path
                break
        if found is None:
            report["status"] = "CH038_no_verified_FCu_return_for_" + uid
            persist()
            return report
        add_path(probe, found, code, .15,
                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
        report["attempts"][-1]["added_to_disposable_copper"] = True
        persist()

    # A SWIG inventory check is a preliminary condition, NEVER DRC proof.
    new_inventory = track_inventory(probe)
    expected_remaining = {
        uid: signature for uid, signature in initial_tracks.items()
        if uid not in EXPECTED_UUIDS
    }
    if any(new_inventory.get(uid) != signature
           for uid, signature in expected_remaining.items()):
        raise RuntimeError("Other original net copper mutated")
    if unchanged_fingerprints(probe) != protected:
        raise RuntimeError("Protected footprint or zone modified")
    if ({t.m_Uuid.AsString() for t in probe.GetTracks()
         if isinstance(t, pcbnew.PCB_VIA)} != initial_vias):
        raise RuntimeError("New or displaced via in CH038 prerequisite")
    if any(t.GetLayer() != pcbnew.F_Cu
           for t in probe.GetTracks()
           if t.m_Uuid.AsString() not in initial_tracks):
        raise RuntimeError("New CH038 trace left F.Cu")
    pcbnew.SaveBoard(str(candidate), probe)
    report["ch038_both_replacements_found"] = True
    report["scratch_candidate_saved"] = True
    report["status"] = "CH038_two_FCu_replacements_pending_separate_native_DRC"
    persist()
    return report

def run(candidate: Path, output: Path) -> dict:
    source_sha = sha(candidate)
    result = {
        **NO_RELEASE,
        "status": "CH038_native_prerequisite_not_qualified",
        "baseline_DRC": None, "candidate_DRC": None,
        "ch038_restitution_DRC_qualified": False,
        "three_target_136_qualified": False,
        "source_archive_unchanged": False,
        "child_exit_code": None, "worker": None,
    }
    def persist() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
    persist()
    with tempfile.TemporaryDirectory(prefix="CH038-rest-before-targets-") as work:
        root = Path(work)
        original = pinned_source_copy(candidate, root)
        original_native = root / "native-source.json"
        result["baseline_DRC"] = isolated_drc(original, original_native)
        if result["baseline_DRC"] != EXPECTED_BASELINE:
            raise RuntimeError("Original 139/0/0 baseline failed")
        subreport = root / "CH038-subprocess.json"
        child = subprocess.run([
            sys.executable, str(Path(__file__).resolve()),
            "--child", "--source", str(original),
            "--native-baseline", str(original_native),
            "--output", str(subreport),
        ], capture_output=True, text=True, timeout=210, check=False)
        result["child_exit_code"] = child.returncode
        result["child_stderr_tail"] = child.stderr[-1800:]
        if subreport.exists():
            result["worker"] = json.loads(subreport.read_text())
        persist()
        scratch = root / "CH038_PROBE_ONLY" / original.name
        if (child.returncode == 0 and result["worker"]
                and result["worker"]["ch038_both_replacements_found"]
                and scratch.exists()):
            result["candidate_DRC"] = isolated_drc(
                scratch, root / "CH038-candidate-native.json")
            result["ch038_restitution_DRC_qualified"] = (
                result["candidate_DRC"] == EXPECTED_BASELINE)
        result["source_archive_unchanged"] = sha(candidate) == source_sha
        result["status"] = (
            "CH038_isolated_139_DRC_qualified_not_136"
            if result["ch038_restitution_DRC_qualified"]
            and result["source_archive_unchanged"]
            else "CH038_isolated_restitution_not_DRC_qualified")
        persist()
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--native-baseline", type=Path)
    a = parser.parse_args()
    if a.child:
        if not a.source or not a.native_baseline or a.candidate:
            raise ValueError("Child requires --source and --native-baseline")
        report = route_child(a.source, a.native_baseline, a.output)
    else:
        if not a.candidate or a.source or a.native_baseline:
            raise ValueError("Parent requires only --candidate")
        report = run(a.candidate, a.output)
    print(json.dumps({
        "status": report["status"],
        "accepted": False, "fabrication_release": False,
    }))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""True joint-state F.Cu A* for CH018_P_MUX and MUX_S1 (NO RELEASE).

One A* queue owns the two moving heads AND both committed partial paths.
Every expansion considers the other net's occupied edges before accepting
a state. S2/S3 and all unrelated original copper remain in place. Isolated
child and independent native KiCad 8.0.9 DRC have no SWIG pointer sharing.
No checkpoints or manufacturing files are ever produced.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NO_RELEASE = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "checkpoint_promoted": False, "schematic_parity_qualified": False,
    "independent_replay_verified": False, "new_vias_added": 0,
}
S1_UUID = "2ac3aecb-9a62-4bc7-846a-75a782ad0474"
TARGET = "CH018_P_MUX"
BASELINE = {"violations": 0, "warnings": 0, "unconnected": 139}
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1),
         (1, 1), (-1, 1), (1, -1), (-1, -1))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def joint_fcu_astar(board, endpoints, nets, *, step: float = .30,
                    max_states: int = 16000, seconds: float = 95.0):
    """Paired-head A*: state stores BOTH accumulated copper paths.

    Unlike sequential A*, the other path is unknown until expanded, and
    simultaneous search backtracks BOTH nets upon a collision. The state
    includes both complete partial paths, not only the current head pair.
    Native DRC must independently verify returned continuous geometry.
    """
    import pcbnew
    import numpy as np
    from shapely.geometry import LineString, box
    from shapely import contains_xy, prepare
    from route_targeted_closure import obstacles, xy

    if not .18 <= step <= .45 or max_states > 50000:
        raise ValueError("Joint-grid budget outside reviewed bounds")
    start_at = time.monotonic()
    e = [p for pair in endpoints for p in pair]
    bounds = board.GetBoardEdgesBoundingBox()
    x0 = max(min(p[0] for p in e)-3,
             pcbnew.ToMM(bounds.GetX())+.555)
    x1 = min(max(p[0] for p in e)+3,
             pcbnew.ToMM(bounds.GetRight())-.555)
    y0 = max(min(p[1] for p in e)-3,
             pcbnew.ToMM(bounds.GetY())+.555)
    y1 = min(max(p[1] for p in e)+3,
             pcbnew.ToMM(bounds.GetBottom())-.555)
    xs, ys = np.arange(x0, x1+step/2, step), np.arange(y0, y1+step/2, step)
    if len(xs) < 3 or len(ys) < 3:
        return None, {"status": "empty_joint_grid"}
    xx, yy = np.meshgrid(xs, ys)
    window = box(x0, y0, x1, y1)
    forbidden = []
    forbidden_shapes = []
    for net in nets:
        obstacles_by_layer, _ = obstacles(
            board, net, .15, .15, window, .65,
            (pcbnew.F_Cu, pcbnew.B_Cu))
        shape = obstacles_by_layer[0].buffer(-1e-9)
        prepare(shape)
        forbidden_shapes.append(shape)
        forbidden.append(contains_xy(shape, xx, yy))
    def coord(n):
        return (float(xs[n[0]]), float(ys[n[1]]))
    def segment_hit(shape, a, b):
        return LineString((a, b)).relate_pattern(shape, "T********")
    def anchor(which, point):
        mask = forbidden[which]
        near = sorted(
            ((x, y) for x in range(max(0, int(round((point[0]-x0)/step))-3),
                                   min(len(xs), int(round((point[0]-x0)/step))+4))
             for y in range(max(0, int(round((point[1]-y0)/step))-3),
                            min(len(ys), int(round((point[1]-y0)/step))+4))
             if not mask[y, x]),
            key=lambda n: math.dist(coord(n), point))
        for n in near:
            if not segment_hit(forbidden_shapes[which], point, coord(n)):
                return n
        return None
    starts = [anchor(i, pair[0]) for i, pair in enumerate(endpoints)]
    goals = [anchor(i, pair[1]) for i, pair in enumerate(endpoints)]
    if any(v is None for v in starts+goals):
        return None, {"status": "joint_start_or_goal_escape_blocked",
                      "starts": starts, "goals": goals}
    # The two routes have different nets and require at least 0.30 mm
    # centreline separation (0.15 trace + 0.15 native clearance).
    min_distance = .301
    def collides(move_a, move_b, other_path):
        new_line = LineString((move_a, move_b))
        if len(other_path) == 1:
            return new_line.distance(
                LineString((coord(other_path[0]),
                            coord(other_path[0])))) < min_distance
        return any(new_line.distance(LineString(
            (coord(p), coord(q)))) < min_distance
            for p, q in zip(other_path, other_path[1:]))
    def h(a, b):
        return (math.dist(coord(a), coord(goals[0])) +
                math.dist(coord(b), coord(goals[1])))
    seq = itertools.count()
    a0, b0 = starts
    initial = (a0, b0, 0, (a0,), (b0,))
    queue = [(h(a0, b0), next(seq), 0.0, initial)]
    visited = set()
    expanded = 0
    while queue and expanded < max_states:
        if time.monotonic()-start_at >= seconds:
            break
        _, _, spent, (a, b, turn, path_a, path_b) = heapq.heappop(queue)
        if (path_a, path_b, turn) in visited:
            continue
        visited.add((path_a, path_b, turn))
        expanded += 1
        if a == goals[0] and b == goals[1]:
            return [
                [(0, *endpoints[0][0])] +
                [(0, *coord(p)) for p in path_a] +
                [(0, *endpoints[0][1])],
                [(0, *endpoints[1][0])] +
                [(0, *coord(p)) for p in path_b] +
                [(0, *endpoints[1][1])],
            ], {"status": "joint_path_found_unverified",
                 "expanded_joint_states": expanded,
                 "grid_shape": [len(xs), len(ys)],
                 "step_mm": step, "wall_s": round(time.monotonic()-start_at, 2)}
        which = turn
        if (which == 0 and a == goals[0]) or (which == 1 and b == goals[1]):
            which = 1-which
        head = a if which == 0 else b
        mask = forbidden[which]
        other_path = path_b if which == 0 else path_a
        own_path = path_a if which == 0 else path_b
        for dx, dy in MOVES:
            nxt = (head[0]+dx, head[1]+dy)
            x, y = nxt
            if not (0 <= x < len(xs) and 0 <= y < len(ys)):
                continue
            if mask[y, x] or nxt in own_path:
                continue
            if dx and dy and (mask[head[1], x] or mask[y, head[0]]):
                continue
            if collides(coord(head), coord(nxt), other_path):
                continue
            if which == 0:
                a1, b1 = nxt, b
                p1, p2 = path_a+(nxt,), path_b
            else:
                a1, b1 = a, nxt
                p1, p2 = path_a, path_b+(nxt,)
            next_turn = 1-which
            step_cost = step*math.hypot(dx, dy)
            g = spent+step_cost
            heapq.heappush(queue, (g+h(a1, b1), next(seq), g,
                                   (a1, b1, next_turn, p1, p2)))
    return None, {
        "status": "joint_state_budget_exhausted_no_solution_proven",
        "expanded_joint_states": expanded,
        "grid_shape": [len(xs), len(ys)],
        "step_mm": step, "wall_s": round(time.monotonic()-start_at, 2),
    }


def child(source: Path, baseline: Path, output: Path) -> dict:
    import pcbnew
    from probe_block2_deep_fcu_multinet import native_open_positions
    from probe_block2_fcu_fixed_cut_upperbound import strip_track_segments_by_uuid
    from probe_ch025_cooperative8 import unchanged_fingerprints
    from probe_ch025_fcu_l3_exact import track_inventory
    from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
    from route_targeted_closure import add_path, xy

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("KiCad 8.0.9 required")
    if file_sha(source) != PINNED_CANDIDATE_SHA:
        raise RuntimeError("Source 139 MUX_EN SHA changed")
    original = pcbnew.LoadBoard(str(source))
    tracks = {tr.m_Uuid.AsString(): tr for tr in original.GetTracks()}
    victim = tracks.get(S1_UUID)
    if (victim is None or victim.GetNetname() != "MUX_S1"
            or victim.GetLayer() != pcbnew.F_Cu
            or isinstance(victim, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
        raise RuntimeError("Pinned S1 UUID/net/FCu mismatch")
    original_tracks = track_inventory(original)
    fp = unchanged_fingerprints(original)
    vias = {tr.m_Uuid.AsString() for tr in original.GetTracks()
            if isinstance(tr, pcbnew.PCB_VIA)}
    native_report = json.loads(baseline.read_text())
    if native_report.get("unconnected_items") is None:
        raise RuntimeError("Native baseline missing connectivity")
    endpoints = native_open_positions(native_report)[TARGET]
    s1_ends = (xy(victim.GetStart()), xy(victim.GetEnd()))
    scratchdir = source.parent / "joint_CH018_MUXS1_diagnostic"
    scratchdir.mkdir()
    boardfile = scratchdir / source.name
    boardfile.write_text(strip_track_segments_by_uuid(
        source.read_text(encoding="utf-8"), {S1_UUID}),
        encoding="utf-8")
    for suffix in (".kicad_pro", ".kicad_dru"):
        boardfile.with_suffix(suffix).write_bytes(
            source.with_suffix(suffix).read_bytes())
    board = pcbnew.LoadBoard(str(boardfile))
    if unchanged_fingerprints(board) != fp:
        raise RuntimeError("Protected copper drifted")
    if ({tr.m_Uuid.AsString() for tr in board.GetTracks()
         if isinstance(tr, pcbnew.PCB_VIA)} != vias):
        raise RuntimeError("Protected vias drifted")
    if any(track_inventory(board).get(uid) != value
           for uid, value in original_tracks.items() if uid != S1_UUID):
        raise RuntimeError("Original copper changed beyond one S1 UUID")
    out = {
        **NO_RELEASE, "status": "joint_search_started",
        "S1_removed_UUID": S1_UUID,
        "S2_S3_original_copper_immutable": True,
        "target_net": TARGET,
        "candidate_native_DRC": None,
        "joint_search": None,
        "joint_138_DRC_qualified": False,
        "source_unchanged": False,
    }
    def persist(stage: str):
        out["last_stage"] = stage
        output.write_text(json.dumps(out, indent=2)+"\n")
    persist("all_other_copper_verified")
    target_code = board.FindNet(TARGET).GetNetCode()
    victim_code = board.FindNet("MUX_S1").GetNetCode()
    path_pair, diag = joint_fcu_astar(
        board, (endpoints, s1_ends),
        (target_code, victim_code), max_states=16000, seconds=95)
    out["joint_search"] = diag
    persist("joint_Astar_finished")
    if path_pair is None:
        out["status"] = "joint_no_solution_within_bounded_grid"
        persist("joint_Astar_no_route")
        return out
    for path, code in zip(path_pair, (target_code, victim_code)):
        if any(p[0] != 0 for p in path):
            raise RuntimeError("Joint paths cannot introduce vias")
        add_path(board, path, code, .15,
                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
    if unchanged_fingerprints(board) != fp:
        raise RuntimeError("Protected copper moved by joint A*")
    if ({tr.m_Uuid.AsString() for tr in board.GetTracks()
         if isinstance(tr, pcbnew.PCB_VIA)} != vias):
        raise RuntimeError("Joint A* produced unapproved via")
    if any(track_inventory(board).get(uid) != value
           for uid, value in original_tracks.items() if uid != S1_UUID):
        raise RuntimeError("Joint A* modified protected original copper")
    pcbnew.SaveBoard(str(boardfile), board)
    out["scratch_candidate_saved"] = True
    out["status"] = "two_coupled_FCu_paths_pending_independent_native_DRC"
    persist("joint_scratch_saved_no_release")
    return out


def run(archive: Path, output: Path) -> dict:
    from probe_block2_isolated_s1s2 import pinned_source_copy
    from probe_block2_ch038_restitution import isolated_drc

    source_sha = file_sha(archive)
    report = {**NO_RELEASE, "status": "joint_unqualified",
              "native_baseline_DRC": None, "native_trial_DRC": None,
              "joint_138_DRC_qualified": False,
              "child_exit_code": None, "child_diagnostic": None,
              "source_archive_unchanged": False}
    def persist():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2)+"\n")
    persist()
    with tempfile.TemporaryDirectory(prefix="CH018-S1-JOINT-") as work:
        root = Path(work)
        board = pinned_source_copy(archive, root)
        baseline = root / "139-native.json"
        report["native_baseline_DRC"] = isolated_drc(board, baseline)
        if report["native_baseline_DRC"] != BASELINE:
            raise RuntimeError("Baseline native 139/0/0 failed")
        child_json = root / "joint-child.json"
        try:
            p = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--child", "--board", str(board),
                 "--baseline", str(baseline),
                 "--output", str(child_json)],
                capture_output=True, text=True, check=False, timeout=195)
            report["child_exit_code"] = p.returncode
            report["child_stderr_tail"] = p.stderr[-1800:]
        except subprocess.TimeoutExpired as exc:
            report["child_exit_code"] = 124
            report["child_stderr_tail"] = str(exc)[-1200:]
        if child_json.exists():
            report["child_diagnostic"] = json.loads(child_json.read_text())
        report["source_archive_unchanged"] = file_sha(archive) == source_sha
        scratch = root / "joint_CH018_MUXS1_diagnostic" / board.name
        if (report["child_exit_code"] == 0
                and (report["child_diagnostic"] or {}).get(
                    "scratch_candidate_saved") is True
                and scratch.exists()):
            report["native_trial_DRC"] = isolated_drc(
                scratch, root / "joint-native.json")
            report["joint_138_DRC_qualified"] = (
                report["native_trial_DRC"] ==
                {"violations": 0, "warnings": 0, "unconnected": 138}
                and report["source_archive_unchanged"])
        report["status"] = (
            "joint_138_native_DRC_pass_no_promotion"
            if report["joint_138_DRC_qualified"]
            else "joint_scratch_unqualified_no_release")
        persist()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--board", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    if a.child:
        if not a.board or not a.baseline or a.candidate:
            raise ValueError("Isolated worker requires --board and --baseline")
        result = child(a.board, a.baseline, a.output)
    else:
        if a.board or a.baseline or not a.candidate:
            raise ValueError("Supervisor requires --candidate only")
        result = run(a.candidate, a.output)
    print(json.dumps({"status": result["status"],
                      "accepted": False, "fabrication_release": False}))


if __name__ == "__main__":
    main()

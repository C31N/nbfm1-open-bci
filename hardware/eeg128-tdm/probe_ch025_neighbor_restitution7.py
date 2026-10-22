#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bounded scratch-only seven-neighbor restoration and joint CH025/CH022 probe.

Does not modify tracked copper, create manufacturing data, or promote a
checkpoint. Native DRC and independent byte replay are distinct gates.
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
from probe_ch025_fcu_l3_exact import (
    CUT, NET, OTHER, ZONE, track_inventory, power_fcu_obstacles,
    trial_l3_mask,
)
from analyze_ch025_l3_precision_mask import (
    PROBE_28_CH022_LAYERS, exact_native_difference,
)

NEIGHBORS = {
    "ff9f490d-9f0d-4dc1-96a8-089ed3689134": "MUX_S0",
    "2ac3aecb-9a62-4bc7-846a-75a782ad0474": "MUX_S1",
    "d63cd5b4-9b79-4d97-8e66-1895bb81d615": "MUX_S2",
    "c320c092-5407-4ad6-9a97-2c324373271c": "MUX_S3",
    "721c2834-e08b-4b5f-a60d-4160225495c2": "MUX_EN",
    "81777460-c80a-48c9-8608-bae0dd42ee2f": "CH027_N_MUX",
    "3a4fd855-0c62-4287-b912-c9d8725d2b24": "CH030_P_MUX",
}
UNCHANGED = {
    "31a40ce9-1b3f-4f1a-b654-7fec9e793976": "MUX_S2",
    "af5b208b-71c0-4c32-82ba-836b5254e9d8": "CH028_N_ELECTRODE",
}
PATH = (
    (49.450000, 14.900000),
    (47.642886, 17.661358),
    (47.450000, 17.926633),
    (47.450000, 18.837592),
    (44.021245, 20.239663),
    (44.025592, 29.275775),
    (41.950000, 30.785452),
    (42.356871, 33.249721),
    (43.040000, 34.975000),
    (43.139692, 37.270803),
    (46.029855, 38.770153),
    (44.284410, 41.302234),
    (37.957858, 44.076838),
    (37.960000, 46.342305),
    (36.055000, 47.975000),
    (36.105000, 48.850000),
)
FLAGS = {
    "accepted": False, "routing_completed": False,
    "fabrication_release": False, "manufacturing_files": False,
    "independent_byte_replay": False, "checkpoint_promoted": False,
}
ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_plan() -> None:
    length = sum(math.dist(a, b) for a, b in zip(PATH, PATH[1:]))
    if (len(NEIGHBORS) != 7 or len(UNCHANGED) != 2 or
            len(PATH) != 16 or PATH[0] != (49.45, 14.9) or
            PATH[-1] != (36.105, 48.85) or not 45.35 < length < 45.45):
        raise ValueError("Not the reviewed 139 checkpoint geometry")
    if any(protected_net(net) for net in NEIGHBORS.values()):
        raise ValueError("Protected neighbor was selected")


def audit_foreign_tracks(
    original: dict[str, tuple[Any, ...]],
    after: dict[str, tuple[Any, ...]],
) -> None:
    """Every original track except the seven candidates and CH025 cut is frozen."""
    for uid, data in original.items():
        if uid not in NEIGHBORS and uid != CUT and after.get(uid) != data:
            raise RuntimeError("Untouchable existing-track UUID changed: " + uid)
    for uid, name in UNCHANGED.items():
        if uid not in original or original[uid][0] != name or after.get(uid) != original[uid]:
            raise RuntimeError("Preserved neighboring original changed: " + uid)


def propose(
    board: Any, original: Any, power: Any,
    margin: float,
) -> Any | None:
    """Route one original 0.15-mm track end-to-end entirely on F.Cu."""
    import pcbnew
    from shapely.geometry import GeometryCollection, Point, box
    from shapely.ops import unary_union
    from escape_mesh_505 import mesh_route
    from route_targeted_closure import routing_domain, xy

    start = xy(original.GetStart())
    goal = xy(original.GetEnd())
    domain = routing_domain(board, .075, .25)
    region = box(min(start[0], goal[0]) - margin,
                 min(start[1], goal[1]) - margin,
                 max(start[0], goal[0]) + margin,
                 max(start[1], goal[1]) + margin).intersection(domain)
    if not domain.covers(Point(start)) or not domain.covers(Point(goal)):
        return None
    ch022_via_guard = [
        Point(a[1:]).buffer(.505)
        for a, b in zip(PROBE_28_CH022_LAYERS, PROBE_28_CH022_LAYERS[1:])
        if a[0] != b[0]
    ]
    blocker = unary_union([power_fcu_obstacles(board), *ch022_via_guard])
    path = mesh_route(
        board, start, goal, original.GetNetCode(),
        (pcbnew.F_Cu, pcbnew.B_Cu), power, region,
        start_layer=0, goal_layer=0, allow_vias=False,
        extra_obstacles=[blocker, GeometryCollection()],
    )
    if (not path or len(path) < 2 or any(v[0] != 0 for v in path)
            or math.dist(path[0][1:], start) > .000002
            or math.dist(path[-1][1:], goal) > .000002):
        return None
    return path


def attempt(root: Path, reverse: bool) -> dict[str, Any]:
    import pcbnew
    from analyze_ch025_l3_native_refill import filled
    from escape_mesh_505 import add_mesh_path
    from route_targeted_closure import xy, metrics, native
    from native_connectivity import airwire_counts, regressed_nets

    boardfile = root / MEMBERS[0]
    board = pcbnew.LoadBoard(str(boardfile))
    old = track_inventory(board)
    tracked = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    if CUT not in tracked or tracked[CUT].GetNetname() != NET:
        raise ValueError("Pinned CH025 In2.Cu cut missing")
    if tracked[CUT].GetLayer() != pcbnew.In2_Cu:
        raise ValueError("CH025 legacy cut no longer In2.Cu")
    refs = []
    for uid, net in NEIGHBORS.items():
        t = tracked.get(uid)
        if (t is None or t.GetNetname() != net or
                t.GetLayer() != pcbnew.F_Cu or
                isinstance(t, (pcbnew.PCB_VIA, pcbnew.PCB_ARC)) or
                pcbnew.ToMM(t.GetWidth()) != .15):
            raise ValueError("Neighbor UUID and F.Cu identity mismatch: " + uid)
        refs.append(t)
    for uid, net in UNCHANGED.items():
        if uid not in tracked or tracked[uid].GetNetname() != net:
            raise ValueError("Untouchable MUX_S2 / CH028 original changed")
    zone = next((z for z in board.Zones() if
                 z.m_Uuid.AsString() == ZONE and
                 z.GetNetname() == "3V3A" and
                 z.IsOnLayer(pcbnew.In2_Cu)), None)
    if zone is None:
        raise ValueError("Native 3V3A zone UUID missing")
    orig_pad = sorted((pad.m_Uuid.AsString(), pad.GetNetname(), xy(pad.GetPosition()))
                      for fp in board.GetFootprints() for pad in fp.Pads())
    orig_via = {uid: value for uid, value in old.items()
                if value[-1] == "PCB_VIA"}
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    baseline_l3 = pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.In2_Cu))
    power = filled(zone)
    board.Remove(tracked[CUT])
    for t in refs:
        board.Remove(t)
    add_mesh_path(board, [(0, *p) for p in PATH],
                  board.FindNet(NET).GetNetCode(),
                  (pcbnew.F_Cu, pcbnew.B_Cu))
    refs.sort(key=lambda t: math.dist(xy(t.GetStart()), xy(t.GetEnd())),
              reverse=reverse)
    report: dict[str, Any] = {
        **FLAGS, "status": "neighbor_routing_started",
        "order": "longest_first" if reverse else "shortest_first",
        "neighbors": [], "restored_count": 0,
        "L3_loss_mm2": None, "L3_gain_mm2": None,
        "native_DRC_qualified": False, "schematic_parity_qualified": False,
        "protected_copper_unchanged": True,
    }
    for t in refs:
        row: dict[str, Any] = {
            "uuid": t.m_Uuid.AsString(), "net": t.GetNetname(),
            "start_mm": list(xy(t.GetStart())),
            "end_mm": list(xy(t.GetEnd())),
            "length_mm": round(math.dist(xy(t.GetStart()), xy(t.GetEnd())), 6),
            "trials": [], "connected_native": False,
        }
        report["neighbors"].append(row)
        proposed = None
        for margin in (2.5, 5.0, 10.0, 18.0):
            proposed = propose(board, t, power, margin)
            row["trials"].append({"margin_mm": margin, "path_found": proposed is not None})
            if proposed is not None:
                break
        if proposed is None:
            report["status"] = "first_unrestored_neighbor_" + t.GetNetname()
            return report
        row["vertices"] = len(proposed)
        row["proposed_path"] = proposed
        add_mesh_path(board, proposed, t.GetNetCode(),
                      (pcbnew.F_Cu, pcbnew.B_Cu))
        report["restored_count"] += 1
    audit_foreign_tracks(old, track_inventory(board))
    current_via = {uid: value for uid, value in track_inventory(board).items()
                   if value[-1] == "PCB_VIA"}
    if current_via != orig_via:
        raise RuntimeError("Existing vias altered or unreviewed vias created")
    new_pad = sorted((pad.m_Uuid.AsString(), pad.GetNetname(), xy(pad.GetPosition()))
                     for fp in board.GetFootprints() for pad in fp.Pads())
    if new_pad != orig_pad:
        raise RuntimeError("Pads/footprints altered")
    report["seven_neighbors_geometrically_proposed"] = True
    path22 = list(PROBE_28_CH022_LAYERS)
    if len(path22) != 23 or sum(a[0] != b[0] for a,b in
                                 zip(path22,path22[1:])) != 4:
        raise ValueError("Unreviewed CH022 geometry")
    add_mesh_path(board, path22, board.FindNet(OTHER).GetNetCode(),
                  (pcbnew.B_Cu, pcbnew.In2_Cu))
    mask, area = trial_l3_mask(board, zone, baseline_l3)
    report["L3_pre_loss_mm2"] = area.get("pre_loss_mm2")
    report["L3_pre_gain_mm2"] = area.get("pre_gain_mm2")
    report["L3_mask_status"] = area["status"]
    report["L3_mask_trials"] = area.get("trials", [])
    if not area["native_exact"]:
        report["status"] = "strict_L3_area_not_restored"
        return report
    if mask is not None and not mask.IsRuleArea():
        raise RuntimeError("Invalid precision rule keepout")
    refilled = pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.In2_Cu))
    exact = exact_native_difference(baseline_l3, refilled)
    if not exact["native_both_empty"]:
        raise RuntimeError("Non-zero native directional zone delta")
    report["L3_loss_mm2"] = 0.0
    report["L3_gain_mm2"] = 0.0
    pcbnew.SaveBoard(str(boardfile), board)
    after = native(boardfile, root / "after.json")
    original = native(root / "baseline" / MEMBERS[0], root / "before.json")
    report["native_DRC"] = metrics(after)
    report["regressed_nets"] = regressed_nets(original, after)
    old_counts, now_counts = airwire_counts(original), airwire_counts(after)
    report["neighbor_unconnected_before"] = {
        net: old_counts[net] for net in set(NEIGHBORS.values())
    }
    report["neighbor_unconnected_after"] = {
        net: now_counts[net] for net in set(NEIGHBORS.values())
    }
    report["restoration_native"] = (not report["regressed_nets"]
        and all(now_counts[n] <= old_counts[n] for n in NEIGHBORS.values()))
    if (report["native_DRC"] != {"violations":0,"warnings":0,"unconnected":136}
            or not report["restoration_native"]):
        report["status"] = "native_DRC_or_neighbor_regression"
        return report
    report["native_DRC_qualified"] = True
    parity = root / "parity.json"
    completed = subprocess.run([
        "kicad-cli", "pcb", "drc", "--schematic-parity",
        "--severity-all", "--all-track-errors",
        "--format", "json", "--output", str(parity), str(boardfile),
    ], capture_output=True, text=True, check=False)
    if parity.is_file():
        result = json.loads(parity.read_text(encoding="utf-8"))
        report["schematic_parity_qualified"] = (
            completed.returncode == 0 and
            all(isinstance(result.get(k), list) and not result[k]
                for k in ("violations", "unconnected_items", "schematic_parity")))
    report["status"] = ("candidate_136_unaccepted_pending_byte_replay" if
        report["schematic_parity_qualified"] else "schematic_parity_failed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    check_plan()
    if sha(args.archive) != ARCHIVE_SHA256:
        raise SystemExit("Wrong pinned 139 ZIP SHA-256")
    reports = []
    for reverse in (False, True):
        with tempfile.TemporaryDirectory(prefix="ch025-restitution7-") as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(args.archive) as archive:
                if sorted(archive.namelist()) != sorted(MEMBERS):
                    raise ValueError("Wrong archive member list")
                for name in MEMBERS:
                    (root / name).write_bytes(archive.read(name))
            if sha(root / MEMBERS[0]) != BOARD_SHA256:
                raise ValueError("Wrong pinned 139 PCB SHA-256")
            import pcbnew
            if not pcbnew.Version().startswith("8.0.9"):
                raise RuntimeError("Pinned KiCad 8.0.9 required")
            (root / "eeg128-tdm.kicad_sch").write_bytes(
                (ROOT / "eeg128-tdm.kicad_sch").read_bytes())
            (root / "baseline").mkdir()
            for name in MEMBERS:
                shutil.copy2(root / name, root / "baseline" / name)
            report = attempt(root, reverse)
            reports.append(report)
            print(json.dumps({
                "order": report["order"], "status": report["status"],
                "neighbors": report["restored_count"],
                "accepted": False, "fabrication_release": False,
            }), flush=True)
            if report["status"] == "candidate_136_unaccepted_pending_byte_replay":
                break
    if sha(args.archive) != ARCHIVE_SHA256:
        raise RuntimeError("Frozen input ZIP mutated")
    result = {
        **FLAGS, "status": reports[-1]["status"],
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_pcb_sha256": BOARD_SHA256,
        "baseline_airwires": 139, "target_airwires": 136,
        "attempts": reports, "F_Cu_only": True,
        "In1_Cu_used": False, "L3_release_gate_required": True,
        "manufacturing_export_invoked": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n",
                           encoding="utf-8")
    print(result["status"], flush=True)


if __name__ == "__main__":
    main()

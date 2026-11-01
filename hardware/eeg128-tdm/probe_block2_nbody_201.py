#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Disposable Block2 three-target + CH038 + 201-victim F.Cu routing probe.

All 203 original cut segments are explicitly identified and tracked. Three
targets are routed on one shared native BOARD after CH038 restitution. Every
victim is then either reconnected or reported as an exact blocked UUID.
Scratch-only: no release, no source mutation, no new via, no In1 routing.
Native 136/0/0 is necessary but never sufficient for acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NO_RELEASE = dict(accepted=False, routing_completed=False,
                  fabrication_release=False, manufacturing_files=False,
                  checkpoint_promoted=False, schematic_parity_qualified=False,
                  independent_replay_verified=False, new_vias_added=0)
TARGETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")
CH038 = ("1a5c9937-f30d-4bf9-b20a-c65f47d46040",
         "f1271355-bfbd-4e09-b95f-b9d10b867e72")
ORDERS = tuple(itertools.permutations(TARGETS))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_drc(board: Path, report: Path) -> dict:
    code = (
        "import sys,json;from pathlib import Path;"
        "sys.path.insert(0,sys.argv[1]);"
        "from route_targeted_closure import native,metrics;"
        "print(json.dumps(metrics(native(Path(sys.argv[2]),Path(sys.argv[3])))))"
    )
    p = subprocess.run(
        [sys.executable, "-c", code, str(Path(__file__).resolve().parent),
         str(board), str(report)], text=True, capture_output=True,
        check=False, timeout=160)
    if p.returncode:
        raise RuntimeError("Independent KiCad DRC failed: " + p.stderr[-1300:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def route_child(board_path: Path, baseline: Path, output: Path,
                order_id: int, future_lane_penalty: float = 0.0,
                joint_three: bool = False,
                joint_weight: float = 1.0,
                cbs_three: bool = False,
                cbs_selection: str = "length",
                cbs_split_mode: str = "single-edge",
                cbs_grid_mm: float = .30,
                macro_three: bool = False,
                elastic_three: bool = False) -> dict:
    import pcbnew
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from probe_block2_fcu_fixed_cut_upperbound import (
        strip_track_segments_by_uuid, upperbound_movable,
    )
    from probe_block2_deep_fcu_multinet import native_open_positions
    from probe_ch025_cooperative8 import unchanged_fingerprints
    from board_scratch_integrity import component_inventory, require_unchanged_components
    from probe_ch025_fcu_l3_exact import track_inventory
    from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
    from route_targeted_closure import (
        add_path, make_track, search, xy,
    )

    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Wrong KiCad version for no-release experiment")

    if file_hash(board_path) != PINNED_CANDIDATE_SHA:
        raise RuntimeError("139 source copper hash drift")
    if order_id not in range(len(ORDERS)):
        raise ValueError("Unapproved target order")
    if not 0.0 <= future_lane_penalty <= 500.0:
        raise ValueError("Unreviewed future FCu lane penalty")
    if not 1.0 <= joint_weight <= 3.0:
        raise ValueError("Unreviewed coupled MAPF3 weight")
    if sum((bool(joint_three), bool(cbs_three), bool(macro_three))) > 1:
        raise ValueError("Select exactly one coupled strategy")
    if elastic_three and any((joint_three, cbs_three, macro_three)):
        raise ValueError("Elastic three-net strategy must be exclusive")
    if cbs_selection not in ("length", "conflict-volume"):
        raise ValueError("Unreviewed CBS node selection strategy")
    if cbs_split_mode not in ("single-edge", "corridor-bundle"):
        raise ValueError("Unreviewed CBS splitting strategy")
    if not .19 <= cbs_grid_mm <= .44:
        raise ValueError("Unreviewed CBS grid size")
    original = pcbnew.LoadBoard(str(board_path))
    component_signature = component_inventory(original)
    initial = track_inventory(original)
    protected = unchanged_fingerprints(original)
    base_vias = {t.m_Uuid.AsString() for t in original.GetTracks()
                 if isinstance(t, pcbnew.PCB_VIA)}
    opens = native_open_positions(json.loads(baseline.read_text()))
    all_xy = [p for a in opens.values() for p in a]
    bbox = box(min(x for x, _ in all_xy) - 2.5,
               min(y for _, y in all_xy) - 2.5,
               max(x for x, _ in all_xy) + 2.5,
               max(y for _, y in all_xy) + 2.5)
    original_tracks = {t.m_Uuid.AsString(): t for t in original.GetTracks()}
    removed: dict[str, dict] = {}
    for tr in original.GetTracks():
        if (isinstance(tr, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))
                or tr.GetLayer() != pcbnew.F_Cu
                or not upperbound_movable(tr.GetNetname())):
            continue
        a, b = xy(tr.GetStart()), xy(tr.GetEnd())
        if LineString((a, b)).intersects(bbox):
            removed[tr.m_Uuid.AsString()] = {
                "net": tr.GetNetname(), "start": a, "end": b,
                "width_mm": pcbnew.ToMM(tr.GetWidth()),
                "original_UUID": tr.m_Uuid.AsString(),
            }
    if len(removed) != 201 or set(removed).intersection(CH038):
        raise RuntimeError("Exact 201 FCu whitelist drift")
    for uid in CH038:
        tr = original_tracks.get(uid)
        if (tr is None or tr.GetNetname() != "CH038_P_MUX"
                or tr.GetLayer() != pcbnew.F_Cu
                or isinstance(tr, pcbnew.PCB_VIA)):
            raise RuntimeError("CH038 UUID protection mismatch")

    record = {
        **NO_RELEASE, "status": "nbody_starting", "order": ORDERS[order_id],
        "future_lane_penalty": future_lane_penalty,
        "joint_three_enabled": joint_three,
        "cbs_three_enabled": cbs_three,
        "cbs_selection": cbs_selection,
        "cbs_split_mode": cbs_split_mode,
        "cbs_grid_mm": cbs_grid_mm,
        "macro_three_enabled": macro_three,
        "elastic_three_enabled": elastic_three,
        "joint_weight": joint_weight,
        "baseline_DRC": {"violations": 0, "warnings": 0, "unconnected": 139},
        "cut_whitelist_UUIDs": sorted(removed),
        "CH038_cut_UUIDs": list(CH038),
        "original_victim_count": len(removed),
        "victims_restored_original_geometry": [],
        "victims_routed_new_geometry": [],
        "blocked_victim_UUIDs": [],
        "attempted_victim_UUIDs": [],
        "CH038_routed_UUIDs": [],
        "target_nets_routed": [],
        "topology_after_CH038": {},
        "topology_after_targets": {},
        "native_candidate_DRC": None,
        "fully_restituted": False,
        "source_unchanged": False,
        "candidate_qualified_136": False,
    }
    def persist(stage: str) -> None:
        record["last_stage"] = stage
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n")
    persist("inventory_verified")
    root = board_path.parent
    # The isolated 139/0/0 CH038 return is already a native proof on the
    # untouched 201-track source. Obtain it in an independently terminated
    # child process BEFORE widening the rip-up set. This avoids doing the
    # most expensive A* initialization on the stripped, highly open PCB.
    ch038_report = root / ("NBODY_CH038_RETURN_%d.json" % order_id)
    persist("isolated_CH038_native_pre_return_started")
    return_cmd = [
        sys.executable,
        str(Path(__file__).with_name("probe_block2_ch038_restitution.py")),
        "--child", "--source", str(board_path),
        "--native-baseline", str(baseline),
        "--output", str(ch038_report),
    ]
    try:
        ch038_child = subprocess.run(
            return_cmd, capture_output=True, text=True,
            check=False, timeout=115)
    except subprocess.TimeoutExpired as exc:
        record["status"] = "CH038_pre_return_timed_out_no_release"
        record["CH038_pre_return_stderr_tail"] = str(exc)[-900:]
        persist("CH038_pre_return_timeout")
        return record
    record["CH038_pre_return_exit_code"] = ch038_child.returncode
    record["CH038_pre_return_stderr_tail"] = ch038_child.stderr[-1200:]
    if ch038_report.exists():
        record["CH038_pre_return_diagnostic"] = json.loads(
            ch038_report.read_text())
    persist("isolated_CH038_native_pre_return_complete")
    pre_return = record.get("CH038_pre_return_diagnostic", {})
    replaced_board = root / "CH038_PROBE_ONLY" / board_path.name
    if (ch038_child.returncode != 0
            or not pre_return.get("ch038_both_replacements_found")
            or not replaced_board.exists()):
        record["status"] = "CH038_pre_return_unqualified"
        persist("CH038_pre_return_rejected")
        return record
    # Separate native DRC process, with .kicad_dru present, before any
    # additional victim is ever removed. A 139/0/0 result is mandatory.
    from probe_block2_ch038_restitution import isolated_drc
    ch038_metrics = isolated_drc(
        replaced_board, root / ("NBODY_CH038_native_%d.json" % order_id))
    record["CH038_pre_return_native_DRC"] = ch038_metrics
    persist("CH038_pre_return_native_DRC_recorded")
    if ch038_metrics != {"violations": 0, "warnings": 0, "unconnected": 139}:
        record["status"] = "CH038_pre_return_native_DRC_failed"
        persist("CH038_pre_return_not_139_0_0")
        return record
    record["CH038_routed_UUIDs"] = list(CH038)
    # The preliminary CH038 PCB is the ONLY source for the 201-track cut;
    # original source PCB/ZIP bytes remain immutable and pinned by SHA.
    scratch = root / ("NBODY_%d" % order_id)
    scratch.mkdir(exist_ok=False)
    trial_board = scratch / board_path.name
    trial_board.write_text(
        strip_track_segments_by_uuid(
            replaced_board.read_text(encoding="utf-8"), set(removed)),
        encoding="utf-8")
    for suffix in (".kicad_pro", ".kicad_dru"):
        trial_board.with_suffix(suffix).write_bytes(
            board_path.with_suffix(suffix).read_bytes())
    persist("201_whitelist_UUIDs_removed_after_CH038_DRC_pass")
    board = pcbnew.LoadBoard(str(trial_board))
    if board is None:
        raise RuntimeError("Cannot parse isolated N-body scratch PCB")
    require_unchanged_components(board, component_signature, "201-track-cut")
    persist("201_cut_native_board_loaded")
    initial_unmodified = {uid: v for uid, v in initial.items()
                          if uid not in removed and uid not in CH038}
    inventory = track_inventory(board)
    if not all(inventory.get(uid) == value
               for uid, value in initial_unmodified.items()):
        raise RuntimeError("Non-whitelisted copper modified by scratch cut")
    if unchanged_fingerprints(board) != protected:
        raise RuntimeError("Protected pads/zones changed by scratch cut")
    if ({t.m_Uuid.AsString() for t in board.GetTracks()
         if isinstance(t, pcbnew.PCB_VIA)} != base_vias):
        raise RuntimeError("A via changed in scratch cut")
    persist("immutable_201_cut_native_copper_verified")
    order = ORDERS[order_id]
    victim_lanes = unary_union([
        LineString((v["start"], v["end"])).buffer(v["width_mm"]/2 + .25)
        for v in removed.values()])
    deadline = time.monotonic() + (245 if elastic_three else 135)
    # Native CH038+201 topology was separately established for all three
    # endpoints in the pinned preceding workflow. Recomputing the exact same
    # costly component graph three times before A* exceeded child budgets.
    # This worker directly tests actual sequential FCu path existence with
    # real SHAPE obstacles; an unsuccessful route is explicitly rejected.
    record["topology_after_CH038"] = {
        "prerequisite": "native_CH038_plus_201_three_target_screens_PASS",
        "previous_workflow_run": 41292189543,
        "recomputed_in_this_worker": False,
        "route_existence_must_be_verified_by_Astar": True,
    }
    persist("CH038_both_replaced_joint_Astar_started")
    persist("three_target_joint_Astar_batch_started")
    if macro_three:
        from probe_block2_macro_voronoi import macro_routes
        record["macro_three_method"] = "sampled_medial_voronoi_ridge_waypoints"
        def update_macro(stage: str, info: dict) -> None:
            record["macro_three_progress"] = info
            persist(stage)
        persist("macro_voronoi_skeleton_started")
        # A 0.44-mm sample reported 29-34 *sampled* free components in
        # native workflow #1, but already closed one full target on four
        # fine-grid micro hops. A disconnected coarse sample is NOT proof of
        # topological impossibility. Retry on independent scratch clones
        # with finer skeletons, never with the previous trial's copper.
        macro_diagnostic = {}
        record["macro_three_attempts"] = []
        for coarse_step in (.44, .30, .22):
            if coarse_step != .44:
                board = pcbnew.LoadBoard(str(trial_board))
                if board is None or unchanged_fingerprints(board) != protected:
                    raise RuntimeError("Macro retry scratch copper drift")
                require_unchanged_components(board, component_signature, "macro-retry-reload")
                persist("macro_reloaded_exact_201_cut_scratch")
            # macro_routes adds every successful micro-hop directly to this
            # disposable board. On failure the whole board is discarded.
            _, macro_diagnostic = macro_routes(
                board, opens, order, step_mm=coarse_step,
                micro_step_mm=.22, lane_bias=10.,
                deadline_s=105., progress=update_macro)
            require_unchanged_components(board, component_signature, "macro-waypoints-and-micro-Astar")
            record["macro_three_attempts"].append({
                "coarse_grid_mm": coarse_step,
                "status": macro_diagnostic.get("status"),
                "component_counts_by_net": macro_diagnostic.get(
                    "component_counts_by_net", {}),
                "blocked_target": macro_diagnostic.get("blocked_target"),
                "micro_segments_completed": macro_diagnostic.get(
                    "micro_segments_completed", {}),
            })
            record["macro_three_diagnostic"] = macro_diagnostic
            persist("macro_three_attempt_completed")
            if macro_diagnostic.get("status") == "macro_three_targets_proposed_unverified":
                break
        persist("macro_three_solver_returned")
        if macro_diagnostic.get("status") != "macro_three_targets_proposed_unverified":
            record["status"] = "macro_three_not_routable_with_bounded_waypoints"
            record["blocked_target"] = macro_diagnostic.get("blocked_target")
            persist("macro_three_no_release")
            return record
        if any(macro_diagnostic.get("micro_segments_completed", {}).get(net) != 4
               for net in TARGETS):
            raise RuntimeError("No complete four-hop macro routing for targets")
        record["target_nets_routed"].extend(order)
        persist("macro_three_proposed_paths_ready_for_all_201_restoration")
    elif elastic_three:
        from probe_block2_macro_voronoi import macro_routes
        from probe_block2_elastic_routes import rubber_band_routes
        from probe_block2_cbs_fcu3 import spatial_cbs_fcu3

        record["elastic_three_method"] = "repulsion_zero_width_guided_CBS3"

        def elastic_progress(stage: str, info: dict) -> None:
            record["elastic_progress"] = info
            persist(stage)

        record["elastic_macro_attempts"] = []
        elastic_diagnostic = {}
        for coarse_step in (.44, .30):
            board = pcbnew.LoadBoard(str(trial_board))
            if board is None:
                raise RuntimeError("Cannot reload elastic scratch PCB")
            require_unchanged_components(
                board, component_signature, "elastic-macro-scratch-reload")
            _, elastic_diagnostic = macro_routes(
                board, opens, order, step_mm=coarse_step,
                micro_step_mm=.22, lane_bias=4., deadline_s=55.,
                progress=elastic_progress, dynamic_repulsion=True)
            require_unchanged_components(
                board, component_signature, "elastic-repulsion-proposal")
            record["elastic_macro_attempts"].append({
                "coarse_step_mm": coarse_step,
                "status": elastic_diagnostic.get("status"),
                "blocked_target": elastic_diagnostic.get("blocked_target"),
                "waypoint_repulsion": elastic_diagnostic.get(
                    "dynamic_waypoint_displacements", {}),
                "micro_segments_completed": elastic_diagnostic.get(
                    "micro_segments_completed", {}),
            })
            persist("elastic_repulsive_waypoint_attempt_finished")
            if (elastic_diagnostic.get("status")
                    == "macro_three_targets_proposed_unverified"):
                record["elastic_selected_strategy"] = "repulsive_macro"
                break
            if time.monotonic() > deadline - 120:
                break
        if (elastic_diagnostic.get("status")
                != "macro_three_targets_proposed_unverified"):
            # Reuse only the untouched scratch file, not copper from a
            # partially routed macro attempt.
            board = pcbnew.LoadBoard(str(trial_board))
            if board is None:
                raise RuntimeError("Cannot reload rubber scratch PCB")
            require_unchanged_components(
                board, component_signature, "rubber-fallback-clean-reload")
            _, rubber_diag, references = rubber_band_routes(
                board, opens, order, step_mm=.22, seconds=65.,
                progress=elastic_progress)
            record["rubber_band_diagnostic"] = rubber_diag
            record["zero_width_reference_nets"] = sorted(references)
            persist("zero_width_topology_and_inflation_checked")
            if rubber_diag.get("status") == "rubber_inflated_three_unverified":
                record["elastic_selected_strategy"] = "rubber_inflation"
            elif set(references) == set(TARGETS):
                # CBS only resolves FINITE-WIDTH boundary conflicts after
                # three crossing-free, zero-width topology paths exist.
                board = pcbnew.LoadBoard(str(trial_board))
                if board is None:
                    raise RuntimeError("Cannot reload guided CBS3 PCB")
                require_unchanged_components(
                    board, component_signature, "guided-CBS3-clean-reload")
                routes, cbs_diag = spatial_cbs_fcu3(
                    board, tuple(opens[net] for net in order),
                    tuple(board.FindNet(net).GetNetCode() for net in order),
                    step_mm=.30, max_cbs_nodes=1100,
                    max_lowlevel_nodes=20000, seconds=55.,
                    selection="conflict-volume",
                    reference_paths=tuple(references[net] for net in order),
                    progress=elastic_progress)
                record["rubber_guided_CBS3_diagnostic"] = cbs_diag
                record["repulsion_guidance"] = True
                persist("rubber_guided_CBS3_solver_returned")
                if routes is None:
                    record["status"] = "rubber_guided_CBS3_bounded_no_solution"
                    persist("elastic_no_release")
                    return record
                for net, path in zip(order, routes):
                    if len(path) < 2 or any(p[0] != 0 for p in path):
                        raise RuntimeError("CBS3 proposed non-FCu or via")
                    add_path(board, path, board.FindNet(net).GetNetCode(),
                             .15, layers=(pcbnew.F_Cu, pcbnew.B_Cu))
                record["elastic_selected_strategy"] = "rubber_guided_CBS3"
            else:
                record["status"] = "elastic_zero_width_topology_unavailable"
                persist("elastic_no_release")
                return record
        require_unchanged_components(
            board, component_signature, "elastic-three-before-restoration")
        record["target_nets_routed"].extend(order)
        persist("elastic_three_proposed_paths_ready_for_all_201_restoration")
    elif joint_three:
        from probe_block2_joint_fcu_mapf3 import simultaneous_fcu_astar3
        # One A* state contains three heads and three full partial paths.
        # CH038 already passed independent 139/0/0 native DRC.
        record["joint_three_method"] = "one_queue_three_heads_three_paths"
        def update_joint(stage: str, info: dict) -> None:
            record["joint_three_progress"] = info
            persist(stage)
        persist("mapf3_joint_solver_invoked")
        joint_endpoints = tuple(opens[n] for n in order)
        joint_codes = tuple(board.FindNet(n).GetNetCode() for n in order)
        routes, diagnostic = simultaneous_fcu_astar3(
            board, joint_endpoints, joint_codes,
            max_states=40000 if joint_weight > 1 else 12000,
            seconds=105, heuristic_weight=joint_weight,
            progress=update_joint)
        record["joint_three_diagnostic"] = diagnostic
        persist("mapf3_joint_solver_returned")
        if routes is None:
            record["status"] = "joint_three_no_solution_within_bounded_search"
            persist("mapf3_joint_three_rejected")
            return record
        if len(routes) != 3:
            raise RuntimeError("MAPF3 must return exactly three target paths")
        for net, code, path in zip(order, joint_codes, routes):
            if len(path) < 2 or any(point[0] != 0 for point in path):
                raise RuntimeError("Joint target crossed non-FCu or via")
            add_path(board, path, code, .15,
                     layers=(pcbnew.F_Cu, pcbnew.B_Cu))
            record["target_nets_routed"].append(net)
            persist("mapf3_target_committed_" + net)
    elif cbs_three:
        from probe_block2_cbs_fcu3 import spatial_cbs_fcu3
        # Conflict tree branches BOTH possible reroutes for each actual
        # crossing. CH038 remains native 139/0/0 DRC-qualified and fixed.
        record["cbs_three_method"] = "spatial_conflict_based_three_net"
        def update_conflict(stage: str, info: dict) -> None:
            record["cbs_three_progress"] = info
            persist(stage)
        persist("CBS3_solver_invoked")
        endpoints3 = tuple(opens[n] for n in order)
        netcodes3 = tuple(board.FindNet(n).GetNetCode() for n in order)
        routes, diagnostic = spatial_cbs_fcu3(
            board, endpoints3, netcodes3,
            max_cbs_nodes=1000, max_lowlevel_nodes=18000,
            seconds=105, selection=cbs_selection,
            split_mode=cbs_split_mode, step_mm=cbs_grid_mm,
            progress=update_conflict)
        record["cbs_three_diagnostic"] = diagnostic
        persist("CBS3_solver_returned")
        if routes is None:
            record["status"] = "CBS3_no_solution_within_bounded_search"
            persist("CBS3_joint_three_rejected")
            return record
        if len(routes) != 3:
            raise RuntimeError("CBS3 must return exactly three target paths")
        for net, code, path in zip(order, netcodes3, routes):
            if len(path) < 2 or any(point[0] != 0 for point in path):
                raise RuntimeError("CBS3 target escaped FCu / via")
            add_path(board, path, code, .15,
                     layers=(pcbnew.F_Cu, pcbnew.B_Cu))
            record["target_nets_routed"].append(net)
            persist("CBS3_target_committed_" + net)
    else:
        # Original sequential A* retained as independent comparison arm.
        for net in order:
            nc = board.FindNet(net).GetNetCode()
            a, b = opens[net]
            persist("Astar_start_" + net)
            remaining_targets = [
                future for future in order
                if future != net and future not in record["target_nets_routed"]]
            future_lanes = unary_union([
                LineString(opens[future]).buffer(.34)
                for future in remaining_targets])
            record.setdefault("future_lane_reservations", {})[net] = {
                "remaining_targets": remaining_targets,
                "penalty": future_lane_penalty,
            }
            costs = ((0, victim_lanes, 28.0),)
            if remaining_targets and future_lane_penalty > 0:
                costs += ((0, future_lanes, future_lane_penalty),)
            persist("joint_remaining_target_corridors_soft_reserved_" + net)
            path = search(
                board, a, b, nc, .15, .15, False, 6.0,
                step=.22, max_nodes=36000,
                deadline=min(time.monotonic()+23, deadline),
                start_layer=0, goal_layer=0,
                layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                cost_regions=costs)
            if path is None or len(path) < 2 or any(v[0] != 0 for v in path):
                record["status"] = "target_FCu_path_unavailable"
                record["blocked_target"] = net
                persist("target_search_failed_" + net)
                return record
            add_path(board, path, nc, .15,
                     layers=(pcbnew.F_Cu, pcbnew.B_Cu))
            record["target_nets_routed"].append(net)
            persist("target_route_added_" + net)
    if set(record["target_nets_routed"]) != set(TARGETS):
        raise RuntimeError("Incomplete target routes before restitution")
    persist("three_targets_completed_restoration_stage_entered")

    # Restore non-colliding victims first, then adapt colliding ones by a
    # separate A* on the SAME occupied copper. All 201 must be dealt with.
    initial_uuids = set(initial)
    introduced = [tr for tr in board.GetTracks()
                  if tr.m_Uuid.AsString() not in initial_uuids
                  and not isinstance(tr, pcbnew.PCB_VIA)]
    footprint = unary_union([
        LineString((xy(tr.GetStart()), xy(tr.GetEnd()))).buffer(
            pcbnew.ToMM(tr.GetWidth())/2 + .151)
        for tr in introduced])
    collided = []
    for uid in sorted(removed):
        victim = removed[uid]
        shape = LineString((victim["start"], victim["end"])).buffer(
            victim["width_mm"]/2)
        if shape.intersects(footprint):
            collided.append(uid)
            continue
        code = board.FindNet(victim["net"]).GetNetCode()
        make_track(board, victim["start"], victim["end"], code,
                   victim["width_mm"], pcbnew.F_Cu)
        record["victims_restored_original_geometry"].append(uid)
    record["victims_requiring_new_routing"] = collided
    persist("noncolliding_victims_restored")
    for uid in collided:
        victim = removed[uid]
        record["attempted_victim_UUIDs"].append(uid)
        if time.monotonic() >= deadline:
            record["blocked_victim_UUIDs"].extend(
                v for v in collided if v not in record["attempted_victim_UUIDs"])
            record["status"] = "bounded_victim_restoration_timeout"
            persist("victim_deadline")
            return record
        net_code = board.FindNet(victim["net"]).GetNetCode()
        path = search(
            board, victim["start"], victim["end"], net_code,
            victim["width_mm"], .15, False, 5.5,
            step=.22, max_nodes=19000,
            deadline=min(time.monotonic()+9, deadline),
            start_layer=0, goal_layer=0,
            layers=(pcbnew.F_Cu, pcbnew.B_Cu))
        if path is None or len(path) < 2 or any(v[0] != 0 for v in path):
            record["blocked_victim_UUIDs"].append(uid)
            record["status"] = "predictive_victim_restitution_deadlock"
            persist("blocked_victim_" + uid)
            return record
        add_path(board, path, net_code, victim["width_mm"],
                 layers=(pcbnew.F_Cu, pcbnew.B_Cu))
        record["victims_routed_new_geometry"].append(uid)
        persist("victim_reconnected_" + uid)
    if (len(record["victims_restored_original_geometry"])
            + len(record["victims_routed_new_geometry"]) != 201):
        raise RuntimeError("201-victim restoration count mismatch")
    if unchanged_fingerprints(board) != protected:
        raise RuntimeError("Protected copper changed after routing")
    # Build exactly ONE native SWIG inventory after all 201 restorations.
    # The repeated getter formerly rebuilt it for every UUID (O(N^2)).
    persist("restored_201_postroute_inventory_started")
    postroute_inventory = track_inventory(board)
    persist("restored_201_postroute_inventory_ready")
    if not all(postroute_inventory.get(uid) == val
               for uid, val in initial_unmodified.items()):
        raise RuntimeError("Other original copper changed")
    if ({t.m_Uuid.AsString() for t in board.GetTracks()
         if isinstance(t, pcbnew.PCB_VIA)} != base_vias):
        raise RuntimeError("New via or via movement detected")
    require_unchanged_components(board, component_signature, "before-scratch-save")
    if pcbnew.SaveBoard(str(trial_board), board) is False:
        raise RuntimeError("Scratch board could not be saved")
    saved = pcbnew.LoadBoard(str(trial_board))
    if saved is None:
        raise RuntimeError("Cannot reload scratch board")
    require_unchanged_components(saved, component_signature, "after-scratch-save")
    record["component_identity_verified"] = True
    record["fully_restituted"] = True
    record["scratch_board_ready_for_independent_DRC"] = True
    record["status"] = "all_201_restituted_pending_separate_native_DRC"
    persist("no_release_scratch_board_saved")
    return record


def run(archive: Path, output: Path, order_id: int,
        future_lane_penalty: float = 0.0,
        joint_three: bool = False,
        joint_weight: float = 1.0,
        cbs_three: bool = False,
        cbs_selection: str = "length",
        cbs_split_mode: str = "single-edge",
        cbs_grid_mm: float = .30,
        macro_three: bool = False) -> dict:
    from probe_block2_isolated_s1s2 import pinned_source_copy
    from probe_block2_ch038_restitution import isolated_drc
    if not 0.0 <= future_lane_penalty <= 500.0:
        raise ValueError("Unreviewed N-body lookahead penalty")
    if not 1.0 <= joint_weight <= 3.0:
        raise ValueError("Unreviewed N-body joint heuristic weight")
    if sum((bool(joint_three), bool(cbs_three), bool(macro_three))) > 1:
        raise ValueError("Choose only one coupled solver")
    if elastic_three and any((joint_three, cbs_three, macro_three)):
        raise ValueError("Elastic three-net strategy must be exclusive")
    if cbs_selection not in ("length", "conflict-volume"):
        raise ValueError("Unreviewed CBS search ordering")
    if cbs_split_mode not in ("single-edge", "corridor-bundle"):
        raise ValueError("Unreviewed CBS constraint bundling")
    if not .19 <= cbs_grid_mm <= .44:
        raise ValueError("Unreviewed CBS grid size")
    original_sha = file_hash(archive)
    report = {**NO_RELEASE, "status": "Nbody_not_qualified",
              "future_lane_penalty": future_lane_penalty,
              "joint_three_enabled": joint_three,
              "cbs_three_enabled": cbs_three,
              "cbs_selection": cbs_selection,
              "cbs_split_mode": cbs_split_mode,
              "cbs_grid_mm": cbs_grid_mm,
              "macro_three_enabled": macro_three,
        "elastic_three_enabled": elastic_three,
              "joint_weight": joint_weight,
              "order": ORDERS[order_id], "source_unchanged": False,
              "candidate_native_DRC": None,
              "candidate_qualified_136": False, "child_exit_code": None,
              "child_diagnostic": None}
    def persist() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
    persist()
    with tempfile.TemporaryDirectory(prefix="NBODY-201-CH038-") as tmp:
        root = Path(tmp)
        board = pinned_source_copy(archive, root)
        base = root / "baseline.json"
        metrics = isolated_drc(board, base)
        if metrics != {"violations": 0, "warnings": 0, "unconnected": 139}:
            raise RuntimeError("Native pinned 139/0/0 source lost")
        diag = root / "nbody-worker.json"
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--child", "--board", str(board), "--baseline", str(base),
                 "--order", str(order_id),
             "--future-lane-penalty", str(future_lane_penalty),
             *(["--joint-three"] if joint_three else []),
             *(["--cbs-three"] if cbs_three else []),
             *(["--macro-three"] if macro_three else []),
             *(["--elastic-three"] if elastic_three else []),
             "--cbs-selection", cbs_selection,
             "--cbs-split-mode", cbs_split_mode,
             "--cbs-grid-mm", str(cbs_grid_mm),
             "--joint-weight", str(joint_weight),
             "--output", str(diag)],
                capture_output=True, text=True, check=False,
            timeout=340 if (joint_three or cbs_three or macro_three or elastic_three) else 265)
            report["child_exit_code"] = result.returncode
            report["child_stderr_tail"] = result.stderr[-2000:]
            report["child_timeout"] = False
        except subprocess.TimeoutExpired as exc:
            # The child must be killed by subprocess.run; salvage its
            # atomically persisted stage/UUID inventory before /tmp cleanup.
            # A timeout is never interpreted as a topology result.
            report["child_exit_code"] = 124
            report["child_timeout"] = True
            report["child_stderr_tail"] = (
                "bounded_child_timeout: " + str(exc)[-1000:])
        report["child_diagnostic"] = (
            json.loads(diag.read_text()) if diag.exists() else None)
        report["last_observed_child_stage"] = (
            report["child_diagnostic"].get("last_stage")
            if report["child_diagnostic"] else "no_child_report")
        report["source_unchanged"] = file_hash(archive) == original_sha
        persist()
        child = report["child_diagnostic"] or {}
        trial = root / ("NBODY_%d" % order_id) / board.name
        if (report["child_exit_code"] == 0 and child.get("fully_restituted")
                and child.get("scratch_board_ready_for_independent_DRC")
                and trial.exists()):
            # Independent process performs native zone fill and DRC.
            report["candidate_native_DRC"] = isolated_drc(
                trial, root / "candidate-native.json")
            report["candidate_qualified_136"] = (
                report["candidate_native_DRC"] ==
                {"violations": 0, "warnings": 0, "unconnected": 136}
                and report["source_unchanged"])
        report["status"] = (
            "136_DRC_only_not_parity_L3_or_replay_qualified"
            if report["candidate_qualified_136"]
            else "Nbody_child_bounded_timeout_no_release"
            if report["child_timeout"]
            else "Nbody_unqualified_no_release")
        persist()
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path)
    p.add_argument("--board", type=Path)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--child", action="store_true")
    p.add_argument("--order", type=int, choices=range(len(ORDERS)), required=True)
    p.add_argument("--future-lane-penalty", type=float, default=0.0)
    p.add_argument("--joint-three", action="store_true")
    p.add_argument("--cbs-three", action="store_true")
    p.add_argument("--macro-three", action="store_true")
    p.add_argument("--elastic-three", action="store_true")
    p.add_argument("--cbs-selection", choices=("length", "conflict-volume"),
                   default="length")
    p.add_argument("--cbs-split-mode", choices=("single-edge", "corridor-bundle"),
                   default="single-edge")
    p.add_argument("--cbs-grid-mm", type=float, default=.30)
    p.add_argument("--joint-weight", type=float, default=1.0)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.child:
        if a.candidate or not a.board or not a.baseline:
            raise ValueError("Child expects only --board and --baseline")
        report = route_child(a.board, a.baseline, a.output, a.order,
                             future_lane_penalty=a.future_lane_penalty,
                             joint_three=a.joint_three,
                             joint_weight=a.joint_weight,
                             cbs_three=a.cbs_three,
                             cbs_selection=a.cbs_selection,
                             cbs_split_mode=a.cbs_split_mode,
                             cbs_grid_mm=a.cbs_grid_mm,
                             macro_three=a.macro_three,
                     elastic_three=a.elastic_three)
    else:
        if not a.candidate or a.board or a.baseline:
            raise ValueError("Parent expects only --candidate")
        report = run(a.candidate, a.output, a.order,
                     future_lane_penalty=a.future_lane_penalty,
                     joint_three=a.joint_three,
                     joint_weight=a.joint_weight,
                     cbs_three=a.cbs_three,
                     cbs_selection=a.cbs_selection,
                     cbs_split_mode=a.cbs_split_mode,
                     cbs_grid_mm=a.cbs_grid_mm,
                     macro_three=a.macro_three,
                     elastic_three=a.elastic_three)
    print(json.dumps({"status": report["status"],
                      "accepted": False, "fabrication_release": False}))


if __name__ == "__main__":
    main()

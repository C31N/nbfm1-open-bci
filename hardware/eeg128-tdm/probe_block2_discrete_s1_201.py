#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""No-release k=3 spatially distinct S1 routes followed by static CH018 A*.

After independently 139/0/0-qualifying the pinned CH038 return, remove only
the exact 201 eligible FCu UUIDs on fresh scratch clones. Find up to three
spatially separated MUX_S1 FCu candidates (no claim of distinct homotopy
without a separate topological proof), and try CH018_P_MUX against each.
For a success, restore all 200 other victims and native-DRC the complete
138-airwire candidate in a new process. In1, zones, VCM, MUX_EN, Block 1
and original untouched tracks remain immutable. No vias or fabrication.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from probe_block2_nbody_201 import NO_RELEASE, file_hash
from probe_block2_isolated_s1s2 import pinned_source_copy
from probe_block2_ch038_restitution import isolated_drc

S1_UUID="2ac3aecb-9a62-4bc7-846a-75a782ad0474"
CH038=("1a5c9937-f30d-4bf9-b20a-c65f47d46040",
       "f1271355-bfbd-4e09-b95f-b9d10b867e72")
BASE={"violations":0,"warnings":0,"unconnected":139}


def worker(source:Path,baseline:Path,output:Path) -> dict:
    import pcbnew
    from shapely.geometry import LineString,box
    from shapely.ops import unary_union
    from probe_block2_deep_fcu_multinet import native_open_positions
    from probe_block2_fcu_fixed_cut_upperbound import (
        upperbound_movable,strip_track_segments_by_uuid)
    from probe_ch025_cooperative8 import unchanged_fingerprints
    from probe_ch025_fcu_l3_exact import track_inventory
    from probe_mux_en_multihop_neighbors import PINNED_CANDIDATE_SHA
    from route_targeted_closure import xy,make_track,add_path,search

    data={**NO_RELEASE,"status":"s1_201_worker_start",
          "original_victim_count":None,"eligible_victim_UUIDs":[],
          "S1_UUID":S1_UUID,"static_candidates":[],
          "blocked_victim_UUIDs":[],"candidate_saved":False,
          "S2_S3_original_copper_readded":False,
          "topological_independence_proven":False,
          "new_vias_added":0,"source_file_unchanged":False}
    def stage(name:str) -> None:
        data["last_stage"]=name
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(data,indent=2)+"\n")
    stage("worker_initialized")
    if not pcbnew.Version().startswith("8.0.9"):
        raise RuntimeError("Pinned KiCad 8.0.9 required")
    # The worker must route on the independently DRC-qualified CH038-return
    # scratch, NOT on its immutable pinned original 139-copper predecessor.
    pinned=source.parent.parent/source.name
    if file_hash(pinned)!=PINNED_CANDIDATE_SHA:
        raise RuntimeError("Pinned MUX_EN predecessor SHA drift")
    if source==pinned or source.parent.name!="CH038_PROBE_ONLY":
        raise RuntimeError("Only native-verified CH038 return may be searched")
    started=time.monotonic()
    original=pcbnew.LoadBoard(str(source))
    inventory=track_inventory(original)
    protected=unchanged_fingerprints(original)
    vias={t.m_Uuid.AsString() for t in original.GetTracks()
          if isinstance(t,pcbnew.PCB_VIA)}
    opens=native_open_positions(json.loads(baseline.read_text()))
    allpts=[p for pair in opens.values() for p in pair]
    region=box(min(p[0] for p in allpts)-2.5,
               min(p[1] for p in allpts)-2.5,
               max(p[0] for p in allpts)+2.5,
               max(p[1] for p in allpts)+2.5)
    removed={}
    for track in original.GetTracks():
        if (isinstance(track,(pcbnew.PCB_VIA,pcbnew.PCB_ARC))
                or track.GetLayer()!=pcbnew.F_Cu
                or not upperbound_movable(track.GetNetname())):
            continue
        a,b=xy(track.GetStart()),xy(track.GetEnd())
        if LineString((a,b)).intersects(region):
            uid=track.m_Uuid.AsString()
            removed[uid]={"net":track.GetNetname(),
                          "start":a,"end":b,
                          "width_mm":pcbnew.ToMM(track.GetWidth())}
    if len(removed)!=201 or S1_UUID not in removed or set(removed)&set(CH038):
        raise RuntimeError("201 whitelist, protected CH038 or S1 membership drift")
    if removed[S1_UUID]["net"]!="MUX_S1":
        raise RuntimeError("S1 original segment mismatch")
    data["original_victim_count"]=len(removed)
    data["eligible_victim_UUIDs"]=sorted(removed)
    stage("201_whitelist_and_original_S1_exact_UUID_verified")
    source_text=source.read_text(encoding="utf-8")
    no_201=strip_track_segments_by_uuid(source_text,set(removed))
    initial_unmodified={k:v for k,v in inventory.items() if k not in removed}
    immutable_sha=file_hash(source)
    old_s1=removed[S1_UUID]
    prior=[]
    candidates=[]
    for iteration in range(3):
        if time.monotonic()-started>220:
            data["status"]="bounded_search_time_exhausted"
            stage("s1_iteration_time_exhausted")
            break
        folder=source.parent/("S1_DISCRETE_%d"%iteration)
        folder.mkdir(exist_ok=False)
        pcb=folder/source.name
        pcb.write_text(no_201,encoding="utf-8")
        for suffix in (".kicad_pro",".kicad_dru"):
            pcb.with_suffix(suffix).write_bytes(
                source.with_suffix(suffix).read_bytes())
        board=pcbnew.LoadBoard(str(pcb))
        if unchanged_fingerprints(board)!=protected:
            raise RuntimeError("Protected zones/pads drift on scratch")
        if any(t.m_Uuid.AsString() not in vias
               for t in board.GetTracks() if isinstance(t,pcbnew.PCB_VIA)):
            raise RuntimeError("Unexpected scratch via")
        local_inventory=track_inventory(board)
        if any(local_inventory.get(k)!=v for k,v in initial_unmodified.items()):
            raise RuntimeError("Protected original track drift")
        # S1 must first explore the FULL 201-cut FCu corridor. Original
        # MUX_S2/S3 remain protected by a large soft cost on their ORIGINAL
        # copper outlines and by explicit hard validation BEFORE CH018P.
        # The earlier S2/S3-first experiment found zero S1 alternatives.
        controls=[v for v in removed.values()
                  if v["net"] in ("MUX_S2","MUX_S3")]
        control_shapes=[
            LineString((v["start"],v["end"])).buffer(
                (v["width_mm"]+old_s1["width_mm"])/2+.15)
            for v in controls]
        control_keepout=unary_union(control_shapes)
        current={"iteration":iteration,"S1_routed":False,
                 "CH018_P_routed":False,"restored_victim_count":0,
                 "blocked_victim_UUIDs":[],"candidate_DRC":None,
                 "S1_path_spatially_distinct":False,
                 "S1_homotopy_independence_proven":False,
                 "scratch_saved_for_native_DRC":False}
        data["static_candidates"].append(current)
        stage("all_201_copper_removed_before_discrete_S1_%d"%iteration)
        # Static prior alternatives plus S2/S3 ORIGINAL clearance envelopes
        # are soft costs; the untouched candidate is a new scratch for k.
        costs=((0,control_keepout,85.),)+tuple(
            (0,line.buffer(.65),160.) for line in prior)
        s1code=board.FindNet("MUX_S1").GetNetCode()
        s1path=None
        if iteration==0:
            # This exact source segment was already DRC-clean at 139/0/0.
            # Test it as a valid static reference, not a "new" route.
            s1path=[(0,*old_s1["start"]),(0,*old_s1["end"])]
            current["route_origin"]="original_S1_segment_reference"
        else:
            # Direct, analytic two-leg bent paths avoid false-negative A*
            # endpoint anchoring on the raster. Each geometrical candidate
            # must avoid every fixed native FCu obstacle before CH018.
            import math
            from shapely.geometry import box as bounds_box
            from route_targeted_closure import obstacles
            a0,b0=old_s1["start"],old_s1["end"]
            vx,vy=b0[0]-a0[0],b0[1]-a0[1]
            norm=math.hypot(vx,vy)
            if norm < .25:
                raise RuntimeError("S1 original segment shorter than quarter mm")
            nx,ny=-vy/norm,vx/norm
            region_s1=bounds_box(min(a0[0],b0[0])-3.,
                                 min(a0[1],b0[1])-3.,
                                 max(a0[0],b0[0])+3.,
                                 max(a0[1],b0[1])+3.)
            shapes,_=obstacles(
                board,s1code,old_s1["width_mm"],.15,
                region_s1,.65,(pcbnew.F_Cu,pcbnew.B_Cu))
            fixed=shapes[0].buffer(-1e-9)
            proposals=(
                (0.66,1.10,1.65,2.20)
                if iteration==1 else (-.66,-1.10,-1.65,-2.20))
            for offset in proposals:
                middle=((a0[0]+b0[0])/2+nx*offset,
                        (a0[1]+b0[1])/2+ny*offset)
                trial=LineString((a0,middle,b0))
                if trial.relate_pattern(fixed,"T********"):
                    continue
                if prior and min(trial.hausdorff_distance(p)
                                 for p in prior)<.45:
                    continue
                s1path=[(0,*a0),(0,*middle),(0,*b0)]
                current["route_origin"]="native_obstacle_screened_bend"
                current["detour_offset_mm"]=offset
                break
            if s1path is None:
                # Grid A* is only a fallback, never a substitute for native
                # verification or unchanged S2/S3 original copper.
                s1path=search(
                    board,a0,b0,s1code,old_s1["width_mm"],.15,
                    False,6.,step=.22,max_nodes=35000,
                    deadline=time.monotonic()+24,
                    start_layer=0,goal_layer=0,
                    layers=(pcbnew.F_Cu,pcbnew.B_Cu),
                    cost_regions=costs)
                if s1path is not None:
                    current["route_origin"]="grid_Astar_fallback"
        if s1path is None or len(s1path)<2 or any(p[0]!=0 for p in s1path):
            current["status"]="S1_static_FCu_path_unavailable"
            stage("S1_static_route_not_found_%d"%iteration)
            continue
        line=LineString([p[1:] for p in s1path])
        # Spatial Hausdorff diversity is NOT enough to prove a distinct
        # obstacle homotopy class, so never report topological independence.
        if prior and min(line.hausdorff_distance(p) for p in prior)<.45:
            current["status"]="S1_candidate_not_spatially_distinct"
            stage("S1_duplicate_route_%d"%iteration)
            continue
        prior.append(line)
        current["S1_path_spatially_distinct"]=True
        current["S1_routed"]=True
        current["S1_length_mm"]=round(line.length,4)
        current["S1_path_nodes"]=len(s1path)
        add_path(board,s1path,s1code,old_s1["width_mm"],
                 layers=(pcbnew.F_Cu,pcbnew.B_Cu))
        stage("S1_static_candidate_routed_%d"%iteration)
        # Fail closed if any proposed S1 edge intrudes into S2/S3 ORIGINAL
        # track+clearance space; only then restore those protected controls.
        if line.intersects(control_keepout.buffer(-1e-9)):
            current["status"]="S1_crosses_protected_S2_S3_original_geometry"
            current["protected_control_conflicts"]=[
                {"net":v["net"],"start":v["start"],"end":v["end"]}
                for v,keepout in zip(controls,control_shapes)
                if line.intersects(keepout.buffer(-1e-9))]
            stage("S1_S2_S3_control_collision_%d"%iteration)
            continue
        for uid in sorted(removed):
            v=removed[uid]
            if v["net"] in ("MUX_S2","MUX_S3"):
                make_track(board,v["start"],v["end"],
                           board.FindNet(v["net"]).GetNetCode(),
                           v["width_mm"],pcbnew.F_Cu)
        data["S2_S3_original_copper_readded"]=True
        current["S2_S3_geometry_restituted_before_CH018P"]=True
        stage("S2_S3_immutable_controls_returned_%d"%iteration)
        target=opens["CH018_P_MUX"]
        chcode=board.FindNet("CH018_P_MUX").GetNetCode()
        chpath=search(
            board,target[0],target[1],chcode,.15,.15,
            False,6.,step=.22,max_nodes=35000,
            deadline=time.monotonic()+26,
            start_layer=0,goal_layer=0,
            layers=(pcbnew.F_Cu,pcbnew.B_Cu))
        if chpath is None or len(chpath)<2 or any(p[0]!=0 for p in chpath):
            current["status"]="CH018P_not_routable_against_static_S1"
            stage("CH018P_static_comparison_failed_%d"%iteration)
            continue
        current["CH018_P_routed"]=True
        current["CH018_P_path_nodes"]=len(chpath)
        add_path(board,chpath,chcode,.15,layers=(pcbnew.F_Cu,pcbnew.B_Cu))
        stage("CH018P_routed_against_static_S1_%d"%iteration)
        # Only newly routed S1/CH018 traces can force additional victims
        # to be displaced; original S2/S3 tracks have been restored first.
        original_uuids=set(inventory)
        introduced=[tr for tr in board.GetTracks()
                    if tr.m_Uuid.AsString() not in original_uuids
                    and tr.GetNetname() not in ("MUX_S2","MUX_S3")
                    and not isinstance(tr,pcbnew.PCB_VIA)]
        obstruction=unary_union([
            LineString((xy(tr.GetStart()),xy(tr.GetEnd()))).buffer(
                pcbnew.ToMM(tr.GetWidth())/2+.15)
            for tr in introduced])
        collided=[]
        restored=1  # S1 itself has been returned via a new route.
        for uid in sorted(removed):
            if uid==S1_UUID:
                continue
            v=removed[uid]
            if v["net"] in ("MUX_S2","MUX_S3"):
                restored+=1
                continue
            shape=LineString((v["start"],v["end"])).buffer(
                v["width_mm"]/2)
            if shape.intersects(obstruction):
                collided.append(uid)
                continue
            make_track(board,v["start"],v["end"],
                       board.FindNet(v["net"]).GetNetCode(),
                       v["width_mm"],pcbnew.F_Cu)
            restored+=1
        current["restored_victim_count"]=restored
        current["victims_requiring_reroute"]=collided
        stage("S1_discrete_noncolliding_victims_restored_%d"%iteration)
        for uid in collided:
            v=removed[uid]
            if time.monotonic()-started>=225:
                current["blocked_victim_UUIDs"].append(uid)
                current["status"]="bounded_victim_restoration_time_exhausted"
                stage("S1_discrete_victim_deadline_%d"%iteration)
                break
            net=board.FindNet(v["net"]).GetNetCode()
            path=search(board,v["start"],v["end"],net,
                        v["width_mm"],.15,False,4.5,
                        step=.22,max_nodes=15000,
                        deadline=time.monotonic()+8,
                        start_layer=0,goal_layer=0,
                        layers=(pcbnew.F_Cu,pcbnew.B_Cu))
            if path is None or len(path)<2 or any(p[0]!=0 for p in path):
                current["blocked_victim_UUIDs"].append(uid)
                current["status"]="S1_discrete_victim_restoration_deadlock"
                stage("S1_discrete_victim_blocked_"+uid)
                break
            add_path(board,path,net,v["width_mm"],
                     layers=(pcbnew.F_Cu,pcbnew.B_Cu))
            current["restored_victim_count"]+=1
            stage("S1_discrete_victim_returned_"+uid)
        if current["blocked_victim_UUIDs"]:
            data["blocked_victim_UUIDs"].extend(current["blocked_victim_UUIDs"])
            continue
        if current["restored_victim_count"]!=201:
            raise RuntimeError("Incorrect 201 victim restitution ledger")
        if unchanged_fingerprints(board)!=protected:
            raise RuntimeError("Protected pads/zones modified")
        if {t.m_Uuid.AsString() for t in board.GetTracks()
            if isinstance(t,pcbnew.PCB_VIA)}!=vias:
            raise RuntimeError("A via was created or modified")
        post=track_inventory(board)
        if any(post.get(uid)!=v for uid,v in initial_unmodified.items()):
            raise RuntimeError("Non-whitelist original copper modified")
        pcbnew.SaveBoard(str(pcb),board)
        current["scratch_saved_for_native_DRC"]=True
        current["status"]="S1_CH018_all_201_restituted_pending_native_DRC"
        candidates.append((iteration,str(pcb)))
        stage("S1_discrete_201_restituted_board_saved_%d"%iteration)
    data["native_DRC_candidate_paths"]=candidates
    data["source_file_unchanged"]=file_hash(source)==immutable_sha
    data["candidate_saved"]=bool(candidates)
    data["status"]="S1_discrete_candidates_unqualified_no_release"
    stage("S1_discrete_child_finished")
    return data


def run(archive:Path,output:Path) -> dict:
    src_sha=file_hash(archive)
    result={**NO_RELEASE,"status":"S1_discrete_unqualified",
            "source_archive_unchanged":False,
            "baseline_DRC":None,"CH038_pre_return_DRC":None,
            "child_exit_code":None,"child_diagnostic":None,
            "native_candidate_metrics":{},
            "all_201_returned_for_DRC":False}
    def persist() -> None:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2)+"\n")
    persist()
    with tempfile.TemporaryDirectory(prefix="S1-DISCRETE-201-") as temp:
        root=Path(temp)
        source=pinned_source_copy(archive,root)
        baseline=root/"baseline.json"
        result["baseline_DRC"]=isolated_drc(source,baseline)
        if result["baseline_DRC"]!=BASE:
            raise RuntimeError("Pinned 139 source DRC mismatch")
        report=root/"CH038-return.json"
        r=subprocess.run(
            [sys.executable,str(Path(__file__).with_name(
                "probe_block2_ch038_restitution.py")),
             "--child","--source",str(source),
             "--native-baseline",str(baseline),
             "--output",str(report)],
            text=True,capture_output=True,check=False,timeout=135)
        qualification=json.loads(report.read_text()) if report.exists() else {}
        replaced=root/"CH038_PROBE_ONLY"/source.name
        result["CH038_pre_return_exit_code"]=r.returncode
        if (r.returncode!=0 or not qualification.get(
                "ch038_both_replacements_found") or not replaced.exists()):
            result["status"]="CH038_first_return_unqualified_no_release"
            persist()
            return result
        result["CH038_pre_return_DRC"]=isolated_drc(
            replaced,root/"CH038-return-native.json")
        if result["CH038_pre_return_DRC"]!=BASE:
            raise RuntimeError("CH038 pre-return not 139/0/0")
        scratch=root/"s1-child.json"
        try:
            subprocess_result=subprocess.run(
                [sys.executable,str(Path(__file__).resolve()),
                 "--child","--board",str(replaced),
                 "--baseline",str(baseline),
                 "--output",str(scratch)],
                capture_output=True,text=True,check=False,timeout=290)
            result["child_exit_code"]=subprocess_result.returncode
            result["child_stderr_tail"]=subprocess_result.stderr[-1800:]
        except subprocess.TimeoutExpired as exc:
            result["child_exit_code"]=124
            result["child_stderr_tail"]=str(exc)[-1000:]
        if scratch.exists():
            result["child_diagnostic"]=json.loads(scratch.read_text())
        result["source_archive_unchanged"]=file_hash(archive)==src_sha
        w=result["child_diagnostic"] or {}
        if result["child_exit_code"]==0 and result["source_archive_unchanged"]:
            for index,path in w.get("native_DRC_candidate_paths",[]):
                if not Path(path).exists():
                    continue
                metrics=isolated_drc(
                    Path(path),root/("s1-native-%d.json"%index))
                result["native_candidate_metrics"][str(index)]=metrics
                if metrics=={"violations":0,"warnings":0,"unconnected":138}:
                    result["all_201_returned_for_DRC"]=True
        result["status"]=(
            "138_DRC_only_missing_independent_L3_parity_replay_no_release"
            if result["all_201_returned_for_DRC"]
            else "S1_discrete_unqualified_no_release")
        persist()
    return result


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--child",action="store_true")
    p.add_argument("--board",type=Path)
    p.add_argument("--baseline",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.child:
        if args.candidate or not args.board or not args.baseline:
            raise ValueError("Worker requires scratch board and baseline")
        result=worker(args.board,args.baseline,args.output)
    else:
        if not args.candidate or args.board or args.baseline:
            raise ValueError("Supervisor requires pinned candidate only")
        result=run(args.candidate,args.output)
    print(json.dumps({"status":result["status"],
                      "accepted":False,"fabrication_release":False}))


if __name__=="__main__":
    main()

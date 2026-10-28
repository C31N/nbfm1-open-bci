#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Two independent pinned native scratch reruns; never promote or manufacture.

A successful native DRC is insufficient for an independent byte-identical PCB
replay. This gate compares all engineering source members, not ZIP metadata.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from analyze_ch025_fcu_blocker_uuids import ARCHIVE_SHA256, BOARD_SHA256, MEMBERS

REQUIRED = ("accepted", "routing_completed", "fabrication_release",
            "manufacturing_files", "schematic_parity_qualified",
            "independent_replay_verified", "checkpoint_promoted", "In1_Cu_used")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def uuid_difference(a: bytes, b: bytes) -> dict:
    """Diagnose random new item UUIDs without modifying their evidence."""
    expression = rb'\(uuid\s+"?([0-9a-fA-F-]{36})"?\)'
    au = set(re.findall(expression, a))
    bu = set(re.findall(expression, b))
    return {"only_first_count": len(au - bu),
            "only_second_count": len(bu - au),
            "common_count": len(au & bu),
            "first_only_samples": sorted(x.decode() for x in au - bu)[:8],
            "second_only_samples": sorted(x.decode() for x in bu - au)[:8]}


def replay(archive: Path) -> dict:
    result = {
        "accepted": False, "routing_completed": False,
        "fabrication_release": False, "manufacturing_files": False,
        "checkpoint_promoted": False, "schematic_parity_qualified": False,
        "independent_replay_verified": False, "byteidentical_PCB_replay": False,
        "status": "not_started",
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_PCB_sha256": BOARD_SHA256, "replays": [],
        "source_unchanged": False,
    }
    if sha(archive.read_bytes()) != ARCHIVE_SHA256:
        raise RuntimeError("Immutable 139 input ZIP hash changed")
    with tempfile.TemporaryDirectory(prefix="mux-en-independent-replay-") as td:
        root = Path(td)
        evidence = []
        for iteration in (1, 2):
            folder = root / str(iteration)
            folder.mkdir()
            output = folder / "route.json"
            candidate = folder / "engineering-only.zip"
            cmd = [sys.executable,
                   str(Path(__file__).with_name("probe_mux_en_multihop_route.py")),
                   "--archive", str(archive),
                   "--output", str(output),
                   "--candidate-output", str(candidate)]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=900, check=False)
            if proc.returncode != 0 or not output.exists():
                result["status"] = "native_replay_process_failed"
                result["replays"].append({
                    "iteration": iteration, "exit_code": proc.returncode,
                    "stderr_tail": proc.stderr[-1200:]})
                return result
            data = json.loads(output.read_text())
            flags_safe = all(data.get(key) is False for key in REQUIRED)
            native_clean = (
                data.get("candidate_native_DRC") ==
                {"violations": 0, "warnings": 0, "unconnected": 139}
                and data.get("candidate_regressed_nets") == [])
            valid_l3 = (
                data.get("native_L3_both_difference_sets_empty") is True
                and data.get("native_L3_loss_mm2") == 0.0
                and data.get("native_L3_gain_mm2") == 0.0)
            routes = (
                data.get("full_MUX_EN_multihop_routed_on_scratch") is True
                and data.get("CH019_BCu_restituted_on_scratch") is True
                and len(data.get("leg_diagnostics", [])) == 5
                and all(row.get("route_found") is True
                        for row in data["leg_diagnostics"]))
            original_safe = all(data.get(k) is True for k in (
                "source_139_PCB_untouched", "protected_original_tracks_unchanged",
                "protected_original_vias_pads_zones_unchanged",
                "CH027_fixed_via_unchanged"))
            if not candidate.is_file():
                result["status"] = "native_candidate_missing"
                return result
            with zipfile.ZipFile(candidate) as z:
                names = set(z.namelist())
                expected = set(MEMBERS) | {"NO_RELEASE_ENGINEERING_ONLY.json"}
                if names != expected:
                    raise RuntimeError("Unexpected candidate or manufacturing member")
                members = {name: z.read(name) for name in MEMBERS}
                audit = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
            if any(audit.get(k) is not False for k in (
                    "accepted", "routing_completed", "fabrication_release",
                    "routing_replay_byteidentical_verified")):
                raise RuntimeError("Engineering-only audit unexpectedly promoted")
            hashes = {name: sha(content) for name, content in members.items()}
            result["replays"].append({
                "iteration": iteration, "candidate_source_SHA256": hashes,
                "native_DRC_zero_zero": native_clean,
                "native_L3_exact_zero": valid_l3,
                "five_MUX_EN_legs_and_CH019": routes,
                "protected_sources_unchanged": original_safe,
                "release_flags_false": flags_safe,
            })
            if not all((native_clean, valid_l3, routes,
                        original_safe, flags_safe)):
                result["status"] = "native_or_protection_gate_failed"
                return result
            evidence.append(members)
        result["member_byte_identity"] = {
            name: evidence[0][name] == evidence[1][name]
            for name in MEMBERS}
        result["byteidentical_PCB_replay"] = all(
            result["member_byte_identity"].values())
        if not result["byteidentical_PCB_replay"]:
            result["PCB_UUID_difference"] = uuid_difference(
                evidence[0][MEMBERS[0]], evidence[1][MEMBERS[0]])
            result["status"] = "independent_replay_bytes_differ_fail_closed"
        else:
            result["independent_replay_verified"] = True
            result["status"] = "independent_source_byte_replay_qualified_only"
    result["source_unchanged"] = sha(archive.read_bytes()) == ARCHIVE_SHA256
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = replay(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"status": out["status"],
                      "byteidentical": out["byteidentical_PCB_replay"],
                      "accepted": False, "fabrication_release": False}))


if __name__ == "__main__":
    main()

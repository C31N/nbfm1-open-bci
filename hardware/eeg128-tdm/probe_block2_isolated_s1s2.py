#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Process-isolated, no-release cooperative MUX_S1/MUX_S2 diagnostic.

The orchestration process never imports pcbnew or SWIG handles. A single
throwaway child owns the entire candidate search; an independent new Python
process performs KiCad native baseline verification on a fresh source copy.
No routed PCB is persisted and no checkpoint is promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

COHORTS = ("N20P20N24", "P18P24N30")
STRATEGY = "mux-s1s2-first-32"
EXPECTED_BASELINE = {"violations": 0, "warnings": 0, "unconnected": 139}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_source_copy(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if not all(n == Path(n).name and "/" not in n and "\\" not in n
                   for n in names):
            raise RuntimeError("Reject nonflat engineering archive")
        boards = [n for n in names if n.endswith(".kicad_pcb")]
        if len(boards) != 1:
            raise RuntimeError("Expected exactly one PCB")
        project = str(Path(boards[0]).with_suffix(".kicad_pro"))
        if project not in names:
            raise RuntimeError("Missing pinned project for DRC")
        if "NO_RELEASE_ENGINEERING_ONLY.json" not in names:
            raise RuntimeError("No protected no-release metadata")
        metadata = json.loads(z.read("NO_RELEASE_ENGINEERING_ONLY.json"))
        if any(metadata.get(flag) is not False for flag in (
                "accepted", "routing_completed", "fabrication_release",
                "routing_replay_byteidentical_verified")):
            raise RuntimeError("Engineering archive release lock drift")
        for name in names:
            if name.endswith((".kicad_pcb", ".kicad_pro", ".kicad_sch")):
                (destination / name).write_bytes(z.read(name))
        return destination / boards[0]


def subprocess_baseline(board: Path, destination: Path) -> dict:
    source_dir = str(Path(__file__).resolve().parent)
    verifier = (
        "import json,sys;"
        "from pathlib import Path;"
        "sys.path.insert(0,sys.argv[1]);"
        "from route_targeted_closure import native,metrics;"
        "print(json.dumps(metrics(native(Path(sys.argv[2]),Path(sys.argv[3])))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", verifier, source_dir, str(board),
         str(destination)],
        capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError("Isolated baseline DRC failed: " +
                           result.stderr[-1600:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def run(candidate: Path, cohort: str, output: Path) -> dict:
    if cohort not in COHORTS:
        raise ValueError("Unreviewed coupled-victim cohort")
    original = sha(candidate)
    record = {
        "cohort": cohort,
        "strategy": STRATEGY,
        "status": "isolated_trial_not_verified",
        "baseline_DRC": None,
        "source_archive_unchanged": False,
        "worker_exit_code": None,
        "worker_trial": None,
        "worker_scratch_discarded": False,
        "parent_natively_reverified": False,
        "native_136_qualified": False,
        "accepted": False, "routing_completed": False,
        "fabrication_release": False, "manufacturing_files": False,
        "checkpoint_promoted": False,
        "schematic_parity_qualified": False,
        "independent_replay_verified": False,
        "new_vias_added": 0,
    }

    def persist() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n")

    persist()
    with tempfile.TemporaryDirectory(prefix="block2-S1S2-isolated-") as tmp:
        scratch = Path(tmp)
        original_board = pinned_source_copy(candidate, scratch)
        worker_file = scratch / "disposable-child.json"
        worker = subprocess.run(
            [sys.executable,
             str(Path(__file__).with_name("probe_block2_deep_fcu_multinet.py")),
             "--candidate", str(candidate),
             "--cohort", cohort,
             "--single-strategy", STRATEGY,
             "--disposable-worker",
             "--output", str(worker_file)],
            capture_output=True, text=True, check=False, timeout=260)
        record["worker_exit_code"] = worker.returncode
        record["worker_stderr_tail"] = worker.stderr[-1600:]
        record["worker_stdout_tail"] = worker.stdout[-900:]
        if worker_file.exists():
            partial = json.loads(worker_file.read_text())
            record["worker_trial"] = partial["trials"][-1] if partial.get("trials") else None
            record["worker_report_status"] = partial.get("status")
            record["worker_source_archive_unchanged"] = partial.get(
                "source_archive_unchanged")
        record["source_archive_unchanged"] = sha(candidate) == original
        persist()
        # Native PCB loading and filled-zone DRC happen in a SEPARATE Python
        # process, never in the just-exited trial worker or this supervisor.
        record["baseline_DRC"] = subprocess_baseline(
            original_board, scratch / "independent-source-native.json")
        record["parent_natively_reverified"] = (
            record["baseline_DRC"] == EXPECTED_BASELINE)
        record["worker_scratch_discarded"] = True
        trial = record["worker_trial"] or {}
        is_good = (
            worker.returncode == 0
            and record["worker_source_archive_unchanged"] is True
            and record["source_archive_unchanged"]
            and record["parent_natively_reverified"]
            and trial.get("worker_scratch_discard_required") is True
            and trial.get("new_vias", 0) == 0
            and not trial.get("candidate_136_qualified", False)
        )
        record["status"] = (
            "isolated_S1S2_diagnostic_complete_no_release"
            if is_good else "isolated_S1S2_diagnostic_rejected_no_release")
        persist()
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cohort", choices=COHORTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.candidate, args.cohort, args.output)
    print(json.dumps({
        "status": report["status"],
        "cohort": report["cohort"], "accepted": False,
        "fabrication_release": False}))
    if report["status"] != "isolated_S1S2_diagnostic_complete_no_release":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

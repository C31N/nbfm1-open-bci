#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reject stale engineering routing checkpoints before continuing routing."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from verify_hardware_identity import footprint_blocks


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry(block: str) -> tuple[object, ...]:
    # Generated footprint UUIDs and <=10 nm serialization rounding may differ.
    block = re.sub(r'\(uuid "[^"\n]+"\)', '(uuid)', block)
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', block)
    return tuple(round(float(t), 5) if re.fullmatch(r'-?\d+\.\d+', t) else t for t in tokens)


def verify(source: Path, checkpoint: Path, metadata: Path) -> None:
    status = json.loads(metadata.read_text())
    root = source.parent
    files = {
        "source_sha256": source,
        "checkpoint_sha256": checkpoint,
        "project_sha256": root / "eeg128-tdm.kicad_pro",
        "rules_sha256": root / "eeg128-tdm.kicad_dru",
        "native_drc_sha256": metadata.parent / "drc-checkpoint.json",
    }
    for key, path in files.items():
        if status.get(key) != digest(path):
            raise RuntimeError(f"stale routing checkpoint: {key} does not match {path}")
    report = json.loads((metadata.parent / "drc-checkpoint.json").read_text())
    if report.get("violations") != [] or len(report["unconnected_items"]) != status["unconnected"]:
        raise RuntimeError("checkpoint report does not match recorded native metrics")
    original = footprint_blocks(source.read_text())
    candidate = footprint_blocks(checkpoint.read_text())
    if set(original) != set(candidate) or len(candidate) != 642:
        raise RuntimeError("checkpoint footprint references differ from primary PCB")
    for ref in original:
        if geometry(original[ref]) != geometry(candidate[ref]):
            raise RuntimeError(f"checkpoint changed footprint geometry or pin mapping: {ref}")
    if status.get("violation_errors") != 0 or status.get("warnings") != 0:
        raise RuntimeError("checkpoint is not geometrically clean")
    print(json.dumps({"checkpoint": str(checkpoint), "footprints_verified": 642,
                      "expected_unconnected": status["unconnected"], "result": "PASS"}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    verify(args.source, args.checkpoint, args.metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

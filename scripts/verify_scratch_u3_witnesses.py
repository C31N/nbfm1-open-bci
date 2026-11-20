#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only KiCad 8.0.9 scratch-PCB UUID and geometric clearance audit.

For the *real* on-disk NBODY post-201-cut PCB, not a JSON snapshot
from the 139-airwire reference board. No pcbnew board mutations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware" / "eeg128-tdm"))
from probe_block2_scratch_verify import analyze_scratch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-board", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path,
                        help="Nbody worker JSON with 201/CH038 UUID inventory")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    worker = json.loads(args.inventory.read_text(encoding="utf-8"))
    removed = set(worker["cut_whitelist_UUIDs"])
    replaced = set(worker["CH038_cut_UUIDs"])
    result = analyze_scratch(
        args.scratch_board, removed, replaced,
        expected_sha256=worker["post_201_cut_scratch_sha256"])
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": "SCRATCH_FCU_READ_ONLY_AUDITED",
        "pcb_sha256": result["scratch_board_sha256_before_and_after"],
        "present_pad_UUIDs": [
            x["uuid"] for x in result["u3_witnesses"]
            if x["present_in_scratch"]],
        "victim_uuids_present_after_cut":
            len(result["victim_uuids_present_after_cut"]),
        "direction_counts": result["scratch_direction_counts"],
        "accepted": False, "routing_completed": False,
        "fabrication_release": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()

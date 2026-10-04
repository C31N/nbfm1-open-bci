#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent
PCB = ROOT / "eeg128-tdm.kicad_pcb"
SCH = ROOT / "eeg128-tdm.kicad_sch"
STATUS = ROOT / "RELEASE_STATUS.json"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def require_release() -> dict[str, object]:
    status: dict[str, object] = json.loads(STATUS.read_text(encoding="utf-8"))
    required_true = (
        "fabrication_release",
        "routing_completed",
        "footprints_verified",
        "erc_passed",
        "drc_passed",
        "bom_cpl_crosscheck_passed",
    )
    false_keys = [key for key in required_true if not bool(status.get(key))]
    if false_keys:
        raise RuntimeError(
            "manufacturing export blocked by RELEASE_STATUS.json; "
            f"false release gates: {', '.join(false_keys)}"
        )
    return status


def require_kicad8() -> None:
    output = subprocess.check_output(["kicad-cli", "--version"], text=True).strip()
    if not output.startswith("8."):
        raise RuntimeError(f"KiCad 8 required for reproducible release, found {output}")


def compare_cpl(generated_path: Path) -> None:
    expected_path = ROOT / "CPL.csv"
    with expected_path.open(newline="", encoding="utf-8") as handle:
        expected = {row["Designator"]: row for row in csv.DictReader(handle)}
    with generated_path.open(newline="", encoding="utf-8") as handle:
        actual = list(csv.DictReader(handle))
    actual_refs = {
        row.get("Ref")
        or row.get("Designator")
        or row.get("Reference")
        or ""
        for row in actual
    }
    missing = sorted(set(expected) - actual_refs)
    if missing:
        raise RuntimeError(
            "KiCad placement export does not contain all expected designators: "
            + ", ".join(missing[:20])
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "manufacturing"))
    args = parser.parse_args()

    require_release()
    require_kicad8()

    run(["python3", "validate_eda.py", "--kicad-release-checks"])

    out = Path(args.output).resolve()
    gerbers = out / "gerbers"
    if out.exists():
        shutil.rmtree(out)
    gerbers.mkdir(parents=True)

    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "gerbers",
            "--layers",
            "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts",
            "--output",
            str(gerbers),
            str(PCB),
        ]
    )
    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "drill",
            "--output",
            str(gerbers),
            str(PCB),
        ]
    )

    kicad_cpl = out / "CPL-kicad.csv"
    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "pos",
            "--format",
            "csv",
            "--units",
            "mm",
            "--smd-only",
            "--exclude-dnp",
            "--output",
            str(kicad_cpl),
            str(PCB),
        ]
    )
    compare_cpl(kicad_cpl)

    shutil.copy2(ROOT / "BOM.csv", out / "BOM.csv")
    shutil.copy2(ROOT / "CPL.csv", out / "CPL.csv")
    shutil.copy2(ROOT / "NETLIST.csv", out / "NETLIST.csv")
    shutil.copy2(STATUS, out / "RELEASE_STATUS.json")

    archive = out / "JLCPCB-eeg128-tdm-A0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(gerbers.rglob("*")):
            if path.is_file():
                zf.write(path, Path("gerbers") / path.relative_to(gerbers))
        for name in ("BOM.csv", "CPL.csv", "NETLIST.csv", "RELEASE_STATUS.json"):
            zf.write(out / name, name)

    print(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())

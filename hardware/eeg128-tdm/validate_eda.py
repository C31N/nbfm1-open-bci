#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "BOM.csv",
    "CPL.csv",
    "NETLIST.csv",
    "design_spec.yaml",
    "eeg128-tdm.kicad_sch",
    "eeg128-tdm.kicad_pcb",
    "eeg128-tdm.kicad_pro",
    "RELEASE_STATUS.json",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def expand_designators(text: str) -> set[str]:
    return {item.strip() for item in text.split(",") if item.strip()}


def bom_designators(rows: Iterable[dict[str, str]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        result |= expand_designators(row["Designator"])
    return result


def cpl_designators(rows: Iterable[dict[str, str]]) -> set[str]:
    return {row["Designator"].strip() for row in rows}


def validate_required_files() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        fail(f"missing EDA source files: {', '.join(missing)}")


def validate_bom_cpl() -> None:
    bom = read_csv(ROOT / "BOM.csv")
    cpl = read_csv(ROOT / "CPL.csv")
    bom_refs = bom_designators(bom)
    cpl_refs = cpl_designators(cpl)

    if bom_refs != cpl_refs:
        missing_cpl = sorted(bom_refs - cpl_refs)
        extra_cpl = sorted(cpl_refs - bom_refs)
        fail(
            "BOM/CPL designator mismatch: "
            f"missing_in_cpl={missing_cpl}, extra_in_cpl={extra_cpl}"
        )

    expected = {
        *(f"U{i}" for i in range(1, 28)),
        *(f"J{i}" for i in range(1, 12)),
        "Y1",
        *(f"R{i}" for i in range(1, 538)),
        *(f"C{i}" for i in range(1, 65)),
    }
    if bom_refs != expected:
        fail(
            f"unexpected BOM reference set: expected {len(expected)} references, "
            f"got {len(bom_refs)}"
        )

    adc_rows = [row for row in bom if "ADS131M08" in row["Manufacturer Part #"]]
    if len(adc_rows) != 1:
        fail("BOM must contain exactly one ADS131M08")
    adc = adc_rows[0]
    if adc["LCSC Part #"] != "C2862610":
        fail("ADS131M08 LCSC part must be C2862610")
    if adc["Footprint"] != "TQFP-32_5x5mm_P0.5mm":
        fail("ADS131M08IPBSR footprint must be TQFP-32 5x5 mm, 0.5 mm pitch")


def validate_netlist() -> None:
    rows = read_csv(ROOT / "NETLIST.csv")
    text = (ROOT / "NETLIST.csv").read_text(encoding="utf-8")

    for channel in range(128):
        name = f"CH{channel:03d}"
        for polarity in ("P", "N"):
            if f"{name}_{polarity}_ELECTRODE" not in text:
                fail(f"missing electrode net for {name}_{polarity}")
            if f"{name}_{polarity}_MUX" not in text:
                fail(f"missing mux net for {name}_{polarity}")

    required_nets = {
        "MUX_S0",
        "MUX_S1",
        "MUX_S2",
        "MUX_S3",
        "MUX_EN",
        "ADC_SCLK",
        "ADC_DIN",
        "ADC_DOUT",
        "ADC_CS",
        "ADC_DRDY",
        "ADC_SYNC_RESET",
        "ADC_CLKIN",
        "VCM",
        "DRL",
        "CMS1",
        "CMS2",
        "3V3A",
        "3V3D",
        "AGND",
        "DGND",
    }
    present = {row["Net"] for row in rows}
    missing = sorted(required_nets - present)
    if missing:
        fail(f"missing required logical nets: {missing}")


def validate_kicad_sources() -> None:
    sch = (ROOT / "eeg128-tdm.kicad_sch").read_text(encoding="utf-8")
    pcb = (ROOT / "eeg128-tdm.kicad_pcb").read_text(encoding="utf-8")
    if "(version 20231120)" not in sch:
        fail("schematic is not KiCad 8 schematic format")
    if "(version 20240108)" not in pcb:
        fail("PCB is not KiCad 8 PCB format")
    for layer in ('"F.Cu"', '"In1.Cu"', '"In2.Cu"', '"B.Cu"', '"Edge.Cuts"'):
        if layer not in pcb:
            fail(f"PCB missing required layer {layer}")
    if pcb.count("(footprint ") < 600:
        fail("PCB unexpectedly contains fewer than 600 footprint instances")
    if 'TQFP-32_5x5mm_P0.5mm' not in (ROOT / "BOM.csv").read_text(encoding="utf-8"):
        fail("ADC package audit failed")


def run_checked(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def kicad_major_version() -> int:
    output = subprocess.check_output(["kicad-cli", "--version"], text=True).strip()
    match = re.match(r"(\d+)", output)
    if match is None:
        fail(f"cannot parse kicad-cli version: {output!r}")
    return int(match.group(1))


def run_kicad_release_checks() -> None:
    if kicad_major_version() != 8:
        fail("manufacturing release validation requires KiCad CLI major version 8")
    run_checked(
        [
            "kicad-cli",
            "sch",
            "erc",
            "--exit-code-violations",
            "eeg128-tdm.kicad_sch",
        ]
    )
    run_checked(
        [
            "kicad-cli",
            "pcb",
            "drc",
            "--exit-code-violations",
            "--schematic-parity",
            "eeg128-tdm.kicad_pcb",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kicad-release-checks",
        action="store_true",
        help="also require KiCad 8 ERC and DRC to pass",
    )
    args = parser.parse_args()

    validate_required_files()
    validate_bom_cpl()
    validate_netlist()
    validate_kicad_sources()

    status = json.loads((ROOT / "RELEASE_STATUS.json").read_text(encoding="utf-8"))
    if args.kicad_release_checks:
        run_kicad_release_checks()

    print(
        json.dumps(
            {
                "source_validation": "PASS",
                "revision": status["revision"],
                "fabrication_release": bool(status["fabrication_release"]),
                "routing_completed": bool(status["routing_completed"]),
                "footprints_verified": bool(status["footprints_verified"]),
                "erc_passed": bool(status["erc_passed"]),
                "drc_passed": bool(status["drc_passed"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

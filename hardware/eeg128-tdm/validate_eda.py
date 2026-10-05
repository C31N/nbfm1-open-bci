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
    "EDA_AUDIT.md",
    "COMPONENT_AUDIT.md",
)

LCSC_RE = re.compile(r"^C[0-9]+$")


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

    seen: set[str] = set()
    for row in bom:
        refs = expand_designators(row["Designator"])
        duplicates = refs & seen
        if duplicates:
            fail(f"duplicate BOM designators: {sorted(duplicates)}")
        seen |= refs

        try:
            quantity = int(row["Qty"])
        except ValueError as exc:
            raise RuntimeError(f"invalid BOM quantity for {row['Designator']}") from exc
        if quantity != len(refs):
            fail(
                f"BOM quantity mismatch for {row['Designator']}: "
                f"Qty={quantity}, designators={len(refs)}"
            )

        lcsc = row["LCSC Part #"].strip()
        if not LCSC_RE.fullmatch(lcsc):
            fail(f"invalid LCSC part identifier {lcsc!r} for {row['Designator']}")

    adc_rows = [row for row in bom if row["Manufacturer Part #"] == "ADS131M08IPBSR"]
    if len(adc_rows) != 1:
        fail("BOM must contain exactly one ADS131M08IPBSR")
    adc = adc_rows[0]
    if adc["LCSC Part #"] != "C2862610":
        fail("ADS131M08 LCSC part must be C2862610")
    if adc["Footprint"] != "TQFP-32_5x5mm_P0.5mm":
        fail(
            "ADS131M08IPBSR must use the TI PBS geometry: "
            "32-pin TQFP, approximately 5x5 mm body, 0.50 mm pitch"
        )


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
        "ADC_REFIN",
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


def source_metrics() -> dict[str, int]:
    sch = (ROOT / "eeg128-tdm.kicad_sch").read_text(encoding="utf-8")
    pcb = (ROOT / "eeg128-tdm.kicad_pcb").read_text(encoding="utf-8")
    return {
        "schematic_instantiated_symbols": len(
            re.findall(r"(?m)^  \(symbol\b", sch)
        ),
        "schematic_wires": len(re.findall(r"(?m)^  \(wire\b", sch)),
        "pcb_footprints": len(re.findall(r"(?m)^  \(footprint\b", pcb)),
        "pcb_segments": len(re.findall(r"(?m)^  \(segment\b", pcb)),
        "pcb_vias": len(re.findall(r"(?m)^  \(via\b", pcb)),
        "pcb_zones": len(re.findall(r"(?m)^  \(zone\b", pcb)),
    }


def validate_kicad_sources() -> dict[str, int]:
    sch = (ROOT / "eeg128-tdm.kicad_sch").read_text(encoding="utf-8")
    pcb = (ROOT / "eeg128-tdm.kicad_pcb").read_text(encoding="utf-8")

    if "(version 20231120)" not in sch:
        fail("schematic is not KiCad 8 schematic format")
    if "(version 20240108)" not in pcb:
        fail("PCB is not KiCad 8 PCB format")

    for layer in ('"F.Cu"', '"In1.Cu"', '"In2.Cu"', '"B.Cu"', '"Edge.Cuts"'):
        if layer not in pcb:
            fail(f"PCB missing required layer {layer}")

    metrics = source_metrics()
    if metrics["pcb_footprints"] < 600:
        fail("PCB unexpectedly contains fewer than 600 footprint instances")

    return metrics


def release_gate_failures(
    status: dict[str, object],
    metrics: dict[str, int],
) -> list[str]:
    failures: list[str] = []

    bool_gates = (
        "schematic_complete",
        "routing_completed",
        "copper_zones_completed",
        "ground_strategy_resolved",
        "footprints_verified",
        "erc_passed",
        "drc_passed",
        "schematic_parity_passed",
        "bom_cpl_crosscheck_passed",
        "gerber_visual_review_passed",
        "isolated_bench_bringup_passed",
        "noise_settling_validation_passed",
    )
    failures.extend(key for key in bool_gates if not bool(status.get(key)))

    if metrics["schematic_instantiated_symbols"] < 30:
        failures.append("schematic_has_too_few_instantiated_symbols")
    if metrics["schematic_wires"] < 30:
        failures.append("schematic_has_too_few_wires")
    if metrics["pcb_segments"] < 100:
        failures.append("pcb_has_too_few_routed_segments")
    if metrics["pcb_vias"] < 1:
        failures.append("pcb_has_no_vias")
    if metrics["pcb_zones"] < 1:
        failures.append("pcb_has_no_copper_zones")

    return failures


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
    parser.add_argument(
        "--fabrication-ready",
        action="store_true",
        help="fail unless all physical release gates and source-completeness checks pass",
    )
    args = parser.parse_args()

    validate_required_files()
    validate_bom_cpl()
    validate_netlist()
    metrics = validate_kicad_sources()

    status: dict[str, object] = json.loads(
        (ROOT / "RELEASE_STATUS.json").read_text(encoding="utf-8")
    )

    if bool(status.get("fabrication_release")) or args.fabrication_ready:
        failures = release_gate_failures(status, metrics)
        if failures:
            fail("fabrication release blocked: " + ", ".join(sorted(set(failures))))
        if not args.kicad_release_checks:
            fail(
                "fabrication-ready validation requires --kicad-release-checks "
                "so ERC/DRC are executed in the current environment"
            )

    if args.kicad_release_checks:
        run_kicad_release_checks()

    print(
        json.dumps(
            {
                "source_validation": "PASS",
                "revision": status["revision"],
                "fabrication_release": bool(status["fabrication_release"]),
                "human_connected_use_authorized": bool(
                    status["human_connected_use_authorized"]
                ),
                "metrics": metrics,
                "release_gate_failures": release_gate_failures(status, metrics),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

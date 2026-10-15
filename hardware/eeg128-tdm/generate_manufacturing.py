#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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
    false_keys = [key for key in required_true if status.get(key) is not True]
    if false_keys:
        raise RuntimeError(
            "manufacturing export blocked by RELEASE_STATUS.json; "
            f"false release gates: {', '.join(false_keys)}"
        )
    return status


def require_clean_drc(report: dict[str, object]) -> None:
    """Missing lists, excluded violations and malformed reports fail closed."""
    for key in ('violations', 'unconnected_items', 'schematic_parity'):
        if not isinstance(report.get(key), list) or report[key]:
            raise RuntimeError(f'Manufacturing blocked: {key} must be an empty list')
    if not str(report.get('kicad_version', '')).startswith('8.'):
        raise RuntimeError('Manufacturing blocked: native KiCad 8 report required')


def native_release_preflight(status: dict[str, object]) -> dict[str, bytes]:
    """Check exact immutable inputs; never export from a stale DRC report."""
    paths = [PCB, SCH, PCB.with_suffix('.kicad_pro'), PCB.with_suffix('.kicad_dru'),
             ROOT/'BOM.csv', ROOT/'CPL.csv', ROOT/'NETLIST.csv']
    snapshot = {p.name: p.read_bytes() for p in paths}
    hashes = {name: hashlib.sha256(data).hexdigest() for name,data in snapshot.items()}
    if status.get('manufacturing_source_sha256') != hashes:
        raise RuntimeError('Manufacturing blocked: reviewed source hashes missing or stale')
    loss = status.get('baseline_l3_power_loss_mm2')
    if type(loss) not in (int,float) or loss != 0:
        raise RuntimeError('Manufacturing blocked: reviewed zero L3-power-loss evidence absent')
    with tempfile.TemporaryDirectory(prefix='eeg128-release-audit-') as directory:
        folder = Path(directory)
        for name,data in snapshot.items():
            (folder/name).write_bytes(data)
        board = folder/PCB.name
        run([sys.executable, str(ROOT/'fill_zones.py'), '--require-four-layer', str(board)])
        if hashlib.sha256(board.read_bytes()).hexdigest() != hashes[PCB.name]:
            raise RuntimeError('Manufacturing blocked: zone refill changed reviewed PCB')
        report = folder/'drc.json'
        run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all',
             '--all-track-errors', '--format', 'json', '--output', str(report), str(board)])
        require_clean_drc(json.loads(report.read_text()))
        run([sys.executable,str(ROOT/'audit_release_power.py'),'--board',str(board),
             '--output',str(folder/'power.json')])
    if hashes != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}:
        raise RuntimeError('Manufacturing inputs changed during preflight')
    return snapshot


def require_kicad8() -> None:
    output = subprocess.check_output(["kicad-cli", "--version"], text=True).strip()
    if not output.startswith("8."):
        raise RuntimeError(f"KiCad 8 required for reproducible release, found {output}")


def compare_cpl(generated_path: Path, expected_path: Path) -> None:
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
    if actual_refs != set(expected) or len(actual) != len(expected):
        raise RuntimeError(
            "KiCad placement designators differ from reviewed CPL or are duplicated"
        )


def write_jlc_cpl(generated_path: Path, output: Path, expected_path: Path) -> None:
    compare_cpl(generated_path,expected_path)
    with generated_path.open(newline='',encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    converted = []
    for row in rows:
        x,y,rotation = (float(row[key]) for key in ('PosX','PosY','Rot'))
        side = {'top':'Top','bottom':'Bottom'}[row['Side'].lower()]
        if not all(math.isfinite(value) for value in (x,y,rotation)):
            raise RuntimeError('Nonfinite native placement coordinate')
        converted.append([row['Ref'],f'{x:.6f}mm',f'{y:.6f}mm',side,f'{rotation%360:.6f}'])
    with output.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Designator','Mid X','Mid Y','Layer','Rotation'])
        writer.writerows(converted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "manufacturing"))
    parser.add_argument('--assert-blocked', action='store_true',
                        help='CI: prove current release flags block before any export')
    args = parser.parse_args()

    try:
        status = require_release()
    except RuntimeError:
        if args.assert_blocked:
            print('Manufacturing is blocked; no artifacts created')
            return 0
        raise
    if args.assert_blocked:
        raise RuntimeError('Expected fabrication lock is absent')
    require_kicad8()
    snapshot = native_release_preflight(status)

    run(
        [
            "python3",
            "validate_eda.py",
            "--fabrication-ready",
            "--kicad-release-checks",
        ]
    )

    out = Path(args.output).resolve()
    gerbers = out / "gerbers"
    if out.exists():
        raise RuntimeError('Refusing to overwrite an existing export directory')
    gerbers.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="eeg128-approved-sources-") as directory:
        source_root = Path(directory)
        for name, data in snapshot.items():
            (source_root/name).write_bytes(data)
        release_pcb = source_root/PCB.name
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
                str(release_pcb),
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
                str(release_pcb),
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
                str(release_pcb),
            ]
        )
        write_jlc_cpl(kicad_cpl,out/'CPL.csv',source_root/'CPL.csv')

        shutil.copy2(source_root / "BOM.csv", out / "BOM.csv")
        shutil.copy2(source_root / "NETLIST.csv", out / "NETLIST.csv")
        (out / "RELEASE_STATUS.json").write_text(json.dumps(status, indent=2)+"\n")

        manifest = out / "SHA256SUMS"
        payload_files = [
            out / "BOM.csv",
            out / "CPL.csv",
            out / "NETLIST.csv",
            out / "RELEASE_STATUS.json",
            *sorted(path for path in gerbers.rglob("*") if path.is_file()),
        ]
        import hashlib

        with manifest.open("w", encoding="utf-8") as handle:
            for path in payload_files:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                handle.write(f"{digest}  {path.relative_to(out).as_posix()}\n")

        archive = out / "JLCPCB-eeg128-tdm-A0.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(gerbers.rglob("*")):
                if path.is_file():
                    zf.write(path, Path("gerbers") / path.relative_to(gerbers))
            for name in (
                "BOM.csv",
                "CPL.csv",
                "NETLIST.csv",
                "RELEASE_STATUS.json",
                "SHA256SUMS",
            ):
                zf.write(out / name, name)

        print(archive)
        return 0


if __name__ == "__main__":
    sys.exit(main())

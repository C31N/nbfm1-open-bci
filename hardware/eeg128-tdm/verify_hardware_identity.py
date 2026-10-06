#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
LCSC_RE = re.compile(r"^C[0-9]+$")

APPROVED_PARTS: dict[str, tuple[str, str]] = {
    "CD74HC4067M96": ("C496123", "SOIC-24_7.5x15.4mm_P1.27mm"),
    "TLV9064IPWR": ("C779410", "TSSOP-14_4.4x5mm_P0.65mm"),
    "ADS131M08IPBSR": ("C2862610", "TQFP-32_5x5mm_P0.5mm"),
    "OPA4171AIPWR": ("C529553", "TSSOP-14_4.4x5mm_P0.65mm"),
    "RP2040": ("C2040", "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm"),
    "TPS7A2033PDBVR": ("C2862740", "SOT-23-5"),
    "AP2112K-3.3TRG1": ("C51118", "SOT-23-5"),
    "W25Q16JVSSIQ": ("C82317", "SOIC-8_5.3x5.3mm_P1.27mm"),
    "OT2JI-111-8.192M": ("C7425393", "SMD3225-4P"),
    "0.5K-QX-32PWB": ("C2919488", "FPC_32P_P0.5mm_RA"),
    "TYPE-C-31-M-12": ("C165948", "USB-C-16P_RA"),
    "S4B-PH-SM4-TB(LF)(SN)": ("C265102", "JST_PH_4P_RA_2.0mm"),
    "S2B-PH-SM4-TB(LF)(SN)": ("C295747", "JST_PH_2P_RA_2.0mm"),
    "X322512MSB4SI": ("C9002", "Crystal_SMD_3225-4Pin"),
    "RCS060310M0FKEA": ("C2092526", "R_0603_1608Metric"),
    "TC0325F1003T5F": ("C2989131", "R_0603_1608Metric"),
    "0603WAF1000T5E": ("C22775", "R_0603_1608Metric"),
    "0603WAF1002T5E": ("C25804", "R_0603_1608Metric"),
    "RC0603FR-0727RL": ("C137753", "R_0603_1608Metric"),
    "RC0603FR-071ML": ("C105578", "R_0603_1608Metric"),
    "RC0603FR-07470KL": ("C114622", "R_0603_1608Metric"),
    "0603WAF5101T5E": ("C23186", "R_0603_1608Metric"),
    "CL10A105KB8NNNC": ("C15849", "C_0603_1608Metric"),
    "CC0603KRX7R9BB104": ("C14663", "C_0603_1608Metric"),
    "CL10B224KO8SFNC": ("C3894271", "C_0603_1608Metric"),
    "0603B103K500NT": ("C57112", "C_0603_1608Metric"),
    "CL10C150JB81PNC": ("C346207", "C_0603_1608Metric"),
}

CRITICAL_FOOTPRINTS: dict[str, str] = {
    **{f"U{i}": "SOIC-24W_7.5x15.4mm_P1.27mm" for i in range(1, 17)},
    **{f"U{i}": "TSSOP-14_4.4x5mm_P0.65mm" for i in range(17, 21)},
    "U21": "TI_PBS_S-PQFP-G32_5x5mm_P0.5mm",
    "U23": "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def refs(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def balanced_blocks(text: str, token: str) -> list[str]:
    needle = f"({token} "
    result: list[str] = []
    cursor = 0
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            return result
        depth = 0
        in_string = False
        escaped = False
        end = start
        while end < len(text):
            char = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1
        result.append(text[start:end])
        cursor = end


def footprint_blocks(pcb: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for block in balanced_blocks(pcb, "footprint"):
        match = re.search(r'\(property "Reference" "([^"]+)"', block)
        if match:
            result[match.group(1)] = block
    return result


def footprint_name(block: str) -> str:
    match = re.match(r'\(footprint "([^"]+)"', block)
    if not match:
        raise RuntimeError("footprint block has no library identifier")
    return match.group(1).split(":")[-1]


def pad_nets(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pad in balanced_blocks(block, "pad"):
        number = re.match(r'\(pad "([^"]+)"', pad)
        if not number:
            continue
        net = re.search(r'\(net\s+\d+\s+"([^"]+)"\)', pad)
        name = net.group(1) if net else ""
        previous = result.get(number.group(1), "")
        if previous and name and previous != name:
            raise RuntimeError(
                f"pad {number.group(1)} is assigned to {previous!r} and {name!r}"
            )
        if name:
            result[number.group(1)] = name
        else:
            result.setdefault(number.group(1), "")
    return result


def require_map(
    actual: dict[str, str],
    expected: dict[str, str],
    reference: str,
) -> None:
    for pin, net in expected.items():
        if actual.get(pin, "") != net:
            raise RuntimeError(
                f"{reference}.{pin}: expected {net!r}, got {actual.get(pin, '')!r}"
            )


def verify_bom_cpl() -> dict[str, object]:
    bom = read_csv(ROOT / "BOM.csv")
    cpl = read_csv(ROOT / "CPL.csv")
    all_refs: list[str] = []
    verified_rows = 0

    for row in bom:
        designators = refs(row["Designator"])
        quantity = int(row["Qty"])
        if quantity != len(designators):
            raise RuntimeError(
                f"{row['Manufacturer Part #']}: Qty={quantity}, "
                f"designators={len(designators)}"
            )
        mpn = row["Manufacturer Part #"].strip()
        if mpn not in APPROVED_PARTS:
            raise RuntimeError(f"unapproved MPN in BOM: {mpn}")
        lcsc, footprint = APPROVED_PARTS[mpn]
        if row["LCSC Part #"].strip() != lcsc:
            raise RuntimeError(
                f"{mpn}: expected LCSC {lcsc}, got {row['LCSC Part #']}"
            )
        if row["Footprint"].strip() != footprint:
            raise RuntimeError(
                f"{mpn}: expected footprint {footprint}, got {row['Footprint']}"
            )
        if not LCSC_RE.fullmatch(lcsc):
            raise RuntimeError(f"invalid LCSC identifier {lcsc}")
        all_refs.extend(designators)
        verified_rows += 1

    if len(all_refs) != 642 or len(set(all_refs)) != 642:
        raise RuntimeError(
            f"BOM must expand to 642 unique placements, got "
            f"{len(all_refs)} entries / {len(set(all_refs))} unique"
        )

    cpl_refs = [row["Designator"].strip() for row in cpl]
    if len(cpl_refs) != 642 or len(set(cpl_refs)) != 642:
        raise RuntimeError(
            f"CPL must contain 642 unique placements, got "
            f"{len(cpl_refs)} entries / {len(set(cpl_refs))} unique"
        )
    if set(all_refs) != set(cpl_refs):
        missing = sorted(set(all_refs) - set(cpl_refs))
        extra = sorted(set(cpl_refs) - set(all_refs))
        raise RuntimeError(
            f"BOM/CPL parity failed: missing={missing[:10]}, extra={extra[:10]}"
        )

    return {
        "bom_rows_verified": verified_rows,
        "placements_verified": len(all_refs),
        "cpl_rows_verified": len(cpl_refs),
        "approved_lcsc_mappings": len(APPROVED_PARTS),
    }


def verify_muxes(blocks: dict[str, str]) -> None:
    for bank in range(8):
        for polarity, offset in (("P", 1), ("N", 2)):
            reference = f"U{2 * bank + offset}"
            actual = pad_nets(blocks[reference])
            expected = {
                "1": f"BANK{bank}_{polarity}_MUX_OUT",
                "10": "MUX_S0",
                "11": "MUX_S1",
                "12": "AGND",
                "13": "MUX_S3",
                "14": "MUX_S2",
                "15": "MUX_EN",
                "24": "3V3A",
            }
            for local in range(8):
                expected[str(9 - local)] = (
                    f"CH{bank * 16 + local:03d}_{polarity}_MUX"
                )
            for local in range(8, 16):
                expected[str(31 - local)] = (
                    f"CH{bank * 16 + local:03d}_{polarity}_MUX"
                )
            require_map(actual, expected, reference)


def verify_buffers(blocks: dict[str, str]) -> None:
    for index in range(4):
        reference = f"U{17 + index}"
        bank_a = 2 * index
        bank_b = bank_a + 1
        expected = {
            "1": f"BANK{bank_a}_P_BUFFER",
            "2": f"BANK{bank_a}_P_BUFFER",
            "3": f"BANK{bank_a}_P_MUX_OUT",
            "4": "3V3A",
            "5": f"BANK{bank_a}_N_MUX_OUT",
            "6": f"BANK{bank_a}_N_BUFFER",
            "7": f"BANK{bank_a}_N_BUFFER",
            "8": f"BANK{bank_b}_P_BUFFER",
            "9": f"BANK{bank_b}_P_BUFFER",
            "10": f"BANK{bank_b}_P_MUX_OUT",
            "11": "AGND",
            "12": f"BANK{bank_b}_N_MUX_OUT",
            "13": f"BANK{bank_b}_N_BUFFER",
            "14": f"BANK{bank_b}_N_BUFFER",
        }
        require_map(pad_nets(blocks[reference]), expected, reference)


def verify_ti_pbs_landpattern(block: str) -> None:
    """Gate U21 against TI PBS/S-PQFP-G32 land-pattern drawing 4212229/A."""
    pads = balanced_blocks(block, "pad")
    if len(pads) != 32:
        raise RuntimeError(f"U21 TI PBS footprint must have 32 pads, got {len(pads)}")

    rows: dict[str, list[tuple[float, float, float, float]]] = {
        "left": [],
        "right": [],
        "top": [],
        "bottom": [],
    }
    for pad in pads:
        at = re.search(r"\(at\s+(-?[0-9.]+)\s+(-?[0-9.]+)", pad)
        size = re.search(r"\(size\s+([0-9.]+)\s+([0-9.]+)\)", pad)
        if not at or not size:
            raise RuntimeError("U21 pad missing at/size geometry")
        x, y = (round(float(value), 3) for value in at.groups())
        sx, sy = (round(float(value), 3) for value in size.groups())
        if x == -3.1:
            rows["left"].append((x, y, sx, sy))
        elif x == 3.1:
            rows["right"].append((x, y, sx, sy))
        elif y == 3.1:
            rows["top"].append((x, y, sx, sy))
        elif y == -3.1:
            rows["bottom"].append((x, y, sx, sy))
        else:
            raise RuntimeError(f"U21 pad center is not on the TI 6.20-mm row span: {(x, y)}")

    expected_axis = [-1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75]
    for side in ("left", "right"):
        row = sorted(rows[side], key=lambda item: item[1])
        if [item[1] for item in row] != expected_axis:
            raise RuntimeError(f"U21 {side} pitch is not 0.50 mm")
        if any((item[2], item[3]) != (1.6, 0.3) for item in row):
            raise RuntimeError(f"U21 {side} pads must be 1.60 x 0.30 mm")
    for side in ("top", "bottom"):
        row = sorted(rows[side], key=lambda item: item[0])
        if [item[0] for item in row] != expected_axis:
            raise RuntimeError(f"U21 {side} pitch is not 0.50 mm")
        if any((item[2], item[3]) != (0.3, 1.6) for item in row):
            raise RuntimeError(f"U21 {side} pads must be 0.30 x 1.60 mm")


def verify_adc(blocks: dict[str, str]) -> None:
    expected = {
        "1": "ADC2_P",
        "2": "ADC2_N",
        "3": "ADC3_N",
        "4": "ADC3_P",
        "5": "ADC4_P",
        "6": "ADC4_N",
        "7": "ADC5_N",
        "8": "ADC5_P",
        "9": "ADC6_P",
        "10": "ADC6_N",
        "11": "ADC7_N",
        "12": "ADC7_P",
        "13": "AGND",
        "14": "ADC_REFIN",
        "15": "3V3A",
        "16": "ADC_SYNC_RESET",
        "17": "ADC_CS",
        "18": "ADC_DRDY",
        "19": "ADC_SCLK",
        "20": "ADC_DOUT",
        "21": "ADC_DIN",
        "22": "",
        "23": "ADC_CLKIN",
        "24": "ADS_CAP",
        "25": "AGND",
        "26": "3V3D",
        "27": "",
        "28": "AGND",
        "29": "ADC0_P",
        "30": "ADC0_N",
        "31": "ADC1_N",
        "32": "ADC1_P",
    }
    require_map(pad_nets(blocks["U21"]), expected, "U21")


def verify_rp2040(blocks: dict[str, str]) -> None:
    expected = {
        "1": "3V3D",
        "4": "MUX_S0",
        "5": "MUX_S1",
        "6": "MUX_S2",
        "7": "MUX_S3",
        "8": "MUX_EN",
        "10": "3V3D",
        "11": "ADC_DOUT",
        "12": "ADC_CS",
        "13": "ADC_SCLK",
        "14": "ADC_DIN",
        "15": "ADC_DRDY",
        "16": "ADC_SYNC_RESET",
        "19": "AGND",
        "20": "XIN_12M",
        "21": "XOUT_12M",
        "22": "3V3D",
        "23": "VREG_1V1",
        "33": "3V3D",
        "42": "3V3D",
        "43": "3V3D",
        "44": "3V3D",
        "45": "VREG_1V1",
        "46": "USB_DM_IC",
        "47": "USB_DP_IC",
        "48": "3V3D",
        "49": "3V3D",
        "50": "VREG_1V1",
        "51": "QSPI_SD3",
        "52": "QSPI_CLK",
        "53": "QSPI_SD0",
        "54": "QSPI_SD2",
        "55": "QSPI_SD1",
        "56": "QSPI_SS",
        "57": "AGND",
    }
    block = blocks["U23"]
    require_map(pad_nets(block), expected, "U23")
    pad57 = next(
        (
            pad
            for pad in balanced_blocks(block, "pad")
            if re.match(r'\(pad "57"', pad)
        ),
        None,
    )
    if pad57 is None:
        raise RuntimeError("U23 exposed pad 57 is missing")
    size = re.search(r"\(size\s+([0-9.]+)\s+([0-9.]+)\)", pad57)
    if not size or tuple(round(float(v), 3) for v in size.groups()) != (3.2, 3.2):
        actual = size.groups() if size else ("missing", "missing")
        raise RuntimeError(f"U23 exposed pad must be 3.2 x 3.2 mm, got {actual}")


def verify_flash(blocks: dict[str, str]) -> None:
    expected = {
        "1": "QSPI_SS",
        "2": "QSPI_SD1",
        "3": "QSPI_SD2",
        "4": "AGND",
        "5": "QSPI_SD0",
        "6": "QSPI_CLK",
        "7": "QSPI_SD3",
        "8": "3V3D",
    }
    require_map(pad_nets(blocks["U26"]), expected, "U26")


def verify_pcb(pcb_path: Path | None = None) -> dict[str, object]:
    pcb = (pcb_path or ROOT / "eeg128-tdm.kicad_pcb").read_text(encoding="utf-8")
    blocks = footprint_blocks(pcb)
    if len(blocks) != 642:
        raise RuntimeError(f"expected 642 PCB references, got {len(blocks)}")

    for reference, expected in CRITICAL_FOOTPRINTS.items():
        actual = footprint_name(blocks[reference])
        if actual != expected:
            raise RuntimeError(
                f"{reference}: expected footprint {expected}, got {actual}"
            )

    # CPL coordinates use board-space millimetres, before assembler origin conversion.
    for row in read_csv(ROOT / "CPL.csv"):
        reference = row["Designator"].strip()
        block = blocks[reference]
        header = block.split('(property', 1)[0]
        position = re.search(
            r"\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+([-0-9.]+))?\)", header
        )
        if position is None:
            raise RuntimeError(f"{reference}: PCB placement is missing")
        actual = [float(value.removesuffix("mm")) for value in (row["Mid X"], row["Mid Y"])]
        expected = [float(position.group(1)), float(position.group(2))]
        if any(abs(a - e) > 0.0051 for a, e in zip(actual, expected)):
            raise RuntimeError(f"{reference}: CPL coordinates {actual} != PCB {expected}")
        rotation = float(position.group(3) or 0)
        delta = (float(row["Rotation"]) - rotation + 180) % 360 - 180
        layer = "Bottom" if '(layer "B.Cu")' in header else "Top"
        if abs(delta) > 0.0051 or row["Layer"] != layer:
            raise RuntimeError(f"{reference}: CPL rotation/layer does not match PCB")

    verify_muxes(blocks)
    verify_buffers(blocks)
    verify_adc(blocks)
    verify_ti_pbs_landpattern(blocks["U21"])
    verify_rp2040(blocks)
    verify_flash(blocks)

    return {
        "pcb_references_verified": len(blocks),
        "cpl_coordinates_verified": len(blocks),
        "critical_footprints_verified": len(CRITICAL_FOOTPRINTS),
        "mux_pinouts_verified": 16,
        "buffer_pinouts_verified": 4,
        "adc_pinout_verified": True,
        "ads131m08_pbs_landpattern_verified": True,
        "ads131m08_pbs_pad_mm": [0.3, 1.6],
        "ads131m08_pbs_opposite_row_centers_mm": 6.2,
        "ads131m08_pbs_pitch_mm": 0.5,
        "rp2040_pinout_verified": True,
        "rp2040_ep_mm": [3.2, 3.2],
        "qspi_flash_pinout_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    parser.add_argument("--pcb", type=Path)
    args = parser.parse_args()

    report = {
        "bom_cpl": verify_bom_cpl(),
        "pcb": verify_pcb(args.pcb),
        "result": "PASS",
    }
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(output, end="")
    if args.json_out:
        Path(args.json_out).write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

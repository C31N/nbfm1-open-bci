#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import uuid


ROOT = Path(__file__).resolve().parent
PCB = ROOT / "eeg128-tdm.kicad_pcb"
BOM = ROOT / "BOM.csv"

ROOT_UUID = uuid.UUID("00000000-0000-4000-8000-00000000e128")
UUID_NAMESPACE = uuid.UUID("4d1b8b3b-4c18-45c8-b6f2-687141fd61f4")


@dataclass(frozen=True)
class Component:
    ref: str
    value: str
    footprint: str
    pads: tuple[tuple[str, str], ...]


def q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def deterministic_uuid(key: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, key))


def balanced_blocks(text: str, token: str) -> list[str]:
    needle = f"({token} "
    blocks: list[str] = []
    cursor = 0
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            return blocks
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
        blocks.append(text[start:end])
        cursor = end


def parse_bom() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    with BOM.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row["Manufacturer Part #"].strip()
            footprint = row["Footprint"].strip()
            for ref in row["Designator"].split(","):
                result[ref.strip()] = (value, footprint)
    return result


def parse_components() -> list[Component]:
    pcb = PCB.read_text(encoding="utf-8")
    bom = parse_bom()
    components: list[Component] = []

    ref_re = re.compile(r'\(property "Reference" "([^"]+)"')

    for block in balanced_blocks(pcb, "footprint"):
        ref_match = ref_re.search(block)
        if ref_match is None:
            continue
        ref = ref_match.group(1)
        if ref not in bom:
            continue

        pads: list[tuple[str, str]] = []
        for pad_block in balanced_blocks(block, "pad"):
            pad_match = re.match(r'\(pad "([^"]+)"', pad_block)
            if pad_match is None:
                continue
            number = pad_match.group(1)
            net_match = re.search(r'\(net\s+\d+\s+"([^"]+)"\)', pad_block)
            net = net_match.group(1) if net_match is not None else ""
            pads.append((number, net))

        def natural_pin(item: tuple[str, str]) -> tuple[int, str]:
            number = item[0]
            numeric = re.fullmatch(r"[0-9]+", number)
            return (0, f"{int(number):08d}") if numeric else (1, number)

        pads.sort(key=natural_pin)
        value, footprint = bom[ref]
        components.append(Component(ref, value, footprint, tuple(pads)))

    def ref_key(component: Component) -> tuple[str, int]:
        match = re.fullmatch(r"([A-Za-z#]+)([0-9]+)", component.ref)
        if match is None:
            return (component.ref, 0)
        return (match.group(1), int(match.group(2)))

    components.sort(key=ref_key)
    return components


def signature(component: Component) -> tuple[str, ...]:
    return tuple(number for number, _ in component.pads)


def symbol_id(numbers: tuple[str, ...]) -> str:
    digest = uuid.uuid5(UUID_NAMESPACE, "|".join(numbers)).hex[:12]
    return f"NBFM1_A0:GEN_{len(numbers)}_{digest}"


def pin_y(index: int, count: int) -> float:
    spacing = 1.27
    return ((count - 1) / 2.0 - index) * spacing


def library_symbol(numbers: tuple[str, ...]) -> str:
    sid = symbol_id(numbers)
    bare = sid.split(":", 1)[1]
    count = len(numbers)
    half_height = max(2.54, (max(count, 1) - 1) * 1.27 / 2.0 + 1.27)
    parts = [
        f'    (symbol {q(sid)}',
        "      (pin_numbers hide)",
        "      (pin_names (offset 0.508))",
        "      (exclude_from_sim no)",
        "      (in_bom yes)",
        "      (on_board yes)",
        '      (property "Reference" "U" (at 0 0 0) '
        "(effects (font (size 1.0 1.0)) (hide yes)))",
        f'      (property "Value" {q(bare)} (at 0 0 0) '
        "(effects (font (size 1.0 1.0)) (hide yes)))",
        '      (property "Footprint" "" (at 0 0 0) '
        "(effects (font (size 1.0 1.0)) (hide yes)))",
        '      (property "Datasheet" "~" (at 0 0 0) '
        "(effects (font (size 1.0 1.0)) (hide yes)))",
        '      (property "Description" "Generated connectivity symbol" (at 0 0 0) '
        "(effects (font (size 1.0 1.0)) (hide yes)))",
        f'      (symbol {q(bare + "_1_1")}',
        f"        (rectangle (start -1.27 {half_height:.3f}) "
        f"(end 1.27 {-half_height:.3f}) "
        "(stroke (width 0.254) (type default)) (fill (type background)))",
    ]
    for index, number in enumerate(numbers):
        y = pin_y(index, count)
        parts.extend(
            [
                "        (pin passive line",
                f"          (at -5.08 {y:.3f} 0)",
                "          (length 3.81)",
                f'          (name {q("Pin_" + number)} '
                "(effects (font (size 0.8 0.8))))",
                f'          (number {q(number)} '
                "(effects (font (size 0.8 0.8))))",
                "        )",
            ]
        )
    parts.extend(["      )", "    )"])
    return "\n".join(parts)


def positions(components: list[Component]) -> dict[str, tuple[float, float]]:
    large = [component for component in components if len(component.pads) > 2]
    small = [component for component in components if len(component.pads) <= 2]
    result: dict[str, tuple[float, float]] = {}

    for index, component in enumerate(large):
        column = index % 12
        row = index // 12
        result[component.ref] = (45.0 + 92.0 * column, 55.0 + 90.0 * row)

    small_start_y = 410.0
    for index, component in enumerate(small):
        column = index % 24
        row = index // 24
        result[component.ref] = (32.0 + 48.0 * column, small_start_y + 15.0 * row)

    return result


def instance(
    component: Component,
    x: float,
    y: float,
) -> tuple[str, list[str], list[str], list[str]]:
    numbers = signature(component)
    sid = symbol_id(numbers)
    count = len(numbers)
    inst_uuid = deterministic_uuid(f"instance:{component.ref}")
    parts = [
        "  (symbol",
        f"    (lib_id {q(sid)})",
        f"    (at {x:.3f} {y:.3f} 0)",
        "    (unit 1)",
        "    (exclude_from_sim no)",
        "    (in_bom yes)",
        "    (on_board yes)",
        "    (dnp no)",
        f'    (uuid {q(inst_uuid)})',
        f'    (property "Reference" {q(component.ref)} '
        f"(at {x:.3f} {y - 4.0:.3f} 0) "
        "(effects (font (size 0.9 0.9))))",
        f'    (property "Value" {q(component.value)} '
        f"(at {x:.3f} {y - 2.0:.3f} 0) "
        "(effects (font (size 0.8 0.8))))",
        f'    (property "Footprint" {q("NBFM1_A0:" + component.ref)} '
        f"(at {x:.3f} {y:.3f} 0) "
        "(effects (font (size 0.8 0.8)) (hide yes)))",
        '    (property "Datasheet" "" '
        f"(at {x:.3f} {y:.3f} 0) "
        "(effects (font (size 0.8 0.8)) (hide yes)))",
        '    (property "Description" '
        f'{q("Generated connectivity symbol; BOM footprint: " + component.footprint)} '
        f"(at {x:.3f} {y:.3f} 0) "
        "(effects (font (size 0.8 0.8)) (hide yes)))",
    ]

    wires: list[str] = []
    labels: list[str] = []
    no_connects: list[str] = []
    for index, (number, net) in enumerate(component.pads):
        parts.extend(
            [
                f'    (pin {q(number)}',
                f'      (uuid {q(deterministic_uuid(f"pin:{component.ref}:{number}"))})',
                "    )",
            ]
        )
        py = y + pin_y(index, count)
        pin_x = x - 5.08
        if not net:
            no_connects.append(
                "  (no_connect "
                f"(at {pin_x:.3f} {py:.3f}) "
                f"(uuid {q(deterministic_uuid(f'no-connect:{component.ref}:{number}'))}))"
            )
            continue
        label_x = pin_x - 3.81
        wires.append(
            "\n".join(
                [
                    "  (wire",
                    f"    (pts (xy {pin_x:.3f} {py:.3f}) "
                    f"(xy {label_x:.3f} {py:.3f}))",
                    "    (stroke (width 0) (type default))",
                    f'    (uuid {q(deterministic_uuid(f"wire:{component.ref}:{number}"))})',
                    "  )",
                ]
            )
        )
        labels.append(
            "\n".join(
                [
                    f"  (label {q(net)}",
                    f"    (at {label_x:.3f} {py:.3f} 0)",
                    "    (effects (font (size 0.7 0.7)) "
                    "(justify left bottom))",
                    f'    (uuid {q(deterministic_uuid(f"label:{component.ref}:{number}"))})',
                    "  )",
                ]
            )
        )

    parts.extend(
        [
            "    (instances",
            '      (project "eeg128-tdm"',
            f'        (path "/{ROOT_UUID}"',
            f'          (reference {q(component.ref)})',
            "          (unit 1)",
            "        )",
            "      )",
            "    )",
            "  )",
        ]
    )
    return "\n".join(parts), wires, labels, no_connects


def render(components: list[Component]) -> str:
    positions_by_ref = positions(components)
    signatures = sorted({signature(component) for component in components})

    instances: list[str] = []
    wires: list[str] = []
    labels: list[str] = []
    no_connects: list[str] = []
    for component in components:
        x, y = positions_by_ref[component.ref]
        (
            rendered,
            component_wires,
            component_labels,
            component_no_connects,
        ) = instance(component, x, y)
        instances.append(rendered)
        wires.extend(component_wires)
        labels.extend(component_labels)
        no_connects.extend(component_no_connects)

    header = [
        "(kicad_sch",
        "  (version 20231120)",
        '  (generator "nbfm1-open-bci-generate_schematic")',
        '  (generator_version "1.0")',
        f'  (uuid {q(str(ROOT_UUID))})',
        '  (paper "A0")',
        "  (title_block",
        '    (title "EEG128-TDM Rev A0 Generated Connectivity Schematic")',
        '    (date "2026-10-05")',
        '    (rev "A0")',
        '    (company "NBFM-1 Open BCI Contributors")',
        '    (comment 1 "CERN-OHL-S-2.0")',
        '    (comment 2 "Generated from PCB pad/net assignments; release remains fail-closed")',
        "  )",
        "  (lib_symbols",
    ]
    header.extend(library_symbol(numbers) for numbers in signatures)
    header.append("  )")

    footer = [
        "  (sheet_instances",
        '    (path "/" (page "1"))',
        "  )",
        ")",
    ]
    return "\n".join(
        [*header, *wires, *labels, *no_connects, *instances, *footer]
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "eeg128-tdm.generated.kicad_sch"),
    )
    parser.add_argument(
        "--replace-primary",
        action="store_true",
        help="replace eeg128-tdm.kicad_sch only after independent KiCad review",
    )
    args = parser.parse_args()

    components = parse_components()
    if len(components) != 642:
        raise RuntimeError(f"expected 642 BOM/PCB components, got {len(components)}")

    text = render(components)
    output = Path(args.output)
    output.write_text(text, encoding="utf-8")

    if args.replace_primary:
        primary = ROOT / "eeg128-tdm.kicad_sch"
        primary.write_text(text, encoding="utf-8")
        print(primary)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pcbnew


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def point(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x_mm), mm(y_mm))


def footprint(board: pcbnew.BOARD, reference: str) -> pcbnew.FOOTPRINT:
    item = board.FindFootprintByReference(reference)
    if item is None:
        raise RuntimeError(f"missing footprint {reference}")
    return item


def place(
    board: pcbnew.BOARD,
    reference: str,
    x_mm: float,
    y_mm: float,
    angle_deg: float = 0.0,
) -> None:
    item = footprint(board, reference)
    item.SetPosition(point(x_mm, y_mm))
    item.SetOrientationDegrees(angle_deg)


def clear_routing(board: pcbnew.BOARD) -> None:
    for track in list(board.GetTracks()):
        board.Remove(track)
    for zone in list(board.Zones()):
        board.Remove(zone)


def merge_digital_ground(board: pcbnew.BOARD) -> int:
    agnd = board.FindNet("AGND")
    if agnd is None:
        raise RuntimeError("AGND net not found")
    changed = 0
    for item in board.GetFootprints():
        for pad in item.Pads():
            if pad.GetNetname() == "DGND":
                pad.SetNet(agnd)
                changed += 1
    if changed == 0:
        raise RuntimeError("no DGND pads found to merge")
    return changed


def place_input_bank(board: pcbnew.BOARD, bank: int) -> None:
    bank_center_x = 16.0 + 23.0 * bank
    connector = f"J{bank + 1}"
    place(board, connector, bank_center_x, 7.6, 0.0)

    p_mux = f"U{2 * bank + 1}"
    n_mux = f"U{2 * bank + 2}"
    place(board, p_mux, bank_center_x - 4.4, 45.0, 90.0)
    place(board, n_mux, bank_center_x + 4.4, 45.0, 90.0)

    first_channel = bank * 16
    for local_channel in range(16):
        channel = first_channel + local_channel
        column = local_channel % 4
        row = local_channel // 4
        cx = bank_center_x - 6.9 + 4.6 * column
        cy = 17.0 + 5.6 * row

        bias_p = 2 * channel + 1
        bias_n = 2 * channel + 2
        series_p = 257 + 2 * channel
        series_n = 258 + 2 * channel

        place(board, f"R{series_p}", cx - 1.15, cy - 1.35, 90.0)
        place(board, f"R{bias_p}", cx + 1.15, cy - 1.35, 90.0)
        place(board, f"R{series_n}", cx - 1.15, cy + 1.35, 90.0)
        place(board, f"R{bias_n}", cx + 1.15, cy + 1.35, 90.0)

    place(board, f"C{21 + 2 * bank}", bank_center_x - 4.4, 51.0, 0.0)
    place(board, f"C{22 + 2 * bank}", bank_center_x + 4.4, 51.0, 0.0)


def place_analog_core(board: pcbnew.BOARD) -> None:
    for index, x_mm in enumerate((62.0, 80.0, 98.0, 116.0), start=17):
        place(board, f"U{index}", x_mm, 61.0, 0.0)

    for index, x_mm in enumerate((62.0, 80.0, 98.0, 116.0), start=37):
        place(board, f"C{index}", x_mm, 66.0, 0.0)

    place(board, "U21", 137.0, 61.0, 0.0)
    place(board, "C41", 133.5, 67.0, 0.0)
    place(board, "C42", 137.0, 67.0, 0.0)
    place(board, "C43", 140.5, 67.0, 0.0)
    place(board, "C61", 143.5, 61.0, 90.0)
    place(board, "U27", 137.0, 73.0, 0.0)

    for index in range(16):
        row = index // 8
        column = index % 8
        place(
            board,
            f"R{513 + index}",
            122.0 + 3.0 * column,
            54.0 + 3.0 * row,
            90.0,
        )

    place(board, "U22", 142.0, 82.0, 0.0)
    for index, x_mm in enumerate((135.0, 138.0, 141.0, 144.0), start=529):
        place(board, f"R{index}", x_mm, 88.0, 0.0)
    place(board, "R533", 148.0, 88.0, 0.0)
    place(board, "R534", 151.0, 88.0, 0.0)
    place(board, "R535", 154.0, 84.0, 90.0)
    place(board, "R536", 157.0, 84.0, 90.0)
    place(board, "R537", 148.0, 82.0, 0.0)
    place(board, "C62", 151.5, 82.0, 0.0)


def place_digital_core(board: pcbnew.BOARD) -> None:
    place(board, "U23", 168.0, 77.0, 0.0)
    place(board, "Y1", 168.0, 67.0, 0.0)
    place(board, "C63", 164.5, 67.0, 0.0)
    place(board, "C64", 171.5, 67.0, 0.0)
    place(board, "U26", 177.0, 88.0, 0.0)
    place(board, "U24", 153.0, 101.0, 0.0)
    place(board, "U25", 163.0, 101.0, 0.0)
    place(board, "J9", 190.0, 77.0, 270.0)
    place(board, "J10", 188.0, 99.0, 270.0)
    place(board, "J11", 188.0, 107.0, 270.0)

    digital_caps = list(range(44, 61))
    for offset, cap in enumerate(digital_caps):
        column = offset % 6
        row = offset // 6
        place(board, f"C{cap}", 151.0 + 5.0 * column, 93.0 + 4.0 * row, 0.0)

    for index in range(1, 21):
        place(board, f"C{index}", 121.0 + 3.3 * ((index - 1) % 10), 104.0 + 3.0 * ((index - 1) // 10), 0.0)


def prepare(input_path: Path, output_path: Path) -> None:
    board = pcbnew.LoadBoard(str(input_path))
    if board is None:
        raise RuntimeError(f"cannot load {input_path}")

    clear_routing(board)
    merged = merge_digital_ground(board)

    for bank in range(8):
        place_input_bank(board, bank)
    place_analog_core(board)
    place_digital_core(board)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)

    text = output_path.read_text(encoding="utf-8")
    text = text.replace('(1 "In1.Cu" power)', '(1 "In1.Cu" signal)')
    text = text.replace('(2 "In2.Cu" power)', '(2 "In2.Cu" signal)')
    output_path.write_text(text, encoding="utf-8")

    print(
        {
            "output": str(output_path),
            "merged_dgnd_pads": merged,
            "footprints": len(list(board.GetFootprints())),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    prepare(Path(args.input), Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

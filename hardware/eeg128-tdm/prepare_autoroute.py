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


def ensure_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def set_pad_net(
    board: pcbnew.BOARD,
    reference: str,
    pad_number: str,
    net_name: str,
) -> None:
    item = footprint(board, reference)
    pad = item.FindPadByNumber(pad_number)
    if pad is None:
        raise RuntimeError(f"missing pad {reference}.{pad_number}")
    pad.SetNet(ensure_net(board, net_name))


def set_two_pad_net(
    board: pcbnew.BOARD,
    reference: str,
    first: str,
    second: str,
) -> None:
    set_pad_net(board, reference, "1", first)
    set_pad_net(board, reference, "2", second)


def load_library_footprint(library: str, name: str) -> pcbnew.FOOTPRINT:
    roots = (
        Path("/usr/share/kicad/footprints"),
        Path("/usr/share/kicad/footprints"),
    )
    for root in roots:
        pretty = root / f"{library}.pretty"
        if not pretty.is_dir():
            continue
        item = pcbnew.FootprintLoad(str(pretty), name)
        if item is not None:
            return item
    raise RuntimeError(f"KiCad footprint not found: {library}:{name}")


def replace_usb_connector(board: pcbnew.BOARD) -> None:
    old = footprint(board, "J9")
    board.Remove(old)

    item = load_library_footprint(
        "Connector_USB",
        "USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    )
    item.SetReference("J9")
    item.SetValue("TYPE-C-31-M-12")
    board.Add(item)
    item.SetPosition(point(185.0, 77.0))
    item.SetOrientationDegrees(90.0)

    mapping = {
        "1": "AGND",
        "2": "5V_ISO",
        "4": "USB_CC1",
        "5": "USB_DM",
        "6": "USB_DP",
        "7": "USB_DM",
        "8": "USB_DP",
        "10": "USB_CC2",
        "11": "5V_ISO",
        "12": "AGND",
        "13": "SHIELD",
    }
    for pad_number, net_name in mapping.items():
        set_pad_net(board, "J9", pad_number, net_name)


def add_cc_resistor(
    board: pcbnew.BOARD,
    reference: str,
    cc_net: str,
    x_mm: float,
    y_mm: float,
) -> None:
    item = load_library_footprint("Resistor_SMD", "R_0603_1608Metric")
    item.SetReference(reference)
    item.SetValue("5.1k")
    board.Add(item)
    item.SetPosition(point(x_mm, y_mm))
    item.SetOrientationDegrees(0.0)
    set_pad_net(board, reference, "1", cc_net)
    set_pad_net(board, reference, "2", "AGND")


def assign_missing_functional_nets(board: pcbnew.BOARD) -> None:
    # Local board ground is one continuous return plane in A1.
    for item in board.GetFootprints():
        for pad in item.Pads():
            if pad.GetNetname() in {"DGND", "ISO_GND"}:
                pad.SetNet(ensure_net(board, "AGND"))

    # LDOs: DBV/SOT-25 pinout IN=1, GND=2, EN=3, NC=4, OUT=5.
    for reference, output_net in (("U24", "3V3A"), ("U25", "3V3D")):
        set_pad_net(board, reference, "1", "5V_ISO")
        set_pad_net(board, reference, "2", "AGND")
        set_pad_net(board, reference, "3", "5V_ISO")
        set_pad_net(board, reference, "5", output_net)

    # 8.192 MHz oscillator: 1=Tri-state, 2=GND, 3=OUT, 4=VDD.
    set_pad_net(board, "U27", "1", "3V3D")
    set_pad_net(board, "U27", "2", "AGND")
    set_pad_net(board, "U27", "3", "ADC_CLKIN")
    set_pad_net(board, "U27", "4", "3V3D")

    # RP2040 crystal case/ground pads.
    set_pad_net(board, "Y1", "2", "AGND")
    set_pad_net(board, "Y1", "4", "AGND")

    # Isolated local power input return is the same local continuous ground.
    set_pad_net(board, "J11", "1", "5V_ISO")
    set_pad_net(board, "J11", "2", "AGND")

    # MUX local bulk + HF decoupling.
    for index in range(1, 17):
        set_two_pad_net(board, f"C{index}", "3V3A", "AGND")
        set_two_pad_net(board, f"C{20 + index}", "3V3A", "AGND")

    # TLV9064 local decoupling.
    for index in range(37, 41):
        set_two_pad_net(board, f"C{index}", "3V3A", "AGND")

    # ADC analog, digital, and REFIN local capacitors.
    set_two_pad_net(board, "C41", "3V3A", "AGND")
    set_two_pad_net(board, "C42", "3V3D", "AGND")
    set_two_pad_net(board, "C43", "ADC_REFIN", "AGND")
    set_two_pad_net(board, "C61", "ADS_CAP", "AGND")

    # LDO input/output capacitors.
    set_two_pad_net(board, "C17", "5V_ISO", "AGND")
    set_two_pad_net(board, "C18", "3V3A", "AGND")
    set_two_pad_net(board, "C19", "5V_ISO", "AGND")
    set_two_pad_net(board, "C20", "3V3D", "AGND")

    # Digital-domain local decoupling. Reserve C50-C52 for the 1.1 V core rail.
    for index in range(44, 50):
        set_two_pad_net(board, f"C{index}", "3V3D", "AGND")
    for index in range(50, 53):
        set_two_pad_net(board, f"C{index}", "VREG_1V1", "AGND")
    for index in range(53, 61):
        set_two_pad_net(board, f"C{index}", "3V3D", "AGND")

    set_two_pad_net(board, "C63", "XIN_12M", "AGND")
    set_two_pad_net(board, "C64", "XOUT_12M", "AGND")


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
    place(board, p_mux, bank_center_x - 5.1, 45.0, 0.0)
    place(board, n_mux, bank_center_x + 5.1, 45.0, 0.0)

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

    place(board, f"C{21 + 2 * bank}", bank_center_x - 5.1, 54.5, 0.0)
    place(board, f"C{22 + 2 * bank}", bank_center_x + 5.1, 54.5, 0.0)


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
    place(board, "J9", 185.0, 77.0, 90.0)
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
    replace_usb_connector(board)
    add_cc_resistor(board, "R538", "USB_CC1", 181.0, 70.5)
    add_cc_resistor(board, "R539", "USB_CC2", 184.0, 70.5)
    assign_missing_functional_nets(board)
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
            "usb_cc_resistors": ["R538", "R539"],
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

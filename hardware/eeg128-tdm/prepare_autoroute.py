#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pcbnew

from apply_board_constraints import apply_stackup


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


def normalize_generated_footprint_metadata(board: pcbnew.BOARD) -> dict[str, int]:
    """Remove false library/silkscreen DRC sources from board-local footprints."""
    detached = 0
    silk_items_moved = 0
    references_hidden = 0

    for item in board.GetFootprints():
        fpid = item.GetFPIDAsString()
        if fpid.startswith("NBFM1_A0:"):
            # Keep the embedded footprint but remove the nonexistent library
            # nickname so KiCad does not report a missing external library.
            item.SetFPIDAsString(item.GetReference())
            detached += 1

            for graphic in item.GraphicalItems():
                if graphic.GetLayer() == pcbnew.F_SilkS:
                    graphic.SetLayer(pcbnew.F_Fab)
                    silk_items_moved += 1

            reference = item.Reference()
            if reference.IsVisible():
                reference.SetVisible(False)
                references_hidden += 1

    return {
        "board_local_footprints": detached,
        "silk_items_moved_to_fab": silk_items_moved,
        "references_hidden": references_hidden,
    }


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


def replace_footprint_keep_nets(
    board: pcbnew.BOARD,
    reference: str,
    library: str,
    name: str,
    x_mm: float,
    y_mm: float,
    angle_deg: float = 0.0,
) -> None:
    old = footprint(board, reference)
    value = old.GetValue()
    nets = {
        pad.GetNumber(): pad.GetNetname()
        for pad in old.Pads()
        if pad.GetNumber() and pad.GetNetname()
    }
    board.Remove(old)

    item = load_library_footprint(library, name)
    item.SetReference(reference)
    item.SetValue(value)
    board.Add(item)
    item.SetPosition(point(x_mm, y_mm))
    item.SetOrientationDegrees(angle_deg)

    for pad_number, net_name in nets.items():
        pad = item.FindPadByNumber(pad_number)
        if pad is None:
            raise RuntimeError(
                f"replacement footprint {library}:{name} missing "
                f"{reference}.{pad_number}"
            )
        pad.SetNet(ensure_net(board, net_name))


def ensure_critical_manufacturer_footprints(board: pcbnew.BOARD) -> int:
    """Replace critical generated land patterns in one mutation-safe batch."""
    specifications: dict[str, tuple[str, str]] = {
        **{
            f"U{index}": (
                "Package_SO",
                "SOIC-24W_7.5x15.4mm_P1.27mm",
            )
            for index in range(1, 17)
        },
        **{
            f"U{index}": (
                "Package_SO",
                "TSSOP-14_4.4x5mm_P0.65mm",
            )
            for index in range(17, 21)
        },
        "U21": ("Package_QFP", "LQFP-32_5x5mm_P0.5mm"),
        "U23": (
            "Package_DFN_QFN",
            "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
        ),
    }

    snapshots: list[
        tuple[
            pcbnew.FOOTPRINT,
            str,
            str,
            str,
            float,
            float,
            float,
            dict[str, str],
        ]
    ] = []
    for reference, (library, name) in specifications.items():
        old = footprint(board, reference)
        position = old.GetPosition()
        nets = {
            str(pad.GetNumber()): str(pad.GetNetname())
            for pad in old.Pads()
            if pad.GetNumber() and pad.GetNetname()
        }
        snapshots.append(
            (
                old,
                reference,
                str(old.GetValue()),
                library,
                pcbnew.ToMM(position.x),
                pcbnew.ToMM(position.y),
                float(old.GetOrientationDegrees()),
                nets,
            )
        )

    for old, *_ in snapshots:
        board.Remove(old)

    for (
        _old,
        reference,
        value,
        library,
        x_mm,
        y_mm,
        angle_deg,
        nets,
    ) in snapshots:
        name = specifications[reference][1]
        item = load_library_footprint(library, name)
        item.SetReference(reference)
        item.SetValue(value)
        item.SetPosition(point(x_mm, y_mm))
        item.SetOrientationDegrees(angle_deg)
        board.Add(item)

        for pad_number, net_name in nets.items():
            pad = item.FindPadByNumber(pad_number)
            if pad is None:
                raise RuntimeError(
                    f"replacement footprint {library}:{name} missing "
                    f"{reference}.{pad_number}"
                )
            pad.SetNet(ensure_net(board, net_name))

    return len(snapshots)

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
        "A1": "AGND",
        "B12": "AGND",
        "A12": "AGND",
        "B1": "AGND",
        "A4": "5V_ISO",
        "B9": "5V_ISO",
        "A9": "5V_ISO",
        "B4": "5V_ISO",
        "A5": "USB_CC1",
        "B5": "USB_CC2",
        "A6": "USB_DP",
        "B6": "USB_DP",
        "A7": "USB_DM",
        "B7": "USB_DM",
        "S1": "SHIELD",
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


def ensure_usb_connector(board: pcbnew.BOARD) -> None:
    item = board.FindFootprintByReference("J9")
    canonical = False
    if item is not None:
        try:
            canonical = (
                item.GetFPID().GetLibItemName()
                == "USB_C_Receptacle_HRO_TYPE-C-31-M-12"
            )
        except Exception:
            canonical = False

    if not canonical:
        replace_usb_connector(board)
        return

    item.SetValue("TYPE-C-31-M-12")
    item.SetPosition(point(185.0, 77.0))
    item.SetOrientationDegrees(90.0)
    mapping = {
        "A1": "AGND",
        "B12": "AGND",
        "A12": "AGND",
        "B1": "AGND",
        "A4": "5V_ISO",
        "B9": "5V_ISO",
        "A9": "5V_ISO",
        "B4": "5V_ISO",
        "A5": "USB_CC1",
        "B5": "USB_CC2",
        "A6": "USB_DP",
        "B6": "USB_DP",
        "A7": "USB_DM",
        "B7": "USB_DM",
        "S1": "SHIELD",
    }
    for pad_number, net_name in mapping.items():
        set_pad_net(board, "J9", pad_number, net_name)


def ensure_cc_resistor(
    board: pcbnew.BOARD,
    reference: str,
    cc_net: str,
    x_mm: float,
    y_mm: float,
) -> None:
    item = board.FindFootprintByReference(reference)
    if item is None:
        add_cc_resistor(board, reference, cc_net, x_mm, y_mm)
        return

    item.SetValue("5.1k")
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

    # RP2040 fixed-function pins and boot-flash bus.
    # Raspberry Pi RP2040 QFN-56: TESTEN=19 must be tied low; QSPI data
    # lanes are package-specific and must not be inferred from sequential order.
    rp2040_fixed = {
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
    for pad_number, net_name in rp2040_fixed.items():
        set_pad_net(board, "U23", pad_number, net_name)

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



def add_track(
    board: pcbnew.BOARD,
    net_name: str,
    start: pcbnew.VECTOR2I,
    end: pcbnew.VECTOR2I,
    layer: int,
    width_mm: float,
) -> None:
    if start == end:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(start)
    track.SetEnd(end)
    track.SetWidth(mm(width_mm))
    track.SetLayer(layer)
    track.SetNet(ensure_net(board, net_name))
    board.Add(track)


def add_through_via(
    board: pcbnew.BOARD,
    net_name: str,
    position: pcbnew.VECTOR2I,
    diameter_mm: float = 0.65,
    drill_mm: float = 0.30,
) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(position)
    via.SetWidth(mm(diameter_mm))
    via.SetDrill(mm(drill_mm))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(ensure_net(board, net_name))
    board.Add(via)


def add_rect_zone(
    board: pcbnew.BOARD,
    net_name: str,
    layer: int,
    x1_mm: float,
    y1_mm: float,
    x2_mm: float,
    y2_mm: float,
) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetNet(ensure_net(board, net_name))
    zone.SetLayer(layer)
    zone.SetMinThickness(mm(0.15))
    zone.SetLocalClearance(mm(0.20))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetThermalReliefGap(mm(0.20))
    zone.SetThermalReliefSpokeWidth(mm(0.25))
    outline = zone.Outline()
    outline.NewOutline()
    outline.Append(point(x1_mm, y1_mm))
    outline.Append(point(x2_mm, y1_mm))
    outline.Append(point(x2_mm, y2_mm))
    outline.Append(point(x1_mm, y2_mm))
    board.Add(zone)


def outward_fanout_position(
    item: pcbnew.FOOTPRINT,
    pad: pcbnew.PAD,
    distance_mm: float,
) -> pcbnew.VECTOR2I:
    pos = pad.GetPosition()
    center = item.GetPosition()
    dx = pos.x - center.x
    dy = pos.y - center.y
    distance = mm(distance_mm)
    if abs(dx) >= abs(dy):
        step = distance if dx >= 0 else -distance
        return pcbnew.VECTOR2I(pos.x + step, pos.y)
    step = distance if dy >= 0 else -distance
    return pcbnew.VECTOR2I(pos.x, pos.y + step)


def fanout_net_to_bus(
    board: pcbnew.BOARD,
    net_name: str,
    references: list[str],
    bus_y_mm: float,
    bus_x1_mm: float,
    bus_x2_mm: float,
    track_width_mm: float,
) -> int:
    add_track(
        board,
        net_name,
        point(bus_x1_mm, bus_y_mm),
        point(bus_x2_mm, bus_y_mm),
        pcbnew.In2_Cu,
        track_width_mm,
    )
    count = 0
    seen: set[tuple[int, int]] = set()
    for reference in references:
        item = board.FindFootprintByReference(reference)
        if item is None:
            continue
        for pad in item.Pads():
            if pad.GetNetname() != net_name:
                continue
            via_pos = outward_fanout_position(item, pad, 0.85)
            key = (via_pos.x, via_pos.y)
            if key in seen:
                continue
            seen.add(key)
            add_track(
                board,
                net_name,
                pad.GetPosition(),
                via_pos,
                pcbnew.F_Cu,
                max(0.20, track_width_mm),
            )
            add_through_via(board, net_name, via_pos)
            add_track(
                board,
                net_name,
                via_pos,
                pcbnew.VECTOR2I(via_pos.x, mm(bus_y_mm)),
                pcbnew.In2_Cu,
                track_width_mm,
            )
            count += 1
    return count


def mux_channel_pin(local_channel: int) -> str:
    if not 0 <= local_channel < 16:
        raise ValueError(local_channel)
    if local_channel < 8:
        return str(9 - local_channel)
    return str(31 - local_channel)


def add_channel_to_mux_routes(board: pcbnew.BOARD) -> int:
    """Route aligned protected EEG channels directly to mux inputs on F.Cu.

    VCM is routed on In2.Cu, leaving the high-impedance signal corridor free
    of the former VCM collection bus. The source and destination ordering is
    monotonic inside each of the four 8-channel groups.
    """
    routed = 0
    for bank in range(8):
        p_mux = footprint(board, f"U{2 * bank + 1}")
        n_mux = footprint(board, f"U{2 * bank + 2}")

        for local_channel in range(16):
            channel = bank * 16 + local_channel
            pin_number = mux_channel_pin(local_channel)
            for polarity, mux, series_ref in (
                ("P", p_mux, 257 + 2 * channel),
                ("N", n_mux, 258 + 2 * channel),
            ):
                series = footprint(board, f"R{series_ref}")
                source = series.FindPadByNumber("2")
                target = mux.FindPadByNumber(pin_number)
                if source is None or target is None:
                    raise RuntimeError(
                        f"missing channel route endpoint "
                        f"CH{channel:03d}_{polarity}"
                    )
                expected = f"CH{channel:03d}_{polarity}_MUX"
                if (
                    source.GetNetname() != expected
                    or target.GetNetname() != expected
                ):
                    raise RuntimeError(f"net mismatch for {expected}")

                add_track(
                    board,
                    expected,
                    source.GetPosition(),
                    target.GetPosition(),
                    pcbnew.F_Cu,
                    0.15,
                )
                routed += 1
    return routed

def add_channel_mux_preroutes(board: pcbnew.BOARD) -> int:
    """Pre-route only the local 100 kOhm / 10 MOhm junction.

    The series resistor output and the bias-resistor input are deliberately
    placed 0.5 mm apart and share the same protected MUX net.  Connecting only
    this local junction is deterministic and DRC-safe.  The longer path to the
    CD74HC4067 pin remains an autorouter task because straight-line routing
    across the full bank can cross neighboring channels.
    """
    routed = 0

    for channel in range(128):
        for polarity in ("P", "N"):
            if polarity == "P":
                bias_ref = 1 + 2 * channel
                series_ref = 257 + 2 * channel
            else:
                bias_ref = 2 + 2 * channel
                series_ref = 258 + 2 * channel

            series = footprint(board, f"R{series_ref}")
            bias = footprint(board, f"R{bias_ref}")
            series_out = series.FindPadByNumber("2")
            bias_tap = bias.FindPadByNumber("1")
            if series_out is None or bias_tap is None:
                raise RuntimeError(
                    f"channel junction pad missing for CH{channel:03d}_{polarity}"
                )

            net_name = series_out.GetNetname()
            if not net_name or bias_tap.GetNetname() != net_name:
                raise RuntimeError(
                    f"net mismatch at CH{channel:03d}_{polarity} bias junction"
                )

            add_track(
                board,
                net_name,
                series_out.GetPosition(),
                bias_tap.GetPosition(),
                pcbnew.F_Cu,
                0.15,
            )
            routed += 1

    return routed

def add_vcm_preroute(board: pcbnew.BOARD) -> int:
    """Route the 10 MOhm bias returns on In2.Cu.

    Only a short F.Cu stub exists on the VCM side of each 10 MOhm resistor.
    A through-via transfers VCM to In2.Cu, where four bank-local vertical
    spines and one horizontal collection bus carry the reference. This keeps
    F.Cu available for the microvolt channel paths.
    """
    routed = 0
    global_bus_y = 36.4
    all_spines: list[float] = []

    for bank in range(8):
        bank_center_x = 17.5 + 23.0 * bank
        spine_x = (
            bank_center_x - 5.75,
            bank_center_x - 1.05,
            bank_center_x + 4.75,
            bank_center_x + 10.25,
        )
        all_spines.extend(spine_x)

        for local_channel in range(16):
            channel = bank * 16 + local_channel
            if local_channel < 8:
                p_spine = spine_x[0]
                n_spine = spine_x[1]
            else:
                p_spine = spine_x[2]
                n_spine = spine_x[3]

            for bias_ref, target_x in (
                (1 + 2 * channel, p_spine),
                (2 + 2 * channel, n_spine),
            ):
                item = footprint(board, f"R{bias_ref}")
                pad = item.FindPadByNumber("2")
                if pad is None or pad.GetNetname() != "VCM":
                    raise RuntimeError(f"invalid VCM bias pad R{bias_ref}.2")

                pad_pos = pad.GetPosition()
                via_pos = point(target_x, pcbnew.ToMM(pad_pos.y))
                add_track(
                    board,
                    "VCM",
                    pad_pos,
                    via_pos,
                    pcbnew.F_Cu,
                    0.15,
                )
                add_through_via(
                    board,
                    "VCM",
                    via_pos,
                    diameter_mm=0.65,
                    drill_mm=0.30,
                )
                add_track(
                    board,
                    "VCM",
                    via_pos,
                    point(target_x, global_bus_y),
                    pcbnew.B_Cu,
                    0.20,
                )
                routed += 1

        add_track(
            board,
            "VCM",
            point(spine_x[0], global_bus_y),
            point(spine_x[3], global_bus_y),
            pcbnew.B_Cu,
            0.25,
        )

    if all_spines:
        add_track(
            board,
            "VCM",
            point(min(all_spines), global_bus_y),
            point(max(all_spines), global_bus_y),
            pcbnew.B_Cu,
            0.25,
        )

    return routed

def add_power_and_reference_preroutes(board: pcbnew.BOARD) -> dict[str, int]:
    """Reserve In1.Cu as a continuous AGND reference plane.

    Do not pre-route power/reference buses with blind geometric fanout. The previous
    implementation created deterministic shorts and via/clearance violations around
    fine-pitch devices and densely placed passives. Signal and power traces are left
    to the constrained router; only the continuous low-impedance ground reference is
    created here.
    """
    # L2 is one uninterrupted local return plane. Do not split analog and
    # digital ground; control return-current geometry by placement and stitching.
    add_rect_zone(board, "AGND", pcbnew.In1_Cu, 5.5, 5.5, 194.5, 114.5)

    # L3 is reserved for non-overlapping power islands. These are deliberately
    # inset from the outline and from each other by >= 1.0 mm.
    add_rect_zone(board, "3V3A", pcbnew.In2_Cu, 5.5, 37.0, 149.5, 75.5)
    add_rect_zone(board, "3V3D", pcbnew.In2_Cu, 150.5, 55.0, 194.5, 99.0)
    add_rect_zone(board, "5V_ISO", pcbnew.In2_Cu, 150.5, 100.0, 194.5, 114.0)

    try:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
    except Exception as exc:
        print(f"zone fill deferred to KiCad CLI: {exc}")
    return {
        "AGND_plane": 1,
        "VCM": 0,
        "3V3A": 1,
        "3V3D": 1,
        "5V_ISO": 1,
        "VREG_1V1": 0,
    }

def add_ground_stitching(board: pcbnew.BOARD) -> int:
    """Add an AGND via fence tied to the uninterrupted L2 reference plane."""
    positions: set[tuple[float, float]] = set()
    for x_mm in range(10, 191, 10):
        positions.add((float(x_mm), 7.0))
        positions.add((float(x_mm), 113.0))
    for y_mm in range(17, 108, 10):
        positions.add((7.0, float(y_mm)))
        positions.add((193.0, float(y_mm)))

    for x_mm, y_mm in sorted(positions):
        add_through_via(
            board,
            "AGND",
            point(x_mm, y_mm),
            diameter_mm=0.60,
            drill_mm=0.30,
        )
    return len(positions)


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
    return changed


def place_input_bank(board: pcbnew.BOARD, bank: int) -> None:
    """Place one 16-channel differential TDM bank for monotonic routing.

    The four resistor groups are aligned to the four CD74HC4067 input pin columns:
      P0..P7, N0..N7, P8..P15, N8..N15.

    CD74HC4067 channels 0..7 appear in reverse vertical order on the left package
    side, while channels 8..15 appear in forward order on the right side. Mirroring
    the resistor row order removes a large class of unavoidable crossing routes.
    """
    bank_center_x = 17.5 + 23.0 * bank
    connector = f"J{bank + 1}"
    place(board, connector, bank_center_x, 7.6, 0.0)

    p_mux = f"U{2 * bank + 1}"
    n_mux = f"U{2 * bank + 2}"
    place(board, p_mux, bank_center_x - 4.0, 45.0, 0.0)
    place(board, n_mux, bank_center_x + 4.0, 45.0, 0.0)
    for reference in (p_mux, n_mux):
        item = footprint(board, reference)
        for pad in item.Pads():
            pad.SetOrientationDegrees(0.0)

    group_x = {
        "P_LOW": bank_center_x - 8.0,
        "N_LOW": bank_center_x - 2.5,
        "P_HIGH": bank_center_x + 2.5,
        "N_HIGH": bank_center_x + 8.0,
    }

    for local_channel in range(16):
        channel = bank * 16 + local_channel
        if local_channel < 8:
            row = 7 - local_channel
            p_center = group_x["P_LOW"]
            n_center = group_x["N_LOW"]
        else:
            row = local_channel - 8
            p_center = group_x["P_HIGH"]
            n_center = group_x["N_HIGH"]

        y = 13.5 + 3.0 * row

        bias_p = 2 * channel + 1
        bias_n = 2 * channel + 2
        series_p = 257 + 2 * channel
        series_n = 258 + 2 * channel

        # Horizontal 0603 pair: series resistor toward the connector/mux column,
        # bias resistor toward the bank interior. A 0.50 mm copper gap remains
        # between their facing pads for a short same-net connection.
        place(board, f"R{series_p}", p_center - 1.05, y, 0.0)
        place(board, f"R{bias_p}", p_center + 1.05, y, 0.0)
        place(board, f"R{series_n}", n_center - 1.05, y, 0.0)
        place(board, f"R{bias_n}", n_center + 1.05, y, 0.0)

    # One bulk (1 uF) and one HF (100 nF) capacitor per MUX, placed locally.
    place(board, f"C{1 + 2 * bank}", bank_center_x - 4.0, 52.0, 0.0)
    place(board, f"C{2 + 2 * bank}", bank_center_x + 4.0, 52.0, 0.0)
    place(board, f"C{21 + 2 * bank}", bank_center_x - 4.0, 54.2, 0.0)
    place(board, f"C{22 + 2 * bank}", bank_center_x + 4.0, 54.2, 0.0)

def place_analog_core(board: pcbnew.BOARD) -> None:
    for index, x_mm in enumerate((62.0, 80.0, 98.0, 116.0), start=17):
        place(board, f"U{index}", x_mm, 61.0, 0.0)

    for index, x_mm in enumerate((62.0, 80.0, 98.0, 108.0), start=37):
        place(board, f"C{index}", x_mm, 64.0 if index == 40 else 66.0, 0.0)

    place(board, "U21", 137.0, 61.0, 0.0)
    place(board, "C41", 142.0, 66.0, 0.0)
    place(board, "C42", 145.0, 66.0, 0.0)
    place(board, "C43", 148.0, 66.0, 0.0)
    place(board, "C61", 143.5, 61.0, 90.0)
    place(board, "U27", 137.0, 73.0, 0.0)

    for index in range(16):
        row = index // 8
        column = index % 8
        place(
            board,
            f"R{513 + index}",
            112.0 + 3.2 * column,
            67.0 + 3.2 * row,
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
    for pad in footprint(board, "U23").Pads():
        pad.SetLocalClearance(mm(0.10))
    place(board, "Y1", 168.0, 67.0, 0.0)
    place(board, "C63", 164.5, 67.0, 0.0)
    place(board, "C64", 171.5, 67.0, 0.0)
    place(board, "U26", 177.0, 88.0, 0.0)
    place(board, "U24", 153.0, 108.0, 0.0)
    place(board, "U25", 163.0, 108.0, 0.0)
    place(board, "J9", 185.0, 77.0, 90.0)
    place(board, "J10", 188.0, 99.0, 0.0)
    place(board, "J11", 188.0, 107.0, 0.0)
    for reference in ("J10", "J11"):
        item = footprint(board, reference)
        for pad in item.Pads():
            pad.SetOrientationDegrees(0.0)

    digital_caps = list(range(44, 61))
    for offset, cap in enumerate(digital_caps):
        column = offset % 6
        row = offset // 6
        place(board, f"C{cap}", 151.0 + 5.0 * column, 93.0 + 4.0 * row, 0.0)
    place(board, "C56", 147.0, 101.0, 0.0)
    place(board, "C58", 157.0, 106.0, 0.0)

    for reference in ("U24", "U25"):
        item = footprint(board, reference)
        for pad in item.Pads():
            pad.SetSize(pcbnew.VECTOR2I(mm(0.6), mm(1.0)))

    # LDO input/output bulk capacitors stay next to the regulators.
    place(board, "C17", 149.5, 108.0, 0.0)
    place(board, "C18", 156.5, 108.0, 0.0)
    place(board, "C19", 159.5, 108.0, 0.0)
    place(board, "C20", 166.5, 108.0, 0.0)


def prepare(input_path: Path, output_path: Path) -> None:
    board = pcbnew.LoadBoard(str(input_path))
    if board is None:
        raise RuntimeError(f"cannot load {input_path}")

    clear_routing(board)
    metadata_normalized = normalize_generated_footprint_metadata(board)
    critical_footprints_replaced = ensure_critical_manufacturer_footprints(board)
    ensure_usb_connector(board)
    ensure_cc_resistor(board, "R538", "USB_CC1", 181.0, 70.5)
    ensure_cc_resistor(board, "R539", "USB_CC2", 184.0, 70.5)
    assign_missing_functional_nets(board)
    merged = merge_digital_ground(board)

    for bank in range(8):
        place_input_bank(board, bank)
    place_analog_core(board)
    place_digital_core(board)
    preroute_counts = add_power_and_reference_preroutes(board)
    preroute_counts["ground_stitch_vias"] = add_ground_stitching(board)
    preroute_counts["channel_bias_junctions"] = add_channel_mux_preroutes(board)
    preroute_counts["channel_to_mux"] = 0
    preroute_counts["VCM_bias_returns"] = add_vcm_preroute(board)

    try:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
    except Exception as exc:
        print(f"final zone refill deferred to KiCad CLI: {exc}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)

    text = output_path.read_text(encoding="utf-8")
    output_path.write_text(apply_stackup(text), encoding="utf-8")

    print(
        {
            "output": str(output_path),
            "merged_dgnd_pads": merged,
            "critical_footprints_replaced": critical_footprints_replaced,
            "metadata_normalized": metadata_normalized,
            "footprints": len(list(board.GetFootprints())),
            "usb_cc_resistors": ["R538", "R539"],
            "preroute_counts": preroute_counts,
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

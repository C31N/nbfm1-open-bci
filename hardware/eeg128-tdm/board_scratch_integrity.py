#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Fail closed if a native scratch router changes a footprint or any pad.

Only routed PCB_TRACK segments may be treated as sacrificial. The geometry,
reference, UUID, net assignment and identity of all components/pads is fixed.
"""
from __future__ import annotations

from typing import Any

EXPECTED_FOOTPRINTS = 642


def _point(value: Any) -> tuple[int, int]:
    return (int(value.x), int(value.y))


def _orientation(item: Any) -> float | None:
    getter = getattr(item, "GetOrientationDegrees", None)
    return round(float(getter()), 9) if callable(getter) else None


def component_inventory(board: Any) -> dict[str, tuple[Any, ...]]:
    footprints = list(board.GetFootprints())
    if len(footprints) != EXPECTED_FOOTPRINTS:
        raise RuntimeError(
            f"Scratch PCB must contain {EXPECTED_FOOTPRINTS} footprints; "
            f"found {len(footprints)}"
        )
    identity: dict[str, tuple[Any, ...]] = {}
    pad_uuids: set[str] = set()
    for footprint in footprints:
        reference = footprint.GetReference()
        if not reference or reference in identity:
            raise RuntimeError(f"Scratch PCB duplicate/empty footprint ref: {reference!r}")
        pads: list[tuple[Any, ...]] = []
        for pad in footprint.Pads():
            uuid = pad.m_Uuid.AsString()
            if uuid in pad_uuids:
                raise RuntimeError(f"Scratch PCB duplicate pad UUID: {uuid}")
            pad_uuids.add(uuid)
            pads.append((
                uuid, str(pad.GetNumber()), pad.GetNetname(),
                _point(pad.GetPosition()), _point(pad.GetSize()),
                str(pad.GetLayerSet().FmtBin()), int(pad.GetShape()),
                _orientation(pad),
            ))
        identity[reference] = (
            footprint.m_Uuid.AsString(), _point(footprint.GetPosition()),
            int(footprint.GetLayer()), _orientation(footprint),
            str(footprint.GetValue()), tuple(sorted(pads)),
        )
    board_get_pads = getattr(board, "GetPads", None)
    if callable(board_get_pads):
        native_pads = list(board_get_pads())
        if {p.m_Uuid.AsString() for p in native_pads} != pad_uuids:
            raise RuntimeError("board.GetPads() differs from footprint pad inventory")
        if len(native_pads) != len(pad_uuids):
            raise RuntimeError("board.GetPads() contains duplicate UUIDs")
    return identity


def require_unchanged_components(
    board: Any, baseline: dict[str, tuple[Any, ...]], stage: str
) -> None:
    actual = component_inventory(board)
    if actual != baseline:
        missing = sorted(baseline.keys() - actual.keys())
        added = sorted(actual.keys() - baseline.keys())
        changed = sorted(ref for ref in baseline.keys() & actual.keys()
                         if baseline[ref] != actual[ref])
        raise RuntimeError(
            f"Footprint/pad mutation at {stage}: "
            f"missing={missing[:12]} added={added[:12]} changed={changed[:12]}"
        )

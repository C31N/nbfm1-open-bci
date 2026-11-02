#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Immutable UUID-specific F.Cu detour masks for fail-closed Block2 probes.

Extra keepout is ONLY in transient path-planning geometry, never in PCB,
project rules, track footprints, via placement or release qualification.
"""
from __future__ import annotations

from typing import Any

# Strictly pinned native 139 scratch items, confirmed in Elastic #6 UUID report.
FIXED_DETOUR_ITEMS: dict[str, tuple[str, str]] = {
    "0c622acd-a2a9-440d-a4d0-7d8cdbdc7014": ("MUX_EN", "pad"),
    "dd561592-853d-47ee-a2f3-f824a719d539": ("MUX_S2", "pad"),
    "86c11baf-c744-4d1a-a036-3274f16e955a": ("VCM", "via"),
    "ee80d57f-1703-424a-8520-9951e8db8c27": ("MUX_S2", "via"),
    "3af750bf-ef0a-495a-9e9c-4af1480ec59d": ("CH038_P_MUX", "track"),
}
EXTRA_RADIUS_MM = .32
U3_GAP_RADIUS_MM = .24


def detour_geometry(board: Any) -> tuple[Any, dict[str, Any]]:
    """Build hard search-only buffers with verified CH038 replacement mapping.

    No eligibility to change protected objects is implied by the geometry.
    The U3.14/U3.15 centre-to-centre stub becomes a forbidden search region
    to avoid the microscopically narrow pad gap. No live board mutation.
    """
    import pcbnew
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    from route_targeted_closure import pad_copper_shape, xy

    found: dict[str, tuple[Any, Any]] = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            uid = pad.m_Uuid.AsString()
            if uid not in FIXED_DETOUR_ITEMS:
                continue
            if uid in found or not pad.IsOnLayer(pcbnew.F_Cu):
                raise RuntimeError("Pinned detour pad absent from F.Cu or duplicated")
            found[uid] = (
                pad_copper_shape(pad, pcbnew.F_Cu), pad)
    for track in board.GetTracks():
        uid = track.m_Uuid.AsString()
        if uid not in FIXED_DETOUR_ITEMS:
            continue
        if uid in found:
            raise RuntimeError("Duplicated native protected UUID")
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetWidth()) / 2)
        elif isinstance(track, pcbnew.PCB_ARC):
            raise RuntimeError("Protected UUID changed to unsupported arc")
        elif track.GetLayer() == pcbnew.F_Cu:
            shape = LineString((xy(track.GetStart()), xy(track.GetEnd())
                                )).buffer(pcbnew.ToMM(track.GetWidth()) / 2)
        else:
            raise RuntimeError("Protected detour UUID changed copper layer")
        found[uid] = shape, track
    # The #6 diagnostic used the pre-restoration CH038 track. Isolated
    # CH038 restitution replaces its cut segments BEFORE the 201-victim cut.
    # Require the four stable pad/via UUIDs; fail closed if any of those
    # changed. For CH038, rediscover actual F.Cu replacement UUIDs by net.
    historical_ch038 = "3af750bf-ef0a-495a-9e9c-4af1480ec59d"
    missing = set(FIXED_DETOUR_ITEMS) - set(found)
    if missing - {historical_ch038}:
        raise RuntimeError("Protected fixed-detour UUID inventory mismatch: " +
                           ",".join(sorted(missing - {historical_ch038})))
    shapes = []
    manifest = []
    for uid, (net, kind) in FIXED_DETOUR_ITEMS.items():
        if uid == historical_ch038 and uid not in found:
            continue
        shape, obj = found[uid]
        actual_kind = (
            "pad" if isinstance(obj, pcbnew.PAD)
            else "via" if isinstance(obj, pcbnew.PCB_VIA) else "track"
        )
        if obj.GetNetname() != net or actual_kind != kind:
            raise RuntimeError("Protected detour identity or net drift: " + uid)
        # Larger than native clearance, solely for path search.
        shapes.append(shape.buffer(EXTRA_RADIUS_MM, resolution=16))
        manifest.append({"uuid": uid, "net": net, "kind": kind,
                         "search_padding_mm": EXTRA_RADIUS_MM})
    replacements = []
    if historical_ch038 not in found:
        for track in board.GetTracks():
            if (track.GetNetname() != "CH038_P_MUX"
                    or track.GetLayer() != pcbnew.F_Cu
                    or isinstance(track, (pcbnew.PCB_VIA, pcbnew.PCB_ARC))):
                continue
            uid = track.m_Uuid.AsString()
            copper = LineString((
                xy(track.GetStart()), xy(track.GetEnd())
            )).buffer(pcbnew.ToMM(track.GetWidth()) / 2)
            replacements.append((uid, copper))
        if not replacements:
            raise RuntimeError("No protected CH038 F.Cu replacement copper")
        for uid, copper in sorted(replacements):
            shapes.append(copper.buffer(EXTRA_RADIUS_MM, resolution=16))
            manifest.append({
                "uuid": uid, "net": "CH038_P_MUX",
                "kind": "replacement_track",
                "search_padding_mm": EXTRA_RADIUS_MM})
    pad_a = found["0c622acd-a2a9-440d-a4d0-7d8cdbdc7014"][1]
    pad_b = found["dd561592-853d-47ee-a2f3-f824a719d539"][1]
    gap = LineString((
        xy(pad_a.GetPosition()), xy(pad_b.GetPosition())
    )).buffer(U3_GAP_RADIUS_MM, resolution=16)
    shapes.append(gap)
    union = unary_union(shapes)
    return union, {
        "search_only": True,
        "uuid_count": len(manifest),
        "historical_CH038_uuid_absent": historical_ch038 not in found,
        "historical_CH038_uuid": historical_ch038,
        "CH038_replacement_UUIDs": sorted(uid for uid, _ in replacements),
        "protected_uuid_keepouts": manifest,
        "U3_14_15_gap_excluded": True,
        "U3_gap_buffer_mm": U3_GAP_RADIUS_MM,
        "no_board_modification": True,
        "fabrication_clearance_unchanged_mm": .15,
        "in1_used": False,
        "new_vias": 0,
        "status": "uuid_detours_applied_to_planner_only",
    }

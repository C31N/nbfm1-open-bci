#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Deterministic bounded rip-up/backtracking controller for proposed copper.

The caller owns all KiCad board state and MUST verify immutable copper,
existing pads, vias and zone outlines before accepting a proposal. This
controller only retries temporary generated tracks and never promotes
a checkpoint or creates manufacturing outputs.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from typing import Any

# Local routing variability: window + soft avoidance weight. None bypasses
# all fallback/clearance exceptions; the caller's native geometry is final.
CHOICES: tuple[tuple[float, float], ...] = (
    (3.0, 0.5),
    (6.0, 1.0),
    (3.0, 2.5),
    (6.0, 0.25),
)


def bounded_ripup(
    order: Sequence[str],
    probe: Callable[[str, float, float, Sequence[str]], tuple[Any | None, dict]],
    place: Callable[[str, Any], Sequence[str]],
    undo: Callable[[str, Sequence[str]], None],
    *,
    deadline: float,
    max_probes: int = 36,
    max_backtracks: int = 12,
    choices: Sequence[tuple[float, float]] = CHOICES,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Try alternate bounded routes, undoing ONLY tracks produced by place.

    After a failed deeper net, backtrack to the last placed net, remove its
    owned temporary objects, choose its next legal proposal and retry.
    Failures are explicitly not net-closure or DRC qualifications.
    """
    nets = tuple(order)
    if len(nets) != 8 or len(set(nets)) != 8:
        raise ValueError("Expected eight distinct mutable net names")
    if (max_probes < 1 or max_backtracks < 0 or
            not choices or any(not math.isfinite(a)
                or not math.isfinite(b) or a <= 0 or b < 0
                for a, b in choices)):
        raise ValueError("Invalid bounded backtrack search constraints")
    positions = [0] * len(nets)
    signatures: list[set[tuple]] = [set() for _ in nets]
    stack: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    best: list[dict[str, Any]] = []
    depth = 0
    probes = 0
    backtracks = 0
    outcome = "incomplete_bounded_search"

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if progress is not None:
            progress({
                "status": "bounded_backtracking_in_progress",
                "current_depth": depth,
                "best_depth": len(best),
                "probes": probes,
                "backtracks": backtracks,
                "event": event,
                "best_routes": best,
            })

    while True:
        if depth == len(nets):
            outcome = "eight_geometric_paths_proposed_not_natively_qualified"
            break
        if time.monotonic() >= deadline:
            outcome = "bounded_backtracking_time_limit"
            break
        if probes >= max_probes:
            outcome = "bounded_backtracking_probe_limit"
            break
        if positions[depth] >= len(choices):
            # No variant worked here; remove one previously created route.
            if depth == 0 or backtracks >= max_backtracks:
                outcome = ("bounded_backtracking_exhausted" if depth == 0
                           else "bounded_backtracking_rollback_limit")
                break
            depth -= 1
            previous = stack.pop()
            if previous["net"] != nets[depth]:
                raise RuntimeError("Route stack/net sequence mismatch")
            undo(previous["net"], previous["created_uuids"])
            backtracks += 1
            emit({
                "event": "rip_up_owned_proposal",
                "net": previous["net"],
                "owned_track_count": len(previous["created_uuids"]),
                "backtracks": backtracks,
            })
            continue

        margin, weight = choices[positions[depth]]
        positions[depth] += 1
        name = nets[depth]
        pending = nets[depth:]
        proposed, details = probe(name, margin, weight, pending)
        probes += 1
        emit({
            "event": "probe", "net": name, "margin_mm": margin,
            "penalty": weight, "found": proposed is not None,
            "diagnostics": details,
        })
        if proposed is None:
            continue
        signature = tuple(tuple(v) for v in proposed)
        if signature in signatures[depth]:
            emit({"event": "duplicate_path_rejected", "net": name})
            continue
        signatures[depth].add(signature)
        owned_uuids = tuple(place(name, proposed))
        if not owned_uuids or len(set(owned_uuids)) != len(owned_uuids):
            raise RuntimeError("Placed proposal lacks unique owned copper")
        route = {
            "net": name,
            "created_uuids": list(owned_uuids),
            "path": proposed,
            "margin_mm": margin,
            "penalty": weight,
        }
        stack.append(route)
        depth += 1
        if depth > len(best):
            best = [{k: v for k, v in item.items() if k != "created_uuids"}
                    for item in stack]
        emit({
            "event": "place_owned_proposal", "net": name,
            "depth": depth, "temporary_tracks": len(owned_uuids),
        })
        if depth < len(nets):
            positions[depth] = 0
            signatures[depth].clear()

    if depth != len(nets):
        # Restore the after-original-ripup board. Nothing speculative remains.
        while stack:
            item = stack.pop()
            undo(item["net"], item["created_uuids"])
        depth = 0
        emit({"event": "discard_unqualified_partial", "outcome": outcome})
    return {
        "status": outcome,
        "eight_geometric_paths_proposed": depth == len(nets),
        "connected": [
            {k: v for k, v in item.items() if k != "created_uuids"}
            for item in stack
        ],
        "best_partial_count": len(best),
        "best_partial": best,
        "backtracks": backtracks,
        "probes": probes,
        "events": events,
        "fabrication_release": False,
        "routing_completed": False,
        "accepted": False,
        "independent_replay_verified": False,
    }

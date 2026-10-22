#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Coupled three-commodity F.Cu corridor selection for MUX controls.

Enumerates a bounded candidate pool for each net and selects *complete*
nonoverlapping triples at once; order of committing temporary segments
does not affect geometric choice. A full native KiCad DRC, all-eight
connectivity, L3 zone parity, and byte-identical replay are still required.
"""
from __future__ import annotations

import math
from itertools import product
from typing import Any

TRIPLET: tuple[str, str, str] = ("MUX_EN", "MUX_S2", "MUX_S3")
# Centre-line clearance: two 0.15-mm traces plus 0.15-mm copper clearance.
MIN_CENTER_SEPARATION_MM = .30001


def coupled_candidates(
    pools: dict[str, list[dict[str, Any]]],
    *, maximum_combinations: int = 256,
    maximum_plans: int = 6,
) -> dict[str, Any]:
    """Exact continuous-Shapely segment separation across all three nets.

    Pools are *independently* proposed on identical fixed-copper snapshots.
    Combined candidates are tested simultaneously before any new copper is
    committed. Sampling/grid optimization is never treated as native DRC.
    """
    from shapely.geometry import LineString

    if set(pools) != set(TRIPLET) or any(not pools[name] for name in TRIPLET):
        return {"status": "incomplete_joint_candidate_pools",
                "plans": [], "combination_count": 0,
                "collisions": [], "native_DRC_qualified": False}
    if maximum_plans <= 0 or maximum_combinations <= 0:
        raise ValueError("Strictly positive joint solver limits required")
    prepared: dict[str, list[dict[str, Any]]] = {}
    for name in TRIPLET:
        prepared[name] = []
        for idx, candidate in enumerate(pools[name]):
            path = candidate["path"]
            if len(path) < 2 or any(
                    len(p) != 3 or p[0] != 0 or
                    any(not math.isfinite(float(x)) for x in p[1:])
                    for p in path):
                raise ValueError("Joint candidate must be finite F.Cu only")
            line = LineString([(p[1], p[2]) for p in path])
            if line.is_empty or line.length < .000001:
                raise ValueError("Zero-length joint routing candidate")
            prepared[name].append({
                "candidate": candidate,
                "index": idx,
                "line": line,
                "length_mm": line.length,
            })
    attempts = 0
    collisions: dict[str, dict[str, Any]] = {}
    plans: list[dict[str, Any]] = []
    for items in product(*(prepared[name] for name in TRIPLET)):
        if attempts >= maximum_combinations:
            break
        attempts += 1
        pairwise: dict[str, float] = {}
        bad = False
        for i in range(3):
            for j in range(i + 1, 3):
                a, b = TRIPLET[i], TRIPLET[j]
                separation = items[i]["line"].distance(items[j]["line"])
                pairwise[a + ":" + b] = round(separation, 9)
                if separation + 1e-10 < MIN_CENTER_SEPARATION_MM:
                    bad = True
                    key = a + ":" + b
                    existing = collisions.get(key)
                    if existing is None or existing["minimum_mm"] > separation:
                        collisions[key] = {
                            "minimum_mm": round(separation, 9),
                            "required_mm": MIN_CENTER_SEPARATION_MM,
                            "candidate_indices": {
                                a: items[i]["index"],
                                b: items[j]["index"],
                            },
                        }
        if bad:
            continue
        total_length = sum(x["length_mm"] for x in items)
        min_sep = min(pairwise.values())
        # Rank compact, separated bundles ahead of near-tangent arrangements.
        score = total_length + .075 / max(
            min_sep - MIN_CENTER_SEPARATION_MM + .01, .01)
        plans.append({
            "score": round(score, 6),
            "total_length_mm": round(total_length, 6),
            "minimum_pair_center_separation_mm": round(min_sep, 9),
            "pairwise_mm": pairwise,
            "paths": {
                TRIPLET[i]: items[i]["candidate"]["path"]
                for i in range(3)
            },
            "candidate_indices": {
                TRIPLET[i]: items[i]["index"]
                for i in range(3)
            },
            "native_DRC_qualified": False,
        })
    plans.sort(key=lambda p: (
        p["score"], p["candidate_indices"]["MUX_EN"],
        p["candidate_indices"]["MUX_S2"],
        p["candidate_indices"]["MUX_S3"]))
    return {
        "status": ("joint_three_commodity_geometries_proposed"
                   if plans else "no_joint_nonoverlapping_triplet"),
        "plans": plans[:maximum_plans],
        "combination_count": attempts,
        "compatible_combination_count": len(plans),
        "collisions": collisions,
        "candidate_pool_sizes": {
            name: len(pools[name]) for name in TRIPLET},
        "power_protection_inherited_from_native_candidate_routes": True,
        "native_DRC_qualified": False,
        "accepted": False,
        "fabrication_release": False,
        "routing_completed": False,
    }

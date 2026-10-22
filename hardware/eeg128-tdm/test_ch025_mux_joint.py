#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Synthetic simultaneous three-net corridor and release safety tests."""
from __future__ import annotations

import unittest
from typing import Any

from ch025_mux_joint import (
    TRIPLET, MIN_CENTER_SEPARATION_MM, coupled_candidates,
)


class CoupledMuxTests(unittest.TestCase):
    def test_joint_resolves_incompatible_individual_first_choices(self) -> None:
        pools: dict[str, list[dict[str, Any]]] = {
            "MUX_EN": [
                {"path": [(0,0.,0.),(0,10.,0.)]},
                {"path": [(0,0.,-1.),(0,10.,-1.)]},
            ],
            "MUX_S2": [
                {"path": [(0,0.,.1),(0,10.,.1)]},
                {"path": [(0,0.,-.55),(0,10.,-.55)]},
            ],
            "MUX_S3": [
                {"path": [(0,0.,1.),(0,10.,1.)]},
            ],
        }
        result = coupled_candidates(pools)
        self.assertEqual(result["status"],
                         "joint_three_commodity_geometries_proposed")
        self.assertGreater(result["compatible_combination_count"],0)
        indices = result["plans"][0]["candidate_indices"]
        # Global optimizer may prefer either alternate net; only the
        # individually optimal colliding pair (0, 0) is forbidden.
        self.assertNotEqual(
            (indices["MUX_EN"], indices["MUX_S2"]), (0, 0))
        self.assertGreaterEqual(result["plans"][0][
            "minimum_pair_center_separation_mm"], MIN_CENTER_SEPARATION_MM)
        self.assertFalse(result["accepted"])

    def test_all_individual_paths_can_exist_without_compatible_triple(
            self) -> None:
        pools: dict[str,list[dict[str,Any]]] = {
            name: [{"path": [(0,0.,0.),(0,5.,0.)]}]
            for name in TRIPLET
        }
        result = coupled_candidates(pools)
        self.assertEqual(result["status"],
                         "no_joint_nonoverlapping_triplet")
        self.assertFalse(result["plans"])
        self.assertFalse(result["fabrication_release"])

    def test_bad_layer_rejected(self) -> None:
        pools: dict[str,list[dict[str,Any]]] = {
            name: [{"path":[(0,0.,0.),(0,5.,1.)]}]
            for name in TRIPLET
        }
        pools["MUX_S2"]=[{"path":[(1,0.,0.),(1,5.,1.)]}]
        with self.assertRaises(ValueError):
            coupled_candidates(pools)

    def test_missing_network_never_promoted(self) -> None:
        result=coupled_candidates({
            "MUX_EN": [{"path":[(0,0.,0.),(0,1.,0.)]}],
            "MUX_S2": [],
            "MUX_S3": [{"path":[(0,0.,1.),(0,1.,1.)]}],
        })
        self.assertFalse(result["plans"])
        self.assertFalse(result["native_DRC_qualified"])


if __name__ == "__main__":
    unittest.main()

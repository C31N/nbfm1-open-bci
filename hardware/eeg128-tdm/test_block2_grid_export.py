#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Diagnostic F.Cu grid export roundtrip and fail-closed manifest."""
from __future__ import annotations

import unittest

import numpy as np

from probe_block2_grid_export import (
    decode_sealed_midpoint_grid,
    export_sealed_midpoint_grid,
)


class NativeMacroGridExportTests(unittest.TestCase):
    def test_deterministic_bitpack_roundtrip(self) -> None:
        rows,cols=23,31
        xs=np.arange(cols,dtype=float)*.22+21.5
        ys=np.arange(rows,dtype=float)*.22+9.25
        masks=[]
        for i in range(3):
            mask=np.zeros((rows,cols),dtype=bool)
            mask[4+i:15,11+i:13+i]=True
            mask[3+i,3+i]=True
            masks.append(mask)
        starts=[(2,2),(2,5),(2,8)]
        goals=[(28,17),(28,19),(28,21)]
        report=export_sealed_midpoint_grid(
            masks,xs,ys,starts,goals,"a"*64,"b"*64)
        copies=decode_sealed_midpoint_grid(report)
        for i in range(3):
            self.assertTrue(np.array_equal(masks[i],copies[i]))
            self.assertEqual(report["agents"][i]["start"],list(starts[i]))
            self.assertEqual(report["agents"][i]["goal"],list(goals[i]))
        self.assertEqual(report["grid_rows"],rows)
        self.assertEqual(report["grid_cols"],cols)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["routing_completed"])
        self.assertFalse(report["fabrication_release"])
        again=export_sealed_midpoint_grid(
            masks,xs,ys,starts,goals,"a"*64,"b"*64)
        self.assertEqual(report,again)

    def test_sha256_tamper_rejected(self) -> None:
        xs=np.arange(20,dtype=float)*.22
        ys=np.arange(20,dtype=float)*.22
        masks=[np.zeros((20,20),dtype=bool) for _ in range(3)]
        report=export_sealed_midpoint_grid(
            masks,xs,ys,[(1,1)]*3,[(17,17)]*3,
            "a"*64,"b"*64)
        report["agents"][0]["bitpack_sha256"]="0"*64
        with self.assertRaisesRegex(RuntimeError,"integrity failure"):
            decode_sealed_midpoint_grid(report)

    def test_invalid_identity_rejected(self) -> None:
        xs=np.arange(20,dtype=float)*.22
        ys=np.arange(20,dtype=float)*.22
        with self.assertRaisesRegex(RuntimeError,
                                    "Three distinct"):
            export_sealed_midpoint_grid(
                [np.zeros((20,20),dtype=bool)],
                xs,ys,[(1,1)]*3,[(17,17)]*3,"a"*64,"b"*64)


if __name__=="__main__":
    unittest.main()

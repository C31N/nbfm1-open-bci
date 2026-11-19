#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Strict staged three-bound-net evasion preflight; never a native release."""
import math
from typing import Dict, List, Optional, Tuple

import pytest
from local_joint_astar_partial_free import (
    PointMM, ThreeNetEvasionConfig, ThreeNetEvasionGenerator,
)

NETS = ("CH028_N_MUX", "CH029_N_MUX", "CH030_N_MUX")


def _make_generator(
    blocked_points: Optional[Dict[str, List[PointMM]]] = None,
    blocked_segments: Optional[Dict[str, List[Tuple[PointMM, PointMM]]]] = None,
    cfg: Optional[ThreeNetEvasionConfig] = None,
):
    blocked_pts = blocked_points or {}
    blocked_segs = blocked_segments or {}
    rejections: List[Tuple[str, int]] = []

    def is_point_clear(net: str, pt: PointMM, _min_clear: float) -> bool:
        return not any(
            math.hypot(pt[0] - bp[0], pt[1] - bp[1]) < 1e-4
            for bp in blocked_pts.get(net, ()))

    def is_segment_clear(net: str, p0: PointMM, p1: PointMM,
                         _min_clear: float) -> bool:
        return not any(
            (p0, p1) == (s0, s1) or (p0, p1) == (s1, s0)
            for s0, s1 in blocked_segs.get(net, ()))

    def record_rejection(reason: str, bound_count: int) -> None:
        rejections.append((reason, bound_count))

    return (ThreeNetEvasionGenerator(
        net_order=NETS,
        is_point_clear=is_point_clear,
        is_segment_clear=is_segment_clear,
        record_rejection=record_rejection,
        config=cfg or ThreeNetEvasionConfig(step_mm=.250),
    ), rejections)


@pytest.fixture
def targets() -> Dict[str, PointMM]:
    return {NETS[0]: (48., 23.4), NETS[1]: (48., 26.),
            NETS[2]: (48., 28.6)}


@pytest.fixture
def positions() -> Dict[str, Optional[PointMM]]:
    return {NETS[0]: (40., 35.), NETS[1]: (40.3, 35.),
            NETS[2]: (40.6, 35.)}


def test_sync_goal_emits_direct_step_when_unobstructed(targets, positions):
    gen, rejections = _make_generator()
    results = list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    assert len(results) >= 1
    assert results[0][2] == "SYNC_GOAL"
    assert all(results[0][0][n] != positions[n] for n in NETS)
    assert rejections == []


def test_skips_when_any_net_is_unbound_none(targets, positions):
    gen, rejections = _make_generator()
    positions[NETS[2]] = None
    headings = {NETS[0]: 0, NETS[1]: 0, NETS[2]: None}
    assert list(gen.generate_evasion_steps(positions, headings, targets)) == []
    assert rejections == []


def test_single_evade_when_one_net_has_blocked_goal_step(targets, positions):
    gen_probe, _ = _make_generator()
    blocked = gen_probe._step_point(
        positions[NETS[1]],
        gen_probe._goal_heading(positions[NETS[1]], targets[NETS[1]]),
        .250)
    gen, rejections = _make_generator(blocked_points={NETS[1]: [blocked]})
    results = list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    assert any(tag.startswith("SINGLE_EVADE_CH029_N_MUX_")
               for _, _, tag in results)
    assert rejections and all(bound == 3 for _, bound in rejections)


def test_rejects_pair_pitch_violation_below_300um(targets):
    gen, rejections = _make_generator()
    positions = {NETS[0]: (40., 35.), NETS[1]: (40.1, 35.),
                 NETS[2]: (40.2, 35.)}
    assert list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets)) == []
    assert ("pair_pitch", 3) in rejections


def test_respects_max_evasion_candidates_cap(targets, positions):
    cfg = ThreeNetEvasionConfig(step_mm=.250, max_evasion_candidates=2)
    gen, _ = _make_generator(cfg=cfg)
    assert len(list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))) <= 2


def test_pitch_configuration_cannot_be_weakened():
    with pytest.raises(ValueError):
        ThreeNetEvasionConfig(min_pitch_mm=.299)
    with pytest.raises(ValueError):
        ThreeNetEvasionConfig(max_evasion_candidates=0)


def test_generator_rejects_direct_blocked_segment(targets, positions):
    probe, _ = _make_generator()
    net = NETS[0]
    p0 = positions[net]
    p1 = probe._step_point(p0, probe._goal_heading(p0, targets[net]), .250)
    gen, rejected = _make_generator(blocked_segments={net: [(p0, p1)]})
    results = list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    assert results
    assert all(not tag.startswith("SYNC_GOAL") for _, _, tag in results)
    assert ("evasion_segment_blocked", 3) in rejected

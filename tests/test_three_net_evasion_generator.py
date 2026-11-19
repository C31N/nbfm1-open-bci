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
) -> tuple[ThreeNetEvasionGenerator, List[Tuple[str, int]]]:
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


def test_sync_goal_emits_direct_step_when_unobstructed(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    gen, rejections = _make_generator()
    results = list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    assert len(results) >= 1
    assert results[0][2] == "SYNC_GOAL"
    assert all(results[0][0][n] != positions[n] for n in NETS)
    assert rejections == []


def test_skips_when_any_net_is_unbound_none(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    gen, rejections = _make_generator()
    positions[NETS[2]] = None
    headings = {NETS[0]: 0, NETS[1]: 0, NETS[2]: None}
    assert list(gen.generate_evasion_steps(positions, headings, targets)) == []
    assert rejections == []


def test_single_evade_when_one_net_has_blocked_goal_step(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
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


def test_rejects_pair_pitch_violation_below_300um(
    targets: Dict[str, PointMM],
) -> None:
    gen, rejections = _make_generator()
    positions = {NETS[0]: (40., 35.), NETS[1]: (40.1, 35.),
                 NETS[2]: (40.2, 35.)}
    assert list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets)) == []
    assert ("pair_pitch", 3) in rejections


def test_staggered_evasion_holds_one_track_without_creating_a_segment(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    probe, _ = _make_generator()
    blocked: Dict[str, List[PointMM]] = {n: [] for n in NETS}
    # The first track is completely blocked. Only channels 1 and 2
    # have a goal-directed step available, so the first must HOLD.
    for name in NETS:
        p = positions[name]
        blocked[name] = [
            probe._step_point(p, direction, .250)
            for direction in range(8)]
    for name in NETS[1:]:
        p = positions[name]
        dest = probe._step_point(
            p, probe._goal_heading(p, targets[name]), .250)
        blocked[name] = [
            q for q in blocked[name] if math.dist(q, dest) > 1e-6]
    gen, _ = _make_generator(blocked_points=blocked)
    results = list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    assert results
    assert all(tag.startswith("STAGGERED_EVADE")
               for _, _, tag in results)
    assert all(next_pos[NETS[0]] == positions[NETS[0]]
               for next_pos, _, _ in results)
    assert any(next_pos[NETS[1]] != positions[NETS[1]]
               and next_pos[NETS[2]] != positions[NETS[2]]
               for next_pos, _, _ in results)


def test_coupled_turn_does_not_suppress_staggered_alternative(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    probe, _ = _make_generator()
    goal = {n: probe._goal_heading(positions[n], targets[n])
            for n in NETS}
    coupled = {n: probe._step_point(
        positions[n], (goal[n] - 1) % 8, .250) for n in NETS}
    staggered = {
        NETS[0]: positions[NETS[0]],
        NETS[1]: probe._step_point(positions[NETS[1]], goal[NETS[1]], .250),
        NETS[2]: probe._step_point(positions[NETS[2]], goal[NETS[2]], .250),
    }
    accepted_keys = {
        tuple(coupled[n] for n in NETS),
        tuple(staggered[n] for n in NETS),
    }
    rejections: List[Tuple[str, int]] = []

    def record(reason: str, bound: int) -> None:
        rejections.append((reason, bound))

    generator = ThreeNetEvasionGenerator(
        net_order=NETS,
        is_point_clear=lambda _n, _p, _c: True,
        is_segment_clear=lambda _n, _a, _b, _c: True,
        is_joint_clear=lambda p: (
            True if tuple(p[n] for n in NETS) in accepted_keys
            else "synthetic_blocked_joint"),
        record_rejection=record,
        config=ThreeNetEvasionConfig(step_mm=.250),
    )
    results = list(generator.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))
    tags = [tag for _, _, tag in results]
    assert any(tag.startswith("COUPLED_TURN") for tag in tags)
    assert any(tag.startswith("STAGGERED_EVADE") for tag in tags)
    assert ("synthetic_blocked_joint", 3) in rejections


def test_respects_max_evasion_candidates_cap(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    cfg = ThreeNetEvasionConfig(step_mm=.250, max_evasion_candidates=2)
    gen, _ = _make_generator(cfg=cfg)
    assert len(list(gen.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets))) <= 2


def test_pitch_configuration_cannot_be_weakened() -> None:
    with pytest.raises(ValueError):
        ThreeNetEvasionConfig(min_pitch_mm=.299)
    with pytest.raises(ValueError):
        ThreeNetEvasionConfig(max_evasion_candidates=0)


def test_generator_rejects_direct_blocked_segment(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
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

def test_joint_native_gate_rejections_are_logged_at_three_bound(
    targets: Dict[str, PointMM], positions: Dict[str, Optional[PointMM]],
) -> None:
    rejections: List[Tuple[str, int]] = []

    def record(reason: str, bound_count: int) -> None:
        rejections.append((reason, bound_count))

    generator = ThreeNetEvasionGenerator(
        net_order=NETS,
        is_point_clear=lambda _n, _p, _c: True,
        is_segment_clear=lambda _n, _a, _b, _c: True,
        is_joint_clear=lambda _p: "continuous_segment_pitch",
        record_rejection=record,
        config=ThreeNetEvasionConfig(step_mm=.250),
    )
    assert list(generator.generate_evasion_steps(
        positions, dict.fromkeys(NETS, 0), targets)) == []
    assert rejections and all((reason, count) ==
                              ("continuous_segment_pitch", 3)
                              or (reason == "pair_pitch" and count == 3)
                              for reason, count in rejections)

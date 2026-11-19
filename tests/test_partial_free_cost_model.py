# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic calibration invariants supplied for PartialFreeCostModel."""
from __future__ import annotations

from typing import Callable

import pytest

from local_joint_astar_partial_free import (
    PartialFreeCostModel,
    PartialFreeWeights,
)


@pytest.fixture
def model() -> PartialFreeCostModel:
    return PartialFreeCostModel(PartialFreeWeights())


@pytest.fixture
def targets() -> dict[str, tuple[float, float]]:
    return {
        "CH028_N_MUX": (48.0, 23.4),
        "CH029_N_MUX": (48.0, 26.0),
        "CH030_N_MUX": (48.0, 28.6),
    }


def _flat_edt(clearance_mm: float) -> Callable[[tuple[float, float]], float]:
    return lambda _pt: clearance_mm


def test_transition_cost_is_strictly_positive_even_with_early_bind_bonus(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """Assert positive delta-g even after early binding discount."""
    prev_pos = {
        "CH028_N_MUX": (38.0, 41.0),
        "CH029_N_MUX": (38.3, 41.0),
        "CH030_N_MUX": None,
    }
    next_pos = {
        "CH028_N_MUX": (38.0, 41.0),
        "CH029_N_MUX": (38.3, 41.0),
        "CH030_N_MUX": (38.6, 41.0),
    }
    headings = {net: 0 for net in targets}
    cost = model.transition_cost(
        prev_positions=prev_pos,
        next_positions=next_pos,
        prev_headings=headings,
        next_headings=headings,
        targets=targets,
        edt_lookup=_flat_edt(1.50),
    )
    assert cost >= 0.02


def test_early_third_net_binding_is_cheaper_than_late_binding(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """Binding before approaching target is cheaper than very late binding."""
    headings = {net: 0 for net in targets}
    edt = _flat_edt(0.80)
    early_prev = {
        "CH028_N_MUX": (38.0, 41.0),
        "CH029_N_MUX": (38.3, 41.0),
        "CH030_N_MUX": None,
    }
    early_next = {
        "CH028_N_MUX": (38.0, 40.8),
        "CH029_N_MUX": (38.3, 40.8),
        "CH030_N_MUX": (38.6, 40.8),
    }
    early_cost = model.transition_cost(
        early_prev, early_next, headings, headings, targets, edt
    )
    late_prev = {
        "CH028_N_MUX": (47.0, 24.4),
        "CH029_N_MUX": (47.3, 27.0),
        "CH030_N_MUX": None,
    }
    late_next = {
        "CH028_N_MUX": (47.0, 24.2),
        "CH029_N_MUX": (47.3, 26.8),
        "CH030_N_MUX": (47.6, 29.4),
    }
    late_cost = model.transition_cost(
        late_prev, late_next, headings, headings, targets, edt
    )
    assert early_cost < late_cost


def test_pitch_harmony_penalizes_deviation_from_300um_bundle(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """0.300-mm adjacent pitch should beat artificially spread tracks."""
    headings = {net: 0 for net in targets}
    edt = _flat_edt(0.80)
    prev_pos = {
        "CH028_N_MUX": (40.0, 35.0),
        "CH029_N_MUX": (40.3, 35.0),
        "CH030_N_MUX": (40.6, 35.0),
    }
    ideal_next = {
        "CH028_N_MUX": (40.0, 34.8),
        "CH029_N_MUX": (40.3, 34.8),
        "CH030_N_MUX": (40.6, 34.8),
    }
    spread_next = {
        "CH028_N_MUX": (39.8, 34.8),
        "CH029_N_MUX": (40.3, 34.8),
        "CH030_N_MUX": (40.9, 34.8),
    }
    cost_ideal = model.transition_cost(
        prev_pos, ideal_next, headings, headings, targets, edt
    )
    cost_spread = model.transition_cost(
        prev_pos, spread_next, headings, headings, targets, edt
    )
    assert cost_ideal < cost_spread


def test_edt_proximity_penalizes_tight_obstacle_clearance(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """A still-permitted near-wall route gets a larger soft cost."""
    headings = {net: 0 for net in targets}
    prev_pos = {
        "CH028_N_MUX": (40.0, 35.0),
        "CH029_N_MUX": (40.3, 35.0),
        "CH030_N_MUX": (40.6, 35.0),
    }
    next_pos = {
        "CH028_N_MUX": (40.0, 34.8),
        "CH029_N_MUX": (40.3, 34.8),
        "CH030_N_MUX": (40.6, 34.8),
    }
    cost_tight = model.transition_cost(
        prev_pos, next_pos, headings, headings, targets, _flat_edt(0.23)
    )
    cost_open = model.transition_cost(
        prev_pos, next_pos, headings, headings, targets, _flat_edt(1.20)
    )
    assert cost_tight > cost_open


def test_progress_synchronization_penalizes_lagging_third_net(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """Penalty rises when the third net lags behind the other two."""
    headings = {net: 0 for net in targets}
    edt = _flat_edt(0.80)
    prev_pos = {
        "CH028_N_MUX": (44.0, 30.0),
        "CH029_N_MUX": (44.3, 30.0),
        "CH030_N_MUX": (44.6, 30.0),
    }
    synced_next = {
        "CH028_N_MUX": (44.0, 29.8),
        "CH029_N_MUX": (44.3, 29.8),
        "CH030_N_MUX": (44.6, 29.8),
    }
    lagging_next = {
        "CH028_N_MUX": (44.0, 29.8),
        "CH029_N_MUX": (44.3, 29.8),
        "CH030_N_MUX": (40.0, 38.0),
    }
    cost_synced = model.transition_cost(
        prev_pos, synced_next, headings, headings, targets, edt
    )
    cost_lagging = model.transition_cost(
        prev_pos, lagging_next, headings, headings, targets, edt
    )
    assert cost_synced < cost_lagging


def test_heuristic_includes_unbound_none_net_estimate(
    model: PartialFreeCostModel, targets: dict[str, tuple[float, float]],
) -> None:
    """None third net must not be assigned an artificial zero heuristic."""
    anchors = {
        "CH028_N_MUX": [(38.0, 41.0)],
        "CH029_N_MUX": [(38.3, 41.0)],
        "CH030_N_MUX": [(38.6, 41.0)],
    }
    pos_two_bound = {
        "CH028_N_MUX": (44.0, 26.0),
        "CH029_N_MUX": (44.3, 27.0),
        "CH030_N_MUX": None,
    }
    pos_only_two_counted = {
        "CH028_N_MUX": (44.0, 26.0),
        "CH029_N_MUX": (44.3, 27.0),
        "CH030_N_MUX": targets["CH030_N_MUX"],
    }
    h_with_unbound = model.heuristic(pos_two_bound, targets, anchors)
    h_without_third = model.heuristic(pos_only_two_counted, targets, anchors)
    assert h_with_unbound > h_without_third
    assert h_with_unbound == pytest.approx(
        h_without_third
        + model._dist((38.6, 41.0), targets["CH030_N_MUX"])
        * model.w.unbound_heuristic_damp
    )

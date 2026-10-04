# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from secure_stream import DecoderFrame, SecureFrameDecoder, SecureFrameExporter  # noqa: E402


def make_frame(probability: float) -> DecoderFrame:
    return DecoderFrame(
        timestamp_ns=123,
        intent_probability=probability,
        motor_mean=np.zeros(4, dtype=np.float32),
        motor_log_std=np.zeros(4, dtype=np.float32),
        speech_logits=np.arange(24, dtype=np.float32).reshape(4, 6),
    )


def test_gate_zeroizes_below_threshold() -> None:
    key = bytes(range(32))
    exporter = SecureFrameExporter(key, 0.95)
    decoder = SecureFrameDecoder(key)
    frame = decoder.decode(exporter.encrypt_frame(make_frame(0.50)))
    assert not frame.speech_allowed
    assert np.count_nonzero(frame.speech_logits) == 0


def test_gate_releases_above_threshold() -> None:
    key = bytes(reversed(range(32)))
    exporter = SecureFrameExporter(key, 0.95)
    decoder = SecureFrameDecoder(key)
    frame = decoder.decode(exporter.encrypt_frame(make_frame(0.99)))
    assert frame.speech_allowed
    assert np.count_nonzero(frame.speech_logits) > 0

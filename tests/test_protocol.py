# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from ring_protocol import (  # noqa: E402
    BCI_DMA_SLOT_BYTES,
    BCI_FLAG_FNIRS_PRESENT,
    build_packet,
    crc32c,
    parse_slot,
)


def test_crc32c_known_vector() -> None:
    assert crc32c(b"123456789") == 0xE3069283


def test_packet_roundtrip() -> None:
    eeg = np.arange(128, dtype=np.int32)
    meg = -np.arange(128, dtype=np.int32)
    long_frame = np.ones((128, 2), dtype=np.uint32) * 1_000_000
    short_frame = np.ones((32, 2), dtype=np.uint32) * 800_000
    slot = build_packet(7, 123456789, eeg, meg, long_frame, short_frame, 3)
    assert len(slot) == BCI_DMA_SLOT_BYTES
    parsed = parse_slot(slot)
    assert parsed.sequence == 7
    assert parsed.timestamp_ns == 123456789
    assert parsed.flags & BCI_FLAG_FNIRS_PRESENT
    np.testing.assert_array_equal(parsed.eeg, eeg.astype(np.float32))
    np.testing.assert_array_equal(parsed.meg, meg.astype(np.float32))

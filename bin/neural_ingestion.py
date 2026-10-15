# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded local LSL ingestion with explicit clock correction and loss counters."""
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any
import numpy as np


class SampleRing:
    def __init__(self, capacity: int, channels: int) -> None:
        if capacity < 1 or channels < 1:
            raise ValueError('Positive ring dimensions required')
        self.capacity, self.channels = capacity, channels
        self.data = np.empty((capacity, channels), dtype=np.float32)
        self.timestamps = np.empty(capacity, dtype=np.float64)
        self.read_index = self.count = self.dropped = 0
        self.last_timestamp = -np.inf
        self.lock = Lock()

    def push(self, samples: np.ndarray, timestamps: np.ndarray) -> None:
        x, t = np.asarray(samples, dtype=np.float32), np.asarray(timestamps, dtype=float)
        if (x.ndim != 2 or x.shape[1] != self.channels or t.shape != (len(x),)
                or not np.isfinite(x).all() or not np.isfinite(t).all()
                or np.any(np.diff(t) <= 0)):
            raise ValueError('Finite ordered sample timestamps required')
        with self.lock:
            if len(t) and t[0] <= self.last_timestamp:
                raise ValueError('Stream timestamp regressed')
            for sample, timestamp in zip(x, t):
                if self.count == self.capacity:
                    self.read_index = (self.read_index+1) % self.capacity
                    self.count -= 1
                    self.dropped += 1
                index = (self.read_index+self.count) % self.capacity
                self.data[index], self.timestamps[index] = sample, timestamp
                self.count += 1
                self.last_timestamp = timestamp

    def pop(self, maximum: int) -> tuple[np.ndarray, np.ndarray]:
        if maximum < 1:
            raise ValueError('Positive chunk size required')
        with self.lock:
            count = min(maximum, self.count)
            indices = (np.arange(count)+self.read_index) % self.capacity
            x, t = self.data[indices].copy(), self.timestamps[indices].copy()
            self.read_index = (self.read_index+count) % self.capacity
            self.count -= count
            return x, t


class LSLIngestion:
    """LSL itself is plaintext. Use only within the trusted acquisition domain."""

    def __init__(self, info: Any, ring: Any, chunk: int = 32) -> None:
        from pylsl import StreamInlet, cf_float32
        if (chunk < 1 or info.channel_count() != ring.channels
                or info.channel_format() != cf_float32):
            raise ValueError('A matching float32 LSL stream is required')
        self.ring, self.chunk = ring, chunk
        self.buffer = np.empty((chunk, ring.channels), dtype=np.float32)
        self.inlet = StreamInlet(info, max_buflen=2, max_chunklen=chunk, recover=False,
                                 processing_flags=0)
        self.inlet.open_stream(timeout=5.)
        self.correction = self.inlet.time_correction(timeout=5.)

    def poll(self) -> int:
        from pylsl.util import TimeoutError
        try:
            self.correction = self.inlet.time_correction(timeout=0.)
        except TimeoutError:
            # Initial correction was acquired before entering the polling loop.
            self.correction = float(self.correction)
        _, stamps = self.inlet.pull_chunk(timeout=0., max_samples=self.chunk,
                                          dest_obj=self.buffer)
        count = len(stamps)
        if count:
            self.ring.push(self.buffer[:count], np.asarray(stamps)+self.correction)
        return count

    def close(self) -> None:
        self.inlet.close_stream()


class CausalContext:
    """Native-rate context: select only acquired samples at or before fast time."""

    def __init__(self, channels: int, capacity: int = 64) -> None:
        if channels < 1 or capacity < 1:
            raise ValueError('Invalid context dimensions')
        self.channels = channels
        self.history: deque[tuple[float, np.ndarray]] = deque(maxlen=capacity)

    def update(self, timestamp: float, values: np.ndarray) -> None:
        x = np.asarray(values, dtype=np.float32)
        if (not np.isfinite(timestamp) or x.shape != (self.channels,)
                or not np.isfinite(x).all()
                or self.history and timestamp <= self.history[-1][0]):
            raise ValueError('Invalid or nonmonotonic context')
        self.history.append((timestamp, x.copy()))

    def at(self, fast_timestamp: float, count: int, maximum_age: float) -> np.ndarray:
        if count < 1 or maximum_age <= 0 or not np.isfinite(fast_timestamp):
            raise ValueError('Invalid context query')
        eligible = [x for t, x in self.history if 0 <= fast_timestamp-t <= maximum_age]
        if len(eligible) < count:
            raise RuntimeError('Insufficient causal context; do not synthesize missing sensors')
        return np.stack(eligible[-count:], axis=1)

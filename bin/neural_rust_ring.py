# SPDX-License-Identifier: AGPL-3.0-only
"""Owned, serialized ctypes wrapper around the preallocated Rust ring."""
from __future__ import annotations

import ctypes as ct
from pathlib import Path
from threading import Lock
import numpy as np


class RustRing:
    def __init__(self, library: Path, capacity: int, channels: int) -> None:
        if capacity < 1 or channels < 1 or capacity*channels > 16777216:
            raise ValueError('Invalid native ring dimensions')
        self.lib = ct.CDLL(str(library.resolve()))
        self.lib.nbfm_ring_new.argtypes = [ct.c_size_t, ct.c_size_t]
        self.lib.nbfm_ring_new.restype = ct.c_void_p
        self.lib.nbfm_ring_push.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_size_t]
        self.lib.nbfm_ring_push.restype = ct.c_bool
        self.lib.nbfm_ring_pop.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_size_t]
        self.lib.nbfm_ring_pop.restype = ct.c_size_t
        self.lib.nbfm_ring_dropped.argtypes = [ct.c_void_p]
        self.lib.nbfm_ring_dropped.restype = ct.c_uint64
        self.lib.nbfm_ring_free.argtypes = [ct.c_void_p]
        self.lib.nbfm_ring_free.restype = None
        self.handle = self.lib.nbfm_ring_new(capacity, channels)
        if not self.handle:
            raise RuntimeError('Native ring allocation refused')
        self.channels, self.capacity, self.lock = channels, capacity, Lock()

    def push(self, samples: np.ndarray, timestamps: np.ndarray) -> None:
        x = np.ascontiguousarray(samples, dtype=np.float32)
        t = np.ascontiguousarray(timestamps, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.channels or t.shape != (len(x),):
            raise ValueError('Invalid native chunk dimensions')
        with self.lock:
            if not self.handle:
                raise RuntimeError('Native ring closed')
            if not self.lib.nbfm_ring_push(self.handle, x.ctypes.data, t.ctypes.data, len(x)):
                raise ValueError('Native ring rejected chunk or timestamps')

    def pop(self, maximum: int) -> tuple[np.ndarray, np.ndarray]:
        if maximum < 1:
            raise ValueError('Positive pop count required')
        count = min(maximum, self.capacity)
        x, t = np.empty((count,self.channels),np.float32), np.empty(count,np.float64)
        with self.lock:
            if not self.handle:
                raise RuntimeError('Native ring closed')
            written = self.lib.nbfm_ring_pop(self.handle, x.ctypes.data, t.ctypes.data, count)
        return x[:written], t[:written]

    @property
    def dropped(self) -> int:
        with self.lock:
            if not self.handle:
                raise RuntimeError('Native ring closed')
            return int(self.lib.nbfm_ring_dropped(self.handle))

    def close(self) -> None:
        with self.lock:
            if self.handle:
                self.lib.nbfm_ring_free(self.handle)
                self.handle = None

    def __enter__(self) -> RustRing:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

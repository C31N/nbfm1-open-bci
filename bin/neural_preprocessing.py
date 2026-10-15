# SPDX-License-Identifier: AGPL-3.0-only
"""Causal, chunk-invariant filtering. No claim of complete EMG removal."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt


class StreamingPreprocessor:
    """Samples x channels; state belongs to one stream and sample rate."""

    def __init__(self, channels: int, sample_rate: float, low_hz: float = .5,
                 high_hz: float = 100., alpha: float = .999,
                 spatial: np.ndarray | None = None) -> None:
        if (channels < 1 or not 0 < low_hz < high_hz < sample_rate/2
                or not 0 < alpha < 1):
            raise ValueError('Invalid channel count, Nyquist bounds or adaptation rate')
        self.channels, self.alpha = channels, alpha
        self.sos = butter(4, [low_hz, high_hz], btype='bandpass', fs=sample_rate, output='sos')
        self.state = np.zeros((len(self.sos), 2, channels))
        self.mean, self.variance = np.zeros(channels), np.ones(channels)
        self.spatial = (np.eye(channels)-np.ones((channels, channels))/channels
                        if spatial is None else np.asarray(spatial, dtype=np.float64).copy())
        if self.spatial.shape != (channels, channels) or not np.isfinite(self.spatial).all():
            raise ValueError('Spatial projection must be a finite square channel matrix')

    def process(self, samples: np.ndarray) -> np.ndarray:
        x = np.asarray(samples, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.channels or not np.isfinite(x).all():
            raise ValueError('Expected finite samples x channels')
        if len(x) == 0:
            return x.astype(np.float32)
        filtered, self.state = sosfilt(self.sos, x, axis=0, zi=self.state)
        projected = filtered @ self.spatial.T
        result = np.empty_like(projected)
        for index, sample in enumerate(projected):
            delta = sample-self.mean
            self.mean += (1-self.alpha)*delta
            self.variance = self.alpha*(self.variance+(1-self.alpha)*delta*delta)
            result[index] = np.clip((sample-self.mean)/np.sqrt(self.variance+1e-8), -12, 12)
        return result.astype(np.float32)


class RidgeAlignment:
    """Regularized paired latent alignment; calibration is explicitly required."""

    def __init__(self, penalty: float = 1.) -> None:
        if not np.isfinite(penalty) or penalty <= 0:
            raise ValueError('Ridge penalty must be positive')
        self.penalty = penalty
        self.weights: np.ndarray | None = None
        self.source_mean: np.ndarray | None = None
        self.target_mean: np.ndarray | None = None

    def fit(self, source: np.ndarray, target: np.ndarray) -> RidgeAlignment:
        x, y = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
        if (x.ndim != 2 or y.ndim != 2 or len(x) != len(y) or len(x) < 2
                or not np.isfinite(x).all() or not np.isfinite(y).all()):
            raise ValueError('Paired finite calibration observations required')
        self.source_mean, self.target_mean = x.mean(0), y.mean(0)
        x, y = x-self.source_mean, y-self.target_mean
        self.weights = np.linalg.solve(x.T@x+self.penalty*np.eye(x.shape[1]), x.T@y)
        return self

    def transform(self, observations: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError('Fit alignment before inference')
        x = np.asarray(observations, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.weights.shape[0] or not np.isfinite(x).all():
            raise ValueError('Invalid latent observations')
        return (x-self.source_mean)@self.weights+self.target_mean

# SPDX-License-Identifier: AGPL-3.0-only
"""Trainable reference interfaces; random weights do not decode thoughts."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import deque
from pathlib import Path
import numpy as np
import torch
from torch import Tensor, nn

from nbfm1 import NBFM1
from neural_preprocessing import StreamingPreprocessor
from neural_ingestion import CausalContext
from sensor_crypto import SensorCipher


class MaskedAutoencoder(nn.Module):
    def __init__(self, model: NBFM1, channels: int, width: int) -> None:
        super().__init__()
        self.model, self.channels = model, channels
        self.reconstruct = nn.Linear(width, channels*2)

    def forward(self, eeg: Tensor, meg: Tensor, geometry: Tensor, fnirs: Tensor,
                mask: Tensor) -> Tensor:
        if (eeg.shape != meg.shape or eeg.shape[1] != self.channels
                or eeg.shape[-1] % 16 or mask.dtype != torch.bool
                or mask.shape != (eeg.shape[0], eeg.shape[-1]//16)
                or not bool(mask.any())):
            raise ValueError('Use aligned 16-sample patches and a nonempty boolean mask')
        hidden = mask.repeat_interleave(16, dim=1).unsqueeze(1)
        result = self.model(eeg.masked_fill(hidden, 0), meg.masked_fill(hidden, 0),
                            geometry, fnirs)
        prediction = self.reconstruct(result['latent'])
        target = torch.cat((eeg, meg), dim=1).reshape(eeg.shape[0], self.channels*2,
                                                    -1, 16).mean(-1).transpose(1, 2)
        return ((prediction-target.detach()).square().mean(-1))[mask].mean()


class ReferenceDecoder:
    def __init__(self, model: NBFM1) -> None:
        self.model = model.eval()

    @torch.inference_mode()
    def infer(self, eeg: np.ndarray, meg: np.ndarray, geometry: np.ndarray,
              fnirs: np.ndarray) -> dict[str, np.ndarray]:
        inputs = [np.asarray(x, dtype=np.float32) for x in (eeg, meg, geometry, fnirs)]
        if not all(np.isfinite(x).all() for x in inputs):
            raise ValueError('Nonfinite neural tensor')
        output = self.model(*(torch.from_numpy(x) for x in inputs))
        return {key: value.cpu().numpy() for key, value in output.items()}


class MultimodalPipeline:
    """Aligned fast streams plus timestamp-selected native-rate slow context.

    Clock mapping and EEG/MEG resampling belong to acquisition: this interface
    rejects missing data instead of fabricating modalities or upsampling EEG.
    """

    def __init__(self, decoder: ReferenceDecoder, geometry: np.ndarray,
                 sample_rate: float = 250., window: int = 64,
                 slow_samples: int = 4, maximum_context_age: float = .5) -> None:
        self.geometry = np.asarray(geometry,dtype=np.float32)
        if (self.geometry.shape != (1,128,6) or not np.isfinite(self.geometry).all()
                or window < 16 or window % 16 or slow_samples < 1
                or maximum_context_age <= 0):
            raise ValueError('Invalid measured geometry or temporal configuration')
        self.decoder, self.window = decoder, window
        self.eeg_filter = StreamingPreprocessor(128,sample_rate)
        self.meg_filter = StreamingPreprocessor(128,sample_rate)
        self.eeg: deque[np.ndarray] = deque(maxlen=window)
        self.meg: deque[np.ndarray] = deque(maxlen=window)
        self.context = CausalContext(320)
        self.slow_samples, self.maximum_age = slow_samples, maximum_context_age
        self.last_timestamp = -np.inf

    def process(self, eeg: np.ndarray, meg: np.ndarray, timestamps: np.ndarray) -> dict[str,np.ndarray] | None:
        e,m,t = np.asarray(eeg),np.asarray(meg),np.asarray(timestamps,dtype=float)
        if (e.ndim != 2 or e.shape[1] != 128 or e.shape != m.shape
                or t.shape != (len(e),) or not np.isfinite(t).all()
                or not np.isfinite(e).all() or not np.isfinite(m).all()
                or np.any(np.diff(t)<=0) or len(t) and t[0]<=self.last_timestamp):
            raise ValueError('Aligned finite fast samples and strictly ordered shared-clock timestamps required')
        if not len(t):
            return None
        self.eeg.extend(self.eeg_filter.process(e))
        self.meg.extend(self.meg_filter.process(m))
        self.last_timestamp = float(t[-1])
        if len(self.eeg)<self.window:
            return None
        slow = self.context.at(self.last_timestamp,self.slow_samples,self.maximum_age)
        return self.decoder.infer(np.stack(self.eeg).T[None],np.stack(self.meg).T[None],
                                  self.geometry,slow[None])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--iterations', type=int, default=30)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error('iterations must be positive')
    torch.set_num_threads(1)
    torch.manual_seed(7)
    rng = np.random.default_rng(7)
    model = NBFM1(d_model=32, num_heads=4, num_layers=1)
    if args.checkpoint:
        model.load_state_dict(torch.load(args.checkpoint, map_location='cpu', weights_only=True))
    decoder = ReferenceDecoder(model)
    preprocessing = StreamingPreprocessor(128, 250.)
    eeg = preprocessing.process(rng.normal(size=(64, 128))).T[None]
    meg, geometry, fnirs = (rng.normal(size=shape).astype(np.float32)
                            for shape in [(1,128,64), (1,128,6), (1,320,4)])
    # Local encryption roundtrip, never transmit or print a neural payload or key.
    master = os.urandom(32)
    sender = SensorCipher(master)
    receiver = SensorCipher(master, sender.session_id)
    decoder.infer(eeg, meg, geometry, fnirs)
    durations = []
    for _ in range(args.iterations):
        start = time.perf_counter_ns()
        result = decoder.infer(eeg, meg, geometry, fnirs)
        packet = sender.encrypt(result['latent'].tobytes())
        receiver.decrypt(packet)
        durations.append((time.perf_counter_ns()-start)/1e6)
    print(json.dumps({'mode':'synthetic-interface-test', 'trained_checkpoint_loaded':bool(args.checkpoint),
                      'samples':len(durations), 'local_compute_p99_ms':float(np.percentile(durations,99)),
                      'measurement_scope':'prebuilt tensors -> inference -> AES-GCM roundtrip',
                      'validates_external_multimodal_measurement':False}))


if __name__ == '__main__':
    main()

# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
import math
import time

import numpy as np

from ring_protocol import RawRingWriter, build_packet


class SyntheticBCI:
    def __init__(self, seed: int = 7) -> None:
        self.rng = np.random.default_rng(seed)
        self.phase_alpha = self.rng.uniform(0, 2 * math.pi, 128)
        self.phase_beta = self.rng.uniform(0, 2 * math.pi, 128)
        self.phase_meg = self.rng.uniform(0, 2 * math.pi, 128)
        self.fnirs_response = 0.0

    @staticmethod
    def intent_active(t: float) -> bool:
        return 2.0 <= (t % 8.0) < 3.5

    def eeg(self, t: float, intent: bool) -> np.ndarray:
        alpha_amp = np.full(128, 18.0)
        beta_amp = np.full(128, 7.0)
        motor = np.arange(36, 52)
        if intent:
            alpha_amp[motor] *= 0.35
            beta_amp[motor] *= 0.50
        signal = (
            alpha_amp * np.sin(2 * math.pi * 10 * t + self.phase_alpha)
            + beta_amp * np.sin(2 * math.pi * 20 * t + self.phase_beta)
            + 1.5 * math.sin(2 * math.pi * 50 * t)
            + self.rng.normal(0, 4.0, 128)
        )
        if intent:
            signal[motor] -= 12.0
        blink_phase = t % 5.0
        if 0.80 <= blink_phase < 0.98:
            signal[:16] += 120.0 * math.sin(math.pi * (blink_phase - 0.80) / 0.18)
        emg_phase = t % 7.0
        if 4.00 <= emg_phase < 4.25:
            signal[72:96] += self.rng.normal(0, 35.0, 24)
        return np.rint(signal * 1000.0).astype(np.int32)

    def meg(self, t: float, intent: bool) -> np.ndarray:
        amp = 55.0 if intent else 40.0
        signal = amp * np.sin(2 * math.pi * 18 * t + self.phase_meg)
        return np.rint(signal + self.rng.normal(0, 12.0, 128)).astype(np.int32)

    def fnirs(self, t: float, intent: bool) -> tuple[np.ndarray, np.ndarray]:
        target = 1.0 if intent else 0.0
        tau = 2.5 if target > self.fnirs_response else 5.0
        self.fnirs_response += (target - self.fnirs_response) * ((1 / 20) / tau)
        systemic = 0.015 * math.sin(2 * math.pi * 0.10 * t) + 0.008 * math.sin(2 * math.pi * 1.10 * t)
        long = np.empty((128, 2), dtype=np.uint32)
        short = np.empty((32, 2), dtype=np.uint32)
        for ch in range(128):
            cortical = 1.0 if 32 <= ch < 64 else 0.25
            m = systemic + 0.025 * cortical * self.fnirs_response
            n = self.rng.normal(0, 500, 2)
            long[ch, 0] = np.uint32(max(1, 1_000_000 * (1 - m) + n[0]))
            long[ch, 1] = np.uint32(max(1, 1_000_000 * (1 + 0.6 * m) + n[1]))
        for ch in range(32):
            n = self.rng.normal(0, 500, 2)
            short[ch, 0] = np.uint32(max(1, 850_000 * (1 - systemic) + n[0]))
            short[ch, 1] = np.uint32(max(1, 850_000 * (1 + systemic) + n[1]))
        return long, short


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ring", default="/dev/shm/bci/raw-ring")
    p.add_argument("--slot-count", type=int, default=4096)
    p.add_argument("--seconds", type=float, default=0.0)
    p.add_argument("--fs", type=int, default=1000)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-realtime", action="store_true")
    p.add_argument("--overwrite-oldest", action="store_true")
    p.add_argument("--timestamp-now", action="store_true")
    args = p.parse_args()
    if args.fs <= 0 or args.fs % 20:
        raise SystemExit("--fs must be a positive multiple of 20")

    writer = RawRingWriter(args.ring, args.slot_count, args.overwrite_oldest)
    source = SyntheticBCI(args.seed)
    fnirs_interval = args.fs // 20
    period_ns = 1_000_000_000 // args.fs
    start_wall = time.time_ns()
    start_mono = time.perf_counter_ns()
    sequence = 0
    fnirs_index = 0
    try:
        while True:
            t = sequence / args.fs
            if args.seconds > 0 and t >= args.seconds:
                break
            intent = source.intent_active(t)
            long_frame = short_frame = None
            if sequence % fnirs_interval == 0:
                long_frame, short_frame = source.fnirs(t, intent)
                current_fnirs = fnirs_index
                fnirs_index += 1
            else:
                current_fnirs = 0
            slot = build_packet(
                sequence=sequence,
                timestamp_ns=(time.time_ns() if args.timestamp_now else start_wall + sequence * period_ns),
                eeg=source.eeg(t, intent),
                meg=source.meg(t, intent),
                fnirs_long=long_frame,
                fnirs_short=short_frame,
                fnirs_sample_index=current_fnirs,
            )
            writer.push(slot)
            sequence += 1
            if not args.no_realtime:
                target = start_mono + sequence * period_ns
                while True:
                    remain = target - time.perf_counter_ns()
                    if remain <= 0:
                        break
                    if remain > 300_000:
                        time.sleep((remain - 150_000) / 1e9)
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()


if __name__ == "__main__":
    main()

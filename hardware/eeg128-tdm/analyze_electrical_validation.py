#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np


def load_numeric_csv(path: Path) -> tuple[list[str], np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [[float(value) for value in row] for row in reader if row]
    data = np.asarray(rows, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] != len(header):
        raise ValueError(f"malformed CSV: {path}")
    return header, data


def band_limited_rms_uv(
    samples_uv: np.ndarray,
    sample_rate_hz: float,
    low_hz: float = 0.5,
    high_hz: float = 100.0,
) -> float:
    if samples_uv.ndim != 1 or samples_uv.size < 16:
        raise ValueError("noise trace must contain at least 16 samples")
    centered = samples_uv - np.mean(samples_uv)
    spectrum = np.fft.rfft(centered)
    frequencies = np.fft.rfftfreq(centered.size, d=1.0 / sample_rate_hz)
    keep = (frequencies >= low_hz) & (frequencies <= high_hz)
    filtered_spectrum = np.where(keep, spectrum, 0.0)
    filtered = np.fft.irfft(filtered_spectrum, n=centered.size)
    return float(np.sqrt(np.mean(np.square(filtered))))


def percentile(values: Iterable[float], q: float) -> float:
    array = np.asarray(list(values), dtype=np.float64)
    if not array.size:
        return math.nan
    return float(np.percentile(array, q))


def analyze_noise(args: argparse.Namespace) -> dict[str, object]:
    header, data = load_numeric_csv(Path(args.csv))
    if args.time_column not in header:
        raise ValueError(f"time column {args.time_column!r} not found")
    channel_indices = [
        index
        for index, name in enumerate(header)
        if index != header.index(args.time_column) and name.startswith(args.prefix)
    ]
    if not channel_indices:
        raise ValueError(f"no channel columns beginning with {args.prefix!r}")

    per_channel: dict[str, float] = {}
    for index in channel_indices:
        per_channel[header[index]] = band_limited_rms_uv(
            data[:, index],
            args.sample_rate_hz,
            args.low_hz,
            args.high_hz,
        )

    values = list(per_channel.values())
    return {
        "kind": "input_referred_noise",
        "units": "uV_RMS",
        "band_hz": [args.low_hz, args.high_hz],
        "sample_rate_hz": args.sample_rate_hz,
        "samples_per_channel": int(data.shape[0]),
        "channels": len(per_channel),
        "median_uv_rms": percentile(values, 50),
        "p95_uv_rms": percentile(values, 95),
        "worst_uv_rms": max(values),
        "target_uv_rms": args.target_uv_rms,
        "pass": all(value < args.target_uv_rms for value in values),
        "per_channel_uv_rms": per_channel,
    }


def analyze_settling(args: argparse.Namespace) -> dict[str, object]:
    header, data = load_numeric_csv(Path(args.csv))
    required = {"conversion_index", "value_uv", "target_uv"}
    missing = required - set(header)
    if missing:
        raise ValueError(f"settling CSV missing columns: {sorted(missing)}")
    index_col = header.index("conversion_index")
    value_col = header.index("value_uv")
    target_col = header.index("target_uv")

    retained = data[data[:, index_col] > args.discard]
    if retained.size == 0:
        raise ValueError("no retained conversions")
    errors = np.abs(retained[:, value_col] - retained[:, target_col])
    return {
        "kind": "tdm_settling",
        "discard_conversions": args.discard,
        "retained_samples": int(errors.size),
        "tolerance_uv": args.tolerance_uv,
        "max_abs_error_uv": float(np.max(errors)),
        "p99_abs_error_uv": float(np.percentile(errors, 99)),
        "pass": bool(np.all(errors <= args.tolerance_uv)),
    }


def sine_amplitude(samples: np.ndarray, sample_rate_hz: float, frequency_hz: float) -> float:
    if samples.ndim != 1:
        raise ValueError("amplitude input must be one-dimensional")
    n = np.arange(samples.size, dtype=np.float64)
    phase = 2.0 * np.pi * frequency_hz * n / sample_rate_hz
    cos_part = 2.0 * np.dot(samples, np.cos(phase)) / samples.size
    sin_part = 2.0 * np.dot(samples, np.sin(phase)) / samples.size
    return float(math.hypot(cos_part, sin_part))


def analyze_crosstalk(args: argparse.Namespace) -> dict[str, object]:
    header, data = load_numeric_csv(Path(args.csv))
    if args.driven not in header:
        raise ValueError(f"driven channel {args.driven!r} not found")
    driven = sine_amplitude(
        data[:, header.index(args.driven)],
        args.sample_rate_hz,
        args.frequency_hz,
    )
    if driven <= 0.0:
        raise ValueError("driven-channel amplitude is zero")

    coupling_db: dict[str, float] = {}
    for index, name in enumerate(header):
        if name == args.time_column or name == args.driven:
            continue
        amplitude = sine_amplitude(data[:, index], args.sample_rate_hz, args.frequency_hz)
        ratio = max(amplitude / driven, np.finfo(float).tiny)
        coupling_db[name] = 20.0 * math.log10(ratio)

    worst_channel = max(coupling_db, key=coupling_db.get)
    worst_db = coupling_db[worst_channel]
    return {
        "kind": "crosstalk",
        "frequency_hz": args.frequency_hz,
        "driven_channel": args.driven,
        "driven_amplitude_uv": driven,
        "worst_other_channel": worst_channel,
        "worst_coupling_db": worst_db,
        "limit_db": args.limit_db,
        "pass": worst_db <= args.limit_db,
        "per_channel_coupling_db": coupling_db,
    }


def analyze_cmrr(args: argparse.Namespace) -> dict[str, object]:
    if args.common_mode_v_rms <= 0.0 or args.equivalent_diff_uv_rms <= 0.0:
        raise ValueError("CMRR inputs must be positive")
    differential_v = args.equivalent_diff_uv_rms * 1e-6
    cmrr_db = 20.0 * math.log10(args.common_mode_v_rms / differential_v)
    return {
        "kind": "cmrr",
        "common_mode_v_rms": args.common_mode_v_rms,
        "equivalent_differential_uv_rms": args.equivalent_diff_uv_rms,
        "cmrr_db": cmrr_db,
        "target_db": args.target_db,
        "pass": cmrr_db >= args.target_db,
    }


def write_result(result: dict[str, object], output: str | None) -> None:
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    print(text, end="")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze physical EEG128-TDM bench measurements."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    noise = subparsers.add_parser("noise")
    noise.add_argument("--csv", required=True)
    noise.add_argument("--sample-rate-hz", type=float, required=True)
    noise.add_argument("--time-column", default="time_s")
    noise.add_argument("--prefix", default="ch")
    noise.add_argument("--low-hz", type=float, default=0.5)
    noise.add_argument("--high-hz", type=float, default=100.0)
    noise.add_argument("--target-uv-rms", type=float, default=1.5)
    noise.add_argument("--output")
    noise.set_defaults(handler=analyze_noise)

    settling = subparsers.add_parser("settling")
    settling.add_argument("--csv", required=True)
    settling.add_argument("--discard", type=int, default=4)
    settling.add_argument("--tolerance-uv", type=float, required=True)
    settling.add_argument("--output")
    settling.set_defaults(handler=analyze_settling)

    crosstalk = subparsers.add_parser("crosstalk")
    crosstalk.add_argument("--csv", required=True)
    crosstalk.add_argument("--sample-rate-hz", type=float, required=True)
    crosstalk.add_argument("--frequency-hz", type=float, required=True)
    crosstalk.add_argument("--driven", required=True)
    crosstalk.add_argument("--time-column", default="time_s")
    crosstalk.add_argument("--limit-db", type=float, default=-60.0)
    crosstalk.add_argument("--output")
    crosstalk.set_defaults(handler=analyze_crosstalk)

    cmrr = subparsers.add_parser("cmrr")
    cmrr.add_argument("--common-mode-v-rms", type=float, required=True)
    cmrr.add_argument("--equivalent-diff-uv-rms", type=float, required=True)
    cmrr.add_argument("--target-db", type=float, default=100.0)
    cmrr.add_argument("--output")
    cmrr.set_defaults(handler=analyze_cmrr)

    args = parser.parse_args()
    result = args.handler(args)
    write_result(result, args.output)
    return 0 if bool(result["pass"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

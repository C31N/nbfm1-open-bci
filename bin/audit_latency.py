# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Optional

import numpy as np

from telemetry_ipc import TelemetryReader


@dataclass
class LatencyStats:
    samples: int
    p50_ms: float
    p99_ms: float
    p999_ms: float
    mean_ms: float
    max_ms: float
    sub_5ms_fraction: float


@dataclass
class JitterStats:
    median_wall_minus_hardware_ms: float
    p99_abs_jitter_ms: float
    p999_abs_jitter_ms: float
    max_abs_jitter_ms: float


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if values.size else math.nan


def latency_stats(values: list[float]) -> LatencyStats:
    a = np.asarray(values, dtype=np.float64)
    if not a.size:
        return LatencyStats(0, math.nan, math.nan, math.nan, math.nan, math.nan, math.nan)
    return LatencyStats(
        int(a.size),
        percentile(a, 50),
        percentile(a, 99),
        percentile(a, 99.9),
        float(a.mean()),
        float(a.max()),
        float(np.mean(a < 5.0)),
    )


def jitter_stats(values: list[float]) -> JitterStats:
    a = np.asarray(values, dtype=np.float64)
    if not a.size:
        return JitterStats(math.nan, math.nan, math.nan, math.nan)
    median = float(np.median(a))
    jitter = np.abs(a - median)
    return JitterStats(median, percentile(jitter, 99), percentile(jitter, 99.9), float(jitter.max()))


class ProcessGroup:
    def __init__(self) -> None:
        self.procs: list[subprocess.Popen] = []

    def start(self, argv: list[str], env: Optional[dict] = None) -> subprocess.Popen:
        p = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        self.procs.append(p)
        return p

    def stop(self) -> None:
        for p in reversed(self.procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for p in reversed(self.procs):
            if p.poll() is None:
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


def wait_for(path: Path, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise TimeoutError(f"timeout waiting for {path}")


def collect_telemetry(
    path: Path,
    duration: float,
    warmup: float = 0.0,
) -> tuple[list[float], int, int, float]:
    wait_for(path)
    reader = TelemetryReader(str(path))
    start = time.monotonic()
    end = start + duration
    latencies = []
    first_seq = last_seq = seen_seq = None
    sample_start = sample_end = None
    try:
        while time.monotonic() < end:
            item = reader.read()
            now = time.monotonic()
            if now - start < warmup:
                time.sleep(0.0005)
                continue
            if item.frame_sequence != seen_seq:
                seen_seq = item.frame_sequence
                if first_seq is None:
                    first_seq = item.frame_sequence
                    sample_start = now
                last_seq = item.frame_sequence
                sample_end = now
                latencies.append(float(item.latency_ms))
            time.sleep(0.0005)
    finally:
        reader.close()
    elapsed = max(1e-9, (sample_end or end) - (sample_start or start))
    return latencies, int(first_seq or 0), int(last_seq or 0), elapsed


def run_phase(root: Path, seconds: float, saturation: bool, hop_samples: int) -> dict:
    py = sys.executable
    pg = ProcessGroup()
    with tempfile.TemporaryDirectory(prefix="bci-audit-") as td:
        base = Path(td)
        run = base / "run"
        shm = base / "shm"
        run.mkdir()
        shm.mkdir()
        key = run / "master.key"
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        arm = run / "arm"
        arm.write_text("LOCKED\n", encoding="utf-8")
        arm.chmod(0o600)
        ring = shm / "raw-ring"
        telemetry = shm / "telemetry"
        sock = run / "secure.sock"

        bridge = pg.start([
            py, str(root / "bin/bci_bridge_runtime.py"),
            "--socket", str(sock),
            "--key-file", str(key),
            "--arm-file", str(arm),
            "--telemetry", str(telemetry),
            "--router", str(root / "config/action_router.json"),
            "--vocabulary", str(root / "config/phonemes.json"),
            "--no-cursor",
            "--no-ollama",
        ])
        wait_for(sock)

        inference = pg.start([
            py, str(root / "bin/bci_inference_daemon.py"),
            "--source", "ring",
            "--ring", str(ring),
            "--engine", str(root / "models/nbfm1_fp16.engine"),
            "--onnx", str(root / "models/nbfm1.onnx"),
            "--cache", str(root / "engine-cache"),
            "--socket", str(sock),
            "--key-file", str(key),
            "--hop-samples", str(hop_samples),
        ])

        sim_args = [
            py, str(root / "bin/bci_signal_simulator.py"),
            "--ring", str(ring),
            "--slot-count", "8192",
            "--seconds", str(max(seconds + 3.0, 10.0) if not saturation else 1000000.0),
        ]
        if saturation:
            sim_args += ["--no-realtime", "--timestamp-now"]
        pg.start(sim_args)

        try:
            wait_for(telemetry, 60.0)
            latencies, first_seq, last_seq, elapsed = collect_telemetry(
                telemetry, duration=seconds, warmup=min(2.0, seconds * 0.2)
            )
            if bridge.poll() is not None:
                raise RuntimeError("bridge exited during audit")
            if inference.poll() is not None:
                raise RuntimeError("inference exited during audit")
        finally:
            pg.stop()

        frames = max(0, last_seq - first_seq)
        return {
            "latencies_ms": latencies,
            "frames": frames,
            "elapsed_s": elapsed,
            "fps": frames / elapsed if elapsed > 0 else 0.0,
        }


def html_report(report: dict) -> str:
    latency = report["latency"]
    jitter = report["jitter"]
    throughput = report["throughput"]
    verdict = "PASS" if report["sub_5ms_p99_pass"] else "FAIL"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>BCI Latency Audit</title></head>
<body><h1>BCI End-to-End Latency Audit</h1>
<h2>{verdict}: P99 &lt; 5 ms</h2>
<table border='1' cellpadding='6'>
<tr><td>Samples</td><td>{latency['samples']}</td></tr>
<tr><td>P50</td><td>{latency['p50_ms']:.4f} ms</td></tr>
<tr><td>P99</td><td>{latency['p99_ms']:.4f} ms</td></tr>
<tr><td>P99.9</td><td>{latency['p999_ms']:.4f} ms</td></tr>
<tr><td>P99 abs jitter</td><td>{jitter['p99_abs_jitter_ms']:.4f} ms</td></tr>
<tr><td>Throughput</td><td>{throughput['fps']:.2f} frames/s</td></tr>
</table></body></html>"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="/opt/bci-stack")
    p.add_argument("--latency-seconds", type=float, default=12.0)
    p.add_argument("--throughput-seconds", type=float, default=10.0)
    p.add_argument("--hop-samples", type=int, default=16)
    p.add_argument("--json", default="/opt/bci-stack/reports/latency-audit.json")
    p.add_argument("--html", default="/opt/bci-stack/reports/latency-audit.html")
    args = p.parse_args()

    root = Path(args.root)
    if not (root / "models/nbfm1.onnx").exists():
        raise SystemExit("NBFM ONNX model missing; run deploy_bci_stack.sh first")

    latency_phase = run_phase(root, args.latency_seconds, False, args.hop_samples)
    load_phase = run_phase(root, args.throughput_seconds, True, args.hop_samples)
    latency = latency_stats(latency_phase["latencies_ms"])
    jitter = jitter_stats(latency_phase["latencies_ms"])
    report = {
        "generated_at_ns": time.time_ns(),
        "path": "DMA ring -> preprocess -> TensorRT/ORT -> privacy gate/AES-GCM -> Unix socket",
        "latency": asdict(latency),
        "jitter": asdict(jitter),
        "throughput": {
            "frames": int(load_phase["frames"]),
            "elapsed_s": float(load_phase["elapsed_s"]),
            "fps": float(load_phase["fps"]),
            "hop_samples": int(args.hop_samples),
        },
        "sub_5ms_p99_pass": bool(latency.samples > 0 and latency.p99_ms < 5.0),
    }
    json_path = Path(args.json)
    html_path = Path(args.html)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    html_path.write_text(html_report(report), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

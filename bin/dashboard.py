# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
import time
from typing import Any

from telemetry_ipc import Telemetry, TelemetryReader


def as_dict(item: Telemetry) -> dict[str, Any]:
    return {
        "timestamp_ns": int(item.timestamp_ns),
        "latency_ms": float(item.latency_ms),
        "p99_ms": float(item.p99_ms),
        "intent_probability": float(item.intent_probability),
        "state": item.state,
        "motor": {
            "vx": float(item.motor[0]),
            "vy": float(item.motor[1]),
            "vz": float(item.motor[2]),
            "grip": float(item.motor[3]),
        },
        "motor_std": {
            "vx": float(item.motor_std[0]),
            "vy": float(item.motor_std[1]),
            "vz": float(item.motor_std[2]),
            "grip": float(item.motor_std[3]),
        },
        "frame_sequence": int(item.frame_sequence),
        "trigger_count": int(item.trigger_count),
    }


def terminal(path: str) -> None:
    from rich.live import Live
    from rich.table import Table

    reader = TelemetryReader(path)

    def render() -> Table:
        item = reader.read()
        table = Table(title="NBFM-1 BCI Live Telemetry")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("State", item.state)
        table.add_row("P(intent)", f"{item.intent_probability:.3f}")
        table.add_row("Latency", f"{item.latency_ms:.3f} ms")
        table.add_row("P99", f"{item.p99_ms:.3f} ms")
        table.add_row("Motor", f"{item.motor.tolist()}")
        return table

    with Live(render(), refresh_per_second=10) as live:
        try:
            while True:
                live.update(render())
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            reader.close()


def web(path: str, host: str, port: int) -> None:
    from fastapi import FastAPI
    import uvicorn

    reader = TelemetryReader(path)
    app = FastAPI(title="BCI Telemetry", docs_url=None, redoc_url=None)

    @app.get("/api/telemetry")
    def telemetry() -> dict[str, Any]:
        return as_dict(reader.read())

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "NBFM-1 BCI telemetry", "endpoint": "/api/telemetry"}

    uvicorn.run(app, host=host, port=port, access_log=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", default="/dev/shm/bci/telemetry")
    parser.add_argument("--mode", choices=["terminal", "web"], default="terminal")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    if args.mode == "web":
        web(args.telemetry, args.host, args.port)
    else:
        terminal(args.telemetry)


if __name__ == "__main__":
    main()

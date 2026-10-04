# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from typing import Optional

import numpy as np

from action_router import ActionRouter
from ring_protocol import crc32c
from secure_stream import SecureFrameDecoder
from telemetry_ipc import Telemetry, TelemetryWriter

ROBOT_BASE = struct.Struct("<4sI4h")


def load_key(path: str) -> bytes:
    p = Path(path)
    if p.stat().st_mode & 0o077:
        raise PermissionError("master key permissions must be 0600")
    raw = p.read_bytes()
    if len(raw) != 32:
        raise ValueError("master key must be exactly 32 bytes")
    return raw


class ArmLatch:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def armed(self) -> bool:
        try:
            if self.path.stat().st_mode & 0o077:
                return False
            return self.path.read_text(encoding="utf-8").strip() == "ARMED"
        except OSError:
            return False

    def lock(self) -> None:
        self.path.write_text("LOCKED\n", encoding="utf-8")
        os.chmod(self.path, 0o600)


class LengthPrefixedUnixServer:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.server.listen(1)

    @staticmethod
    def recv_exact(conn: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                raise EOFError
            data.extend(chunk)
        return bytes(data)

    def frames(self):
        while True:
            conn, _ = self.server.accept()
            with conn:
                while True:
                    try:
                        raw_len = self.recv_exact(conn, 4)
                        frame_len = struct.unpack("<I", raw_len)[0]
                        if not 32 <= frame_len <= 16 * 1024 * 1024:
                            raise ValueError("invalid secure frame length")
                        yield self.recv_exact(conn, frame_len)
                    except EOFError:
                        break


class IntentTrigger:
    def __init__(self, high: float, low: float, consecutive: int, cooldown_ms: int) -> None:
        self.high = high
        self.low = low
        self.consecutive = consecutive
        self.cooldown = cooldown_ms / 1000.0
        self.count = 0
        self.latched = False
        self.last = -1e30

    def update(self, p: float, now: float) -> bool:
        self.count = self.count + 1 if p >= self.high else 0
        if p <= self.low:
            self.latched = False
        if not self.latched and self.count >= self.consecutive and now - self.last >= self.cooldown:
            self.latched = True
            self.last = now
            self.count = 0
            return True
        return False


class MotorFilter:
    def __init__(self) -> None:
        self.state = np.zeros(4, dtype=np.float32)

    def update(self, mean: np.ndarray, log_std: np.ndarray, p: float, armed: bool) -> np.ndarray:
        std = np.exp(np.clip(log_std.astype(np.float64), -6, 2))
        safe = armed and p >= 0.80 and np.all(np.isfinite(mean)) and np.all(std <= 0.75)
        target = np.clip(mean, -1, 1).astype(np.float32) if safe else np.zeros(4, np.float32)
        target[np.abs(target) < 0.08] = 0
        self.state = 0.75 * self.state + 0.25 * target
        if not safe:
            self.state *= 0.5
            if np.max(np.abs(self.state)) < 0.01:
                self.state[:] = 0
        return self.state.copy()


class CursorSink:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = False
        self.mouse = None
        self.Button = None
        self.last_grip = False
        if not enabled:
            return
        try:
            from pynput.mouse import Button, Controller
            self.Button = Button
            self.mouse = Controller()
            self.enabled = True
        except Exception as exc:
            print(f"cursor output disabled: {exc}", flush=True)

    def apply(self, vector: np.ndarray, dt: float, p: float) -> None:
        if not self.enabled:
            return
        dt = min(max(dt, 0.0), 0.05)
        dx = int(round(float(vector[0]) * 900.0 * dt))
        dy = int(round(float(vector[1]) * 900.0 * dt))
        if dx or dy:
            self.mouse.move(dx, dy)
        grip = bool(vector[3] >= 0.70 and p >= 0.98)
        if grip and not self.last_grip:
            self.mouse.click(self.Button.left, 1)
        self.last_grip = grip

    def click(self, right: bool = False) -> None:
        if self.enabled:
            self.mouse.click(self.Button.right if right else self.Button.left, 1)

    def center(self) -> None:
        if not self.enabled:
            return
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            w, h = root.winfo_screenwidth(), root.winfo_screenheight()
            root.destroy()
            self.mouse.position = (w // 2, h // 2)
        except Exception:
            pass


class RobotSink:
    def __init__(self, port: str = "") -> None:
        self.serial = None
        self.sequence = 0
        selected = port or ("/dev/bci-robot" if os.path.exists("/dev/bci-robot") else "")
        if selected:
            try:
                import serial
                self.serial = serial.Serial(selected, 921600, timeout=0, write_timeout=0.02)
            except Exception as exc:
                print(f"robot serial disabled: {exc}", flush=True)

    def apply(self, vector: np.ndarray, armed: bool) -> None:
        if self.serial is None:
            return
        safe = np.clip(vector, -1, 1) if armed else np.zeros(4, np.float32)
        q = np.rint(safe * 1000).astype(np.int16)
        base = ROBOT_BASE.pack(b"RBOT", self.sequence & 0xFFFFFFFF, *[int(x) for x in q])
        self.serial.write(base + struct.pack("<I", crc32c(base)))
        self.sequence += 1

    def stop(self) -> None:
        self.apply(np.zeros(4, np.float32), False)


class CTCDecoder:
    def __init__(self, vocab_path: str) -> None:
        self.tokens = [str(x) for x in json.loads(Path(vocab_path).read_text(encoding="utf-8"))]

    def decode(self, logits: np.ndarray) -> str:
        if logits.ndim != 2 or logits.size == 0:
            return ""
        ids = np.argmax(logits, axis=-1).tolist()
        out = []
        previous = None
        for i in ids:
            if i != previous and i != 0:
                out.append(self.tokens[i] if 0 <= i < len(self.tokens) else "<?>")
            previous = i
        return " ".join(out)


class ActionExecutor:
    def __init__(self, router: ActionRouter, cursor: CursorSink, robot: RobotSink, arm: ArmLatch) -> None:
        self.router = router
        self.cursor = cursor
        self.robot = robot
        self.arm = arm

    def execute(self, action_id: str) -> Optional[np.ndarray]:
        spec = self.router.spec(action_id)
        handler = spec["handler"]
        if handler == "noop":
            return None
        if handler == "mouse_click_left":
            self.cursor.click(False)
        elif handler == "mouse_click_right":
            self.cursor.click(True)
        elif handler == "mouse_center":
            self.cursor.center()
        elif handler == "vector_pulse":
            return np.asarray(spec["vector"], dtype=np.float32)
        elif handler == "robot_stop":
            self.robot.stop()
        elif handler == "open_dashboard":
            if os.path.exists("/usr/bin/xdg-open") and os.environ.get("DISPLAY"):
                subprocess.Popen(
                    ["/usr/bin/xdg-open", "http://127.0.0.1:8088"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
        elif handler == "lock_interface":
            self.arm.lock()
            self.robot.stop()
        else:
            raise ValueError(f"unsupported fixed handler {handler}")
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--socket", default="/run/bci/secure.sock")
    p.add_argument("--key-file", default="/run/bci/master.key")
    p.add_argument("--arm-file", default="/run/bci/arm")
    p.add_argument("--telemetry", default="/dev/shm/bci/telemetry")
    p.add_argument("--router", default="/opt/bci-stack/config/action_router.json")
    p.add_argument("--vocabulary", default="/opt/bci-stack/config/phonemes.json")
    p.add_argument("--robot-serial", default="")
    p.add_argument("--no-cursor", action="store_true")
    p.add_argument("--no-ollama", action="store_true")
    args = p.parse_args()

    router = ActionRouter(args.router)
    gate_cfg = router.config["intent_gate"]
    decoder = SecureFrameDecoder(load_key(args.key_file))
    server = LengthPrefixedUnixServer(args.socket)
    arm = ArmLatch(args.arm_file)
    trigger = IntentTrigger(
        float(gate_cfg["trigger_probability"]),
        float(gate_cfg["release_probability"]),
        int(gate_cfg["consecutive_frames"]),
        int(gate_cfg["cooldown_ms"]),
    )
    filter_ = MotorFilter()
    cursor = CursorSink(not args.no_cursor)
    robot = RobotSink(args.robot_serial)
    ctc = CTCDecoder(args.vocabulary)
    executor = ActionExecutor(router, cursor, robot, arm)
    telemetry = TelemetryWriter(args.telemetry)
    latencies = deque(maxlen=4096)
    p99 = 0.0
    triggers = 0
    frames = 0
    previous = time.monotonic()

    for encrypted in server.frames():
        start = time.perf_counter_ns()
        try:
            frame = decoder.decode(encrypted)
        except Exception as exc:
            print(f"secure frame rejected: {exc}", flush=True)
            continue
        now = time.monotonic()
        dt = min(max(now - previous, 0.0), 0.05)
        previous = now
        armed = arm.armed()
        speech_allowed = (
            armed
            and frame.speech_allowed
            and frame.intent_probability >= float(gate_cfg["trigger_probability"])
        )
        if not speech_allowed:
            frame.speech_logits.fill(0.0)
        vector = filter_.update(frame.motor_mean, frame.motor_log_std, frame.intent_probability, armed)
        cursor.apply(vector, dt, frame.intent_probability)
        robot.apply(vector, armed)

        if armed and speech_allowed and trigger.update(frame.intent_probability, now):
            triggers += 1
            text = ctc.decode(frame.speech_logits)
            action_id = router.resolve(text, allow_llm=not args.no_ollama)
            pulse = executor.execute(action_id)
            if pulse is not None:
                cursor.apply(pulse, float(router.spec(action_id).get("duration_ms", 100)) / 1000.0, 1.0)
                robot.apply(pulse, armed)

        state = "LOCKED" if not armed else ("DECODING" if speech_allowed else "ARMED")
        wall_delta = time.time_ns() - frame.timestamp_ns
        latency_ms = (
            wall_delta / 1e6
            if 0 <= wall_delta <= 5_000_000_000
            else (time.perf_counter_ns() - start) / 1e6
        )
        latencies.append(float(latency_ms))
        frames += 1
        if frames % 20 == 0:
            p99 = float(np.percentile(np.asarray(latencies), 99))
        telemetry.write(
            Telemetry(
                timestamp_ns=time.time_ns(),
                latency_ms=float(latency_ms),
                p99_ms=p99,
                intent_probability=float(frame.intent_probability),
                state=state,
                motor=vector,
                motor_std=np.exp(
                    np.clip(frame.motor_log_std.astype(np.float64), -6, 2)
                ).astype(np.float32),
                frame_sequence=int(frame.sequence),
                trigger_count=triggers,
            )
        )


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import struct
from typing import Optional

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ENVELOPE_MAGIC = b"BCS1"
ENVELOPE_VERSION = 1
FLAG_SPEECH_ALLOWED = 1 << 0
ENVELOPE_STRUCT = struct.Struct("<4sHHQQ16s12sI")
PAYLOAD_HEADER_STRUCT = struct.Struct("<fB3x8fII")

@dataclass(frozen=True)
class DecoderFrame:
    timestamp_ns: int
    intent_probability: float
    motor_mean: np.ndarray
    motor_log_std: np.ndarray
    speech_logits: np.ndarray

@dataclass(frozen=True)
class PrivacyResult:
    intent_probability: float
    speech_allowed: bool
    motor_mean: np.ndarray
    motor_log_std: np.ndarray
    speech_logits: np.ndarray

class IntentGate:
    def __init__(self, threshold: float = 0.95) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be in (0,1)")
        self.threshold = float(threshold)

    def process(self, frame: DecoderFrame) -> PrivacyResult:
        p = float(frame.intent_probability)
        if not math.isfinite(p):
            raise ValueError("intent probability is not finite")
        p = min(1.0, max(0.0, p))
        motor_mean = np.asarray(frame.motor_mean, dtype=np.float32).reshape(4).copy()
        motor_log_std = np.asarray(frame.motor_log_std, dtype=np.float32).reshape(4).copy()
        original = np.asarray(frame.speech_logits, dtype=np.float32)
        if original.ndim != 2:
            raise ValueError("speech_logits must be [time,vocabulary]")
        allowed = p >= self.threshold
        speech = np.ascontiguousarray(original).copy() if allowed else np.zeros_like(original)
        return PrivacyResult(p, allowed, motor_mean, motor_log_std, speech)

class SecureFrameExporter:
    def __init__(self, master_key: bytes, intent_threshold: float = 0.95) -> None:
        if len(master_key) != 32:
            raise ValueError("master_key must be exactly 32 bytes")
        self.session_id = os.urandom(16)
        self.stream_id = int.from_bytes(os.urandom(4), "big")
        session_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=self.session_id,
            info=b"NBFM-1/local-export/v1"
        ).derive(master_key)
        self.aead = AESGCM(session_key)
        self.gate = IntentGate(intent_threshold)
        self.sequence = 0

    def _next_nonce(self) -> bytes:
        if self.sequence >= (1 << 64):
            raise OverflowError("AES-GCM sequence exhausted")
        return struct.pack(">IQ", self.stream_id, self.sequence)

    @staticmethod
    def _serialize_payload(result: PrivacyResult) -> bytes:
        speech = np.ascontiguousarray(result.speech_logits, dtype="<f4")
        mm = np.asarray(result.motor_mean, dtype=np.float32).reshape(4)
        ms = np.asarray(result.motor_log_std, dtype=np.float32).reshape(4)
        header = PAYLOAD_HEADER_STRUCT.pack(
            float(result.intent_probability),
            1 if result.speech_allowed else 0,
            *[float(x) for x in mm],
            *[float(x) for x in ms],
            int(speech.shape[0]),
            int(speech.shape[1]),
        )
        return header + speech.tobytes(order="C")

    def encrypt_frame(self, frame: DecoderFrame) -> bytes:
        result = self.gate.process(frame)
        plaintext = self._serialize_payload(result)
        nonce = self._next_nonce()
        flags = FLAG_SPEECH_ALLOWED if result.speech_allowed else 0
        envelope = ENVELOPE_STRUCT.pack(
            ENVELOPE_MAGIC, ENVELOPE_VERSION, flags, self.sequence,
            int(frame.timestamp_ns), self.session_id, nonce, len(plaintext)
        )
        ciphertext = self.aead.encrypt(nonce, plaintext, envelope)
        self.sequence += 1
        return envelope + ciphertext

@dataclass(frozen=True)
class DecryptedFrame:
    sequence: int
    timestamp_ns: int
    intent_probability: float
    speech_allowed: bool
    motor_mean: np.ndarray
    motor_log_std: np.ndarray
    speech_logits: np.ndarray

class SecureFrameDecoder:
    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("master_key must be exactly 32 bytes")
        self.master_key = master_key
        self.session_id: Optional[bytes] = None
        self.aead: Optional[AESGCM] = None
        self.stream_prefix: Optional[bytes] = None
        self.last_sequence = -1

    def _select_session(self, session_id: bytes, nonce: bytes) -> None:
        if self.session_id == session_id:
            return
        session_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=session_id,
            info=b"NBFM-1/local-export/v1"
        ).derive(self.master_key)
        self.session_id = session_id
        self.aead = AESGCM(session_key)
        self.stream_prefix = nonce[:4]
        self.last_sequence = -1

    def decode(self, packet: bytes) -> DecryptedFrame:
        if len(packet) < ENVELOPE_STRUCT.size + 16:
            raise ValueError("frame too short")
        envelope = packet[:ENVELOPE_STRUCT.size]
        magic, version, flags, sequence, timestamp_ns, session_id, nonce, plaintext_len = ENVELOPE_STRUCT.unpack(envelope)
        if magic != ENVELOPE_MAGIC or version != ENVELOPE_VERSION:
            raise ValueError("invalid secure frame")
        if len(packet) != ENVELOPE_STRUCT.size + plaintext_len + 16:
            raise ValueError("secure frame length mismatch")
        self._select_session(session_id, nonce)
        if nonce[:4] != self.stream_prefix or nonce[4:] != struct.pack(">Q", sequence):
            raise ValueError("nonce/sequence mismatch")
        if sequence <= self.last_sequence:
            raise ValueError("replayed/out-of-order frame")
        assert self.aead is not None
        plain = self.aead.decrypt(nonce, packet[ENVELOPE_STRUCT.size:], envelope)
        fields = PAYLOAD_HEADER_STRUCT.unpack_from(plain, 0)
        p, speech_valid, *rest = fields
        motor_mean = np.array(rest[:4], dtype=np.float32)
        motor_log_std = np.array(rest[4:8], dtype=np.float32)
        t_steps, vocab = int(rest[8]), int(rest[9])
        count = t_steps * vocab
        expected = PAYLOAD_HEADER_STRUCT.size + count * 4
        if len(plain) != expected:
            raise ValueError("speech tensor length mismatch")
        speech = np.frombuffer(plain, dtype="<f4", count=count,
                               offset=PAYLOAD_HEADER_STRUCT.size).reshape(t_steps, vocab).copy()
        allowed = bool(speech_valid) and bool(flags & FLAG_SPEECH_ALLOWED)
        self.last_sequence = sequence
        return DecryptedFrame(sequence, timestamp_ns, float(p), allowed,
                              motor_mean, motor_log_std, speech)

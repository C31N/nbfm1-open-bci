# SPDX-License-Identifier: AGPL-3.0-only
"""AES-256-GCM raw-sensor envelopes for a trusted edge acquisition endpoint."""
from __future__ import annotations

import os
import struct
from threading import Lock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HEADER = struct.Struct('!4s16sQI')
MAXIMUM_PAYLOAD = 8*1024*1024


class SensorCipher:
    """One direction/session. Exchange session ID through an authenticated channel.

    Fresh sender instance creates a fresh subkey. Receivers must not be reset
    within that session: replay state is process-local, not persistent storage.
    """

    def __init__(self, master_key: bytes, session_id: bytes | None = None) -> None:
        if len(master_key) != 32:
            raise ValueError('Exactly 256 key bits required')
        self.is_sender = session_id is None
        self.session_id = os.urandom(16) if self.is_sender else bytes(session_id)
        if len(self.session_id) != 16:
            raise ValueError('Exactly 128 session bits required')
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=self.session_id,
                   info=b'NBFM/raw-sensor/v1').derive(master_key)
        self.aead, self.sequence, self.received = AESGCM(key), 0, -1
        self.lock = Lock()

    def encrypt(self, data: bytes) -> bytes:
        if not self.is_sender:
            raise RuntimeError('Receivers cannot encrypt; start a fresh sender session')
        if len(data) > MAXIMUM_PAYLOAD:
            raise ValueError('Sensor block too large')
        with self.lock:
            if self.sequence >= 2**32:
                raise OverflowError('Rotate the session before counter exhaustion')
            sequence = self.sequence
            self.sequence += 1  # Never reuse a reserved nonce, including after errors.
            nonce = b'\x00'*4+sequence.to_bytes(8, 'big')
            header = HEADER.pack(b'NBS1', self.session_id, sequence, len(data))
            return header+self.aead.encrypt(nonce, data, header)

    def decrypt(self, packet: bytes) -> bytes:
        if self.is_sender:
            raise RuntimeError('Use a distinct receiver for the authenticated session')
        if len(packet) < HEADER.size+16:
            raise ValueError('Truncated sensor envelope')
        magic, session, sequence, length = HEADER.unpack_from(packet)
        if (magic != b'NBS1' or session != self.session_id or sequence >= 2**32
                or length > MAXIMUM_PAYLOAD or len(packet) != HEADER.size+length+16):
            raise ValueError('Invalid sensor envelope')
        with self.lock:
            if sequence <= self.received:
                raise ValueError('Replayed or reordered sensor envelope')
            nonce = b'\x00'*4+sequence.to_bytes(8, 'big')
            plain = self.aead.decrypt(nonce, packet[HEADER.size:], packet[:HEADER.size])
            self.received = sequence
            return plain

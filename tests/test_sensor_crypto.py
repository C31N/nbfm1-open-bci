# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys
import pytest
from cryptography.exceptions import InvalidTag
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from sensor_crypto import SensorCipher
from secure_stream import SecureFrameExporter,SecureFrameDecoder,ENVELOPE_STRUCT
from test_secure_stream import make_frame


def test_raw_authenticated_roundtrip_replay_and_session_binding() -> None:
    key = bytes(range(32));sender = SensorCipher(key);receiver = SensorCipher(key,sender.session_id)
    packet = sender.encrypt(b'neural test bytes')
    corrupted = packet[:-1]+bytes([packet[-1]^1])
    with pytest.raises(InvalidTag):receiver.decrypt(corrupted)
    assert receiver.decrypt(packet) == b'neural test bytes'
    with pytest.raises(ValueError):receiver.decrypt(packet)
    with pytest.raises(RuntimeError):receiver.encrypt(b'forbidden sender reuse')
    other = SensorCipher(key)
    with pytest.raises(ValueError):receiver.decrypt(other.encrypt(b'other session'))


def test_forged_decoder_session_cannot_reset_replay_counter() -> None:
    key = bytes(range(32));sender = SecureFrameExporter(key);receiver = SecureFrameDecoder(key)
    packet = sender.encrypt_frame(make_frame(.2));receiver.decode(packet)
    parts = list(ENVELOPE_STRUCT.unpack_from(packet));parts[5] = b'x'*16
    forged = ENVELOPE_STRUCT.pack(*parts)+packet[ENVELOPE_STRUCT.size:]
    with pytest.raises(ValueError):receiver.decode(forged)
    with pytest.raises(ValueError):receiver.decode(packet)
    assert receiver.decode(sender.encrypt_frame(make_frame(.2))).sequence == 1


def test_decoder_envelope_hides_gate_and_reserves_unique_nonces_concurrently() -> None:
    exporter = SecureFrameExporter(bytes(range(32)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        packets = list(pool.map(lambda p:exporter.encrypt_frame(make_frame(p)),[.1,.99]*20))
    fields = [ENVELOPE_STRUCT.unpack_from(packet) for packet in packets]
    assert {field[2] for field in fields} == {0}
    assert len({field[6] for field in fields}) == 40
    assert len({len(packet) for packet in packets}) == 1

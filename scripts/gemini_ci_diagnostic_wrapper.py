#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded, redacted Gemini retry/degraded envelope for read-only CI triage.

The caller uses the official Google GenAI SDK. Never put the API key in a
request URL, diagnostic JSON, exception detail, or GitHub Actions output.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import re
import time
from typing import Callable

TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
SDK_ERRORS = frozenset({"ServerError", "ClientError", "APIError"})
TRANSPORT_ERRORS = frozenset({
    "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout",
    "PoolTimeout", "TimeoutException", "RemoteProtocolError", "NetworkError",
    "TransportError",
})


class GeminiTransientError(RuntimeError):
    def __init__(self, reason: str, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class GeminiPermanentError(RuntimeError):
    def __init__(self, reason: str, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    outcome: str
    status_code: int | None
    sleep_before_next_s: float
    detail: str


@dataclass(frozen=True)
class DiagnosticEnvelope:
    status: str
    degraded_reason: str | None
    model: str
    attempts_used: int
    max_retries: int
    total_elapsed_s: float
    analysis_text: str | None
    attempts: list[AttemptRecord]


def compute_backoff_with_jitter(
    attempt_idx: int,
    base_delay_s: float = 2.0,
    max_delay_s: float = 25.0,
    jitter_ratio: float = 0.25,
    rng: random.Random | None = None,
) -> float:
    if (attempt_idx < 0 or not all(math.isfinite(v) for v in
            (base_delay_s, max_delay_s, jitter_ratio)) or
            base_delay_s < 0.0 or max_delay_s <= 0.0 or
            not 0.0 <= jitter_ratio <= 1.0):
        raise ValueError("Invalid bounded Gemini retry parameters")
    raw = min(max_delay_s, base_delay_s * (2.0 ** min(attempt_idx, 16)))
    source = rng if rng is not None else random
    return round(min(max_delay_s, max(0.0, raw * (
        1.0 + source.uniform(-jitter_ratio, jitter_ratio)))), 4)


def classify_gemini_exception(
    error: Exception,
) -> GeminiTransientError | GeminiPermanentError:
    """Use typed SDK status first; never copy an exception into JSON.

    Unknown exceptions fail closed as real errors. This prevents accidental
    masking of implementation bugs, auth failures or model/config errors.
    """
    if isinstance(error, GeminiTransientError):
        # Even library-created exception reasons must not be trusted:
        # they might contain SDK payloads, credentials or log excerpts.
        code = error.status_code
        if code in TRANSIENT_HTTP_CODES:
            return GeminiTransientError(f"HTTP_{code}_TRANSIENT", code)
        if code is None:
            return GeminiTransientError("TRANSPORT_UNAVAILABLE")
        return GeminiPermanentError("UNEXPECTED_TRANSIENT_STATUS")
    if isinstance(error, GeminiPermanentError):
        if error.reason == "EMPTY_MODEL_OUTPUT":
            return GeminiPermanentError("EMPTY_MODEL_OUTPUT")
        code = error.status_code
        if isinstance(code, int):
            return GeminiPermanentError(f"HTTP_{code}_PERMANENT", code)
        return GeminiPermanentError("GEMINI_PERMANENT_ERROR")
    if isinstance(error, (TimeoutError, ConnectionError)):
        return GeminiTransientError("TRANSPORT_TIMEOUT_OR_CONNECTION")
    name = type(error).__name__
    if name in TRANSPORT_ERRORS:
        return GeminiTransientError("TRANSPORT_UNAVAILABLE")
    code = getattr(error, "code", None)
    if not isinstance(code, int):
        code = getattr(error, "status_code", None)
    if not isinstance(code, int) and name in SDK_ERRORS:
        message = str(error)
        match = re.search(r"(?<!\d)(429|500|502|503|504|400|401|403|404)(?!\d)", message)
        code = int(match.group(1)) if match else None
        if code is None and ("UNAVAILABLE" in message.upper() or
                             "RESOURCE_EXHAUSTED" in message.upper()):
            code = 503 if "UNAVAILABLE" in message.upper() else 429
    if isinstance(code, int):
        if code in TRANSIENT_HTTP_CODES:
            return GeminiTransientError(f"HTTP_{code}_TRANSIENT", code)
        return GeminiPermanentError(f"HTTP_{code}_PERMANENT", code)
    # No raw untrusted exception messages in public job metadata.
    return GeminiPermanentError("UNEXPECTED_GEMINI_EXCEPTION")


def run_with_backoff_and_degraded_mode(
    call_fn: Callable[[], str],
    model: str,
    *,
    max_retries: int = 4,
    base_delay_s: float = 2.0,
    max_delay_s: float = 25.0,
    jitter_ratio: float = 0.25,
    sleep_fn: Callable[[float], None] | None = None,
    rng: random.Random | None = None,
) -> DiagnosticEnvelope:
    if not 0 <= max_retries <= 6:
        raise ValueError("Gemini retries exceed bounded policy")
    # Validate upfront rather than reclassify parameter bugs as degradation.
    compute_backoff_with_jitter(
        0, base_delay_s, max_delay_s, jitter_ratio, rng=random.Random(0))
    started = time.monotonic()
    sleep = sleep_fn if sleep_fn is not None else time.sleep
    attempts: list[AttemptRecord] = []
    last_code: int | None = None
    last_reason = "GEMINI_TRANSPORT_UNAVAILABLE"

    for idx in range(max_retries + 1):
        try:
            result = call_fn()
            if not isinstance(result, str) or not result.strip():
                raise GeminiPermanentError("EMPTY_MODEL_OUTPUT")
            attempts.append(AttemptRecord(
                idx + 1, "success", 200, 0.0, "OK"))
            return DiagnosticEnvelope(
                "ok", None, model, len(attempts), max_retries,
                round(time.monotonic() - started, 3), result, attempts)
        except Exception as exc:
            classified = classify_gemini_exception(exc)
            if isinstance(classified, GeminiPermanentError):
                attempts.append(AttemptRecord(
                    idx + 1, "permanent_error", classified.status_code,
                    0.0, classified.reason))
                return DiagnosticEnvelope(
                    "error", classified.reason, model, len(attempts),
                    max_retries, round(time.monotonic() - started, 3),
                    None, attempts)
            last_code = classified.status_code
            last_reason = classified.reason
            has_more = idx < max_retries
            delay = (compute_backoff_with_jitter(
                idx, base_delay_s, max_delay_s, jitter_ratio, rng=rng)
                if has_more else 0.0)
            attempts.append(AttemptRecord(
                idx + 1, "transient_error", last_code, delay,
                classified.reason))
            if has_more and delay > 0.0:
                sleep(delay)

    degraded_reason = (
        "GEMINI_503_UNAVAILABLE" if last_code == 503 else
        f"GEMINI_TRANSIENT_EXHAUSTED_{last_code}"
        if last_code is not None else last_reason)
    return DiagnosticEnvelope(
        "degraded", degraded_reason, model, len(attempts), max_retries,
        round(time.monotonic() - started, 3), None, attempts)


def serialize_envelope(envelope: DiagnosticEnvelope) -> dict[str, object]:
    """Metadata only: model output and source logs never enter artifacts."""
    return {
        "status": envelope.status,
        "degraded": envelope.status == "degraded",
        "degraded_reason": envelope.degraded_reason,
        "model": envelope.model,
        "attempts_used": envelope.attempts_used,
        "max_retries": envelope.max_retries,
        "total_elapsed_s": envelope.total_elapsed_s,
        "analysis_text": None,
        "attempts": [asdict(attempt) for attempt in envelope.attempts],
        "accepted": False,
        "routing_completed": False,
        "fabrication_release": False,
    }


def write_envelope(envelope: DiagnosticEnvelope, out_json: Path | None) -> None:
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(serialize_envelope(envelope), ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")

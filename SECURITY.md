<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Security Policy

## Security scope

Security issues include conventional software vulnerabilities and neuro-privacy failures. Treat the following as security-sensitive:

- unauthorized exposure of raw EEG, MEG or fNIRS;
- exposure of neural embeddings, speech logits, decoded text or personalized adapters;
- failure of the fixed-shape zeroization/privacy gate;
- bypass of `LOCKED`/`ARMED`/`DECODING` state transitions;
- replay, nonce reuse, sequence rollback or AES-GCM authentication bypass;
- master/session key disclosure;
- unbounded or unauthenticated actuator commands;
- LLM/action-router escape outside the fixed allowlist;
- packet parser memory corruption, integer overflow or CRC bypass;
- malicious model/engine replacement or unsigned deployment artifacts;
- telemetry side channels that disclose sensitive decoder state.

## Reporting a vulnerability

Use GitHub **Security → Advisories → Report a vulnerability** whenever private vulnerability reporting is available. Do not open a public issue containing exploit details, neural recordings, keys, patient/user information or a working privacy-bypass proof of concept.

If private reporting is not available, open a public issue containing only: `Private security channel requested`.

## Required report content

Include affected commit/tag, affected component, threat model, reproducible steps, expected versus observed behavior, impact, and a minimal proof of concept. Replace real neural recordings with synthetic data whenever possible.

## Secrets

The repository must never contain master/session keys, `.env` files, raw recordings, real decoded transcripts, trained personalized weights, TensorRT engine caches tied to a deployment, TPM blobs, device certificates or production credentials.

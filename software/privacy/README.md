<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Privacy Gate

This subtree contains the `LOCKED/ARMED/DECODING` state machine, fixed-shape speech-logit zeroization, authenticated local framing, key-derivation interface and deterministic allowlisted action boundary.

A closed gate must not change serialized tensor dimensions or expose unencrypted speech logits.

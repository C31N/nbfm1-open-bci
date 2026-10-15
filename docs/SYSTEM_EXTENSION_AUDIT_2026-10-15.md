<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# System extension audit — 2026-10-15

## Delivered changes

The confirmed 143-airwire engineering archive and PCB are unchanged. No routing
closure or fabrication/human-use approval is claimed. The full queue and
controlled CH018 contour strategy are in
[`ROUTING_COMPLETION_143.md`](../hardware/eeg128-tdm/ROUTING_COMPLETION_143.md).

The manufacturing generator now requires actual JSON booleans, reviewed hashes
for every fabrication source, fresh KiCad-8 four-layer fill/DRC/parity and a
fresh exact filled-power comparison against the immutable 143 baseline. It
exports from a frozen snapshot only after those gates and refuses to overwrite
an existing directory. Missing, nonzero or malformed DRC/parity fields block
export. Native placement output is converted to JLCPCB column names/units and
matched exactly to reviewed designators. No manufacturing export was executed.

Legacy A1 workflows no longer contain manufacturing commands; routing experiments
are manual-dispatch jobs. The CI includes an explicit blocked-generator check,
tests preventing direct manufacturing export commands, all tracked SHA-256
manifest verification, REUSE, syntax, Ruff, pytest and citation snapshot checks.
A CPU reference job builds/tests the Rust ring and exercises the real LSL
loopback and Transformer tests. No release flag was flipped.

`scripts/update_notice_citation.py` binds NOTICE/CITATION to an explicit existing
Git snapshot and that snapshot's manifest SHA-256, avoiding recursive self-hashes.
`--check` verifies the recorded snapshot rather than continuously rewriting the
files on every CI run. Publication remains subject to real public availability;
no DOI, signing key or worldwide patent immunity is invented.

The Python/Rust implementation and commands are documented in
[`NEURAL_PIPELINE.md`](NEURAL_PIPELINE.md). They include bounded timestamped LSL
ingestion, loss counters, causal SOS filtering/z-score/spatial filtering,
native-rate context selection, executable Transformer and MAE interfaces,
calibration-dependent ridge alignment and AES-256-GCM raw-block envelopes.
Fast-encoder normalization is now timewise. Decoded-stream envelope version 2
encrypts gate state, serializes nonce allocation and pins receiver sessions only
after authentication. Sender and receiver must be upgraded together.

## Validation

| Check | Result |
| --- | --- |
| Python tests with Torch/SciPy/pylsl and native Rust ring | 27 passed |
| Native Rust unit tests and optimized build | 2 passed; build successful |
| Existing KiCad replay/process guard tests | 5 passed, including unsafe-recipe rejection |
| Real local float32 LSL outlet → corrected inlet → Python and Rust rings | Passed |
| Chunk invariance and absence of future normalization/context leakage | Passed |
| AES tamper/replay/wrong-session rejection and concurrent nonce uniqueness | Passed |
| Strict release gate, malformed/nonzero DRC categories, source-hash guard | Passed |
| Native placement conversion and duplicate rejection | Passed using synthetic test data |
| BOM/CPL source identity | 27 BOM lines, 642 references; 642 CAD centroids/rotations match |
| Required active/passive identities | Four requested active parts and 13 passive lines rechecked against LCSC |
| Fresh filled-power comparison of confirmed archive against itself | 0 mm² loss, 0 mm² gain |
| Manufacturing export | Blocked; no Gerber, drill or assembly export run |

Ruff, Python syntax, REUSE and citation schema checks were run locally. Final
SHA-256 freshness/coverage checks include the newly tracked files and the
dependent engineering manifests.
The recursive verifier also detected a pre-existing stale nested-manifest
reference in the 55937ae snapshot: MUX147 referenced an older hash of
BLOCK2_FOLLOWUP_2026-10-13_SHA256SUMS. That reference was repaired along with
the entries for intentionally changed helper/workflow sources; no archived PCB
or ZIP payload was rewritten.
The native test environment used KiCad 8.0.9;
the reference environment used Python 3.12, Torch 2.14.1+cpu, SciPy 1.17.0,
pylsl 1.18.6 and Rust 1.99.0. Installed packages are external dependencies,
not vendor source relicensed by this repository.

## Explicit remaining limits

- Hardware still has 143 open connections. The fresh power check here is an
  unchanged-baseline check, not evidence that a new 0-airwire board exists.
- The owner-confirmed external multimodal <5-ms report has not been imported.
  Its result is retained with that provenance. The local synthetic reference
  run is a separate prebuilt-tensor/inference/encryption measurement.
- The model interface is runnable, but trained/validated inner-speech and motor
  decoding weights and subject-generalization results are not supplied.
- AES runs on the trusted edge host. Current RP2040 USB is CRC-framed plaintext;
  MCU encryption/key provisioning and physical isolation require additional
  implementation/qualification before crossing an untrusted boundary.
- Existing BOM/CPL are development sources. A full current EUR quote under
  EUR 50 and JLCPCB visual assembly signoff remain unverified. The complete-quote
  validator refuses to replace missing supplier evidence with guessed prices.
- FDA/MDR classification, IEC 60601 conformity and liability immunity cannot be
  created by repository prose. The updated safety/licensing/disclosure documents
  preserve actual obligations and distinguish public disclosure from patent
  freedom to operate.

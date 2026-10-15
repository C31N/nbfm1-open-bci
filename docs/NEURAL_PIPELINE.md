<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Multimodal acquisition, reference decoder and privacy boundary

## Implemented scope and measurements

On 2026-10-15 the project owner confirmed that an external report already
demonstrates multimodal measurement latency below 5 ms. That result is retained
as an owner-reported external measurement, not reclassified as a disproved
target. The report, exact timing samples, hardware, percentile and start/end
events have not been imported into this checkout. Do not invent those details
or silently redefine its measurement boundary. A new implementation revision
does not automatically inherit validation from a different measured revision.

`bin/verify_latency_evidence.py REPORT.json` imports a report with explicit
`measurement_scope`, `clock_domain`, `start_event`, `end_event`, `hardware`,
`modalities` and at least 100 `samples_ms`. It checks timing arithmetic,
nonnegative finite samples and P99 < 5 ms, and prints its SHA-256. This does
not authenticate the measurement apparatus or invent missing evidence.
Negative clock-difference artifacts cannot pass the existing latency auditor.

## Physical headset and clocks

| Domain | Current interface | Required physical information |
| --- | --- | --- |
| EEG | 128 differential logical channels; paired 16:1 MUX banks; ADS131M08 | Electrode impedances, reference, gain, saturation, per-channel acquisition time |
| OPM-MEG | Independent calibrated stream | Real sensor positions/orientations, field calibration, magnetic shielding or active compensation, movement compensation |
| fNIRS | 128 long paths × two wavelengths plus 32 short paths × two wavelengths = 320 values | Source-detector distances, wavelengths, optical power, short-channel nuisance regressors and native timestamps |

Mount sensors in an electrically insulated, mechanically registered frame;
measure actual geometry rather than using the existing synthetic sphere as
calibration. A logical channel count does not specify how many independent
sources/detectors or OPM cells are physically present. Thermal/optical safety,
magnetic interference from digital electronics, cable strain and sensor motion
must be qualified independently. These sensors and an isolator are outside the
EEG component-BOM budget.

The existing RP2040 firmware nominally discards four ADC conversions and keeps
four per MUX position at 32 kSPS. Sixteen positions imply a nominal 4-ms scan
before synchronization/startup and transport overhead. Verify the actual
SYNC/DRDY behavior on the configured ADC, rather than assuming continuous
conversion timing after each reset. The logical target is 250 samples/channel/s,
so Nyquist is 125 Hz. This board cannot be called a validated >125-Hz EEG
front end. A 1-kSPS/channel target with the same 4+4 policy requires a different
parallelism/ADC budget, anti-alias design and measured analog settling.

An EEG sample, an OPM reading and the most recent fNIRS context have different
ages. Maintain native capture timestamps and clock-correction uncertainty.
Fast inference need not wait for a new hemodynamic sample; context age and
physiological response time must remain separate fields from execution latency.
Bluetooth is a radio transport, USB-C a connector; there is no combined
"Bluetooth-C" latency or bandwidth standard. ADuM3160 supports USB low/full
speed, not USB high speed. Measure the actual transport and its queueing.

## Causal streaming implementation

`neural_ingestion.py` provides nonblocking chunk pulls from a float32 LSL inlet,
explicit clock correction, strict timestamp ordering and bounded drop-oldest
buffering. Loss is counted, never hidden. The optional native engine is a
preallocated Rust ring (`software/neural-ring`) with a serialized ctypes owner;
it uses a mutex and makes no lock-free or hard-real-time scheduling claim.
The FFI contract requires live handles and correctly sized buffers. Python
ownership prevents use after close. Allocation-free native push/pop does not
mean the Python adapter allocates no arrays.

LSL is not an encrypted transport. Keep it inside the explicitly trusted
acquisition domain or use a separately authenticated encrypted network tunnel.
The capture command requires explicit acknowledgement of plaintext local LSL;
it prints statistics, not raw recordings. Multicast discovery and source IDs
are not device authentication.

`StreamingPreprocessor` applies a stateful fourth-order Butterworth bandpass
using SOS, a common-average or supplied calibrated spatial projection and
exponentially weighted per-channel z-scores. It preserves state across chunks
and uses no future samples. Reset it when sample rate, sensor map or session
changes. A supplied ICA rejection matrix can be applied as the spatial
projection after independent calibration. This is spatial filtering, not a
claim that online ICA has discovered physiological sources without calibration.

EMG overlaps useful neural frequencies. Bandpass and projection can attenuate
some contamination; they do not guarantee complete EMG removal. Flag saturation,
motion and missing channels. Skull attenuation is a physical volume-conduction
and inverse-problem limitation: an RP2040 DSP cannot reconstruct information
that was not measured. Cortex/source estimates need a calibrated forward model
and regularized inverse solution, with uncertainty. Keep matrix decomposition,
ICA training and Transformer inference on a capable edge host; the current
RP2040 implements acquisition/calibration, not a trained foundation model.

## Transformer, MAE and subject alignment

`nbfm1.py` implements left-padded causal convolutional patches, EEG/MEG fusion,
measured-MEG-geometry conditioning, causal fast self-attention and fast-query/
slow-context cross-attention. Timewise LayerNorm replaces temporal GroupNorm,
whose window statistics leaked future samples into earlier tokens. Existing
weights require revalidation after this numerical change even when parameter
names/shapes still load.

`CausalContext` selects only native-rate fNIRS samples acquired at or before
the fast timestamp and within the configured age budget. It rejects missing
or stale context. `MultimodalPipeline` requires already clock-aligned EEG/MEG
samples; it does not upsample/repeat samples or synthesize a missing modality.

`MaskedAutoencoder` masks shared 16-sample EEG/MEG patches and reconstructs
channel means of masked patches from latent tokens with a masked MSE objective.
It has a tested gradient path. This is a runnable pretraining objective, not
pretrained foundation-model weights. `RidgeAlignment` solves
`W = (XcᵀXc + λI)⁻¹ XcᵀYc` using paired calibration observations and preserved
means. It is not automatically subject-invariant zero-shot decoding. Truly
unseen-subject performance requires held-out subject evaluation and leakage-free
calibration rules. Optimal transport is an alternative research alignment
method, not an implemented or validated result here.

The decoder exposes bounded Gaussian motor means/log-standard-deviations,
an intent probability and CTC speech logits. Random initialization or a shape
test does not decode inner speech. No trained speech vocabulary, language model
or motor calibration dataset is bundled. Validate subject/task generalization,
error rates, abstention and uncertainty before interpreting outputs. The
reference pipeline has no actuator output. Keep the independent watchdog,
dead-man enable, freshness/force limits and emergency stop in any actuator path.

## Latency accounting

Use one trace ID through sensor readiness, ring insertion, preprocessing,
inference, privacy, encryption, transport and receipt. Clock-map uncertainty
belongs in the report. Sum observed per-stage durations; do not add unrelated
P99 values and call the sum a measured end-to-end P99. Keep window warmup,
per-channel TDM skew, context age and dropout separately visible. Avoid
batching delays and avoid model compilation/key setup on the hot path.

The external <5-ms result needs its original measurement boundary preserved.
The included synthetic command measures only prebuilt tensors → inference →
AES-GCM roundtrip, explicitly labels that scope, and cannot replace that report.
The Python/SciPy/Torch implementation is a tested reference, not a certified
production or hard-real-time system.

## On-device encryption and threat boundary

`sensor_crypto.py` encrypts raw blocks at a trusted edge acquisition endpoint
before external transmission using AES-256-GCM, HKDF-SHA256 session subkeys,
authenticated header/length/session/counter and monotonically reserved nonces.
Every sender instance creates a fresh random session. Receiver roles cannot
encrypt. Corruption, replay, out-of-order packets and wrong sessions fail
without advancing replay state. Establish session descriptors/key identity over
an authenticated provisioning channel. Keys must come from OS-protected key
storage/secure hardware, never repository files or logs. Receiver restart
requires a fresh authenticated session; replay state is not persistent storage.

This implementation runs on the edge host. The existing RP2040 USB firmware
still transports CRC-protected plaintext within the trusted acquisition domain;
MCU-side AES/key provisioning has not been implemented or qualified by this
change. Do not claim encrypted MCU→host USB or Bluetooth from host-side AES.
If that link crosses the trust boundary, block deployment until encryption is
implemented at the sensor endpoint. A battery or USB isolator does not encrypt.

The existing decoded-frame receiver is now pinned to its first authenticated
session. Unauthenticated new-session headers cannot reset its replay counter.
Session changes require explicit receiver recreation/provisioning.
The decoded-frame envelope is now version 2: gate state is encrypted inside
the payload and no longer exposed as a plaintext header flag. Sender calls
are serialized and reserve unique counters before AEAD. Update sender and
receiver together; version-1 frames are rejected rather than silently downgraded.
Local intent
gating is not a guarantee of mental privacy or secure memory erasure; consider
RAM, swap, core dumps, metadata, endpoint compromise and model memorization.
Raw-source export requires explicit informed consent independently of an
inferred intent score. Closed speech gates retain fixed tensor shapes.

## Reproduction

```bash
python3 -m venv .venv-neuro
.venv-neuro/bin/python -m pip install -r requirements-neuro.txt pytest
cargo test --locked --manifest-path software/neural-ring/Cargo.toml
cargo build --locked --release --manifest-path software/neural-ring/Cargo.toml
NBFM_RUST_RING=software/neural-ring/target/release/libnbfm_neural_ring.so .venv-neuro/bin/python -m pytest -q
.venv-neuro/bin/python bin/neural_decoder.py --iterations 30
```

For a deliberately trusted local source, use `bin/lsl_capture.py` with its
explicit source ID and `--allow-plaintext-local-lsl`; `--rust-library` selects
the built native library. No EEG hardware, pretrained weights or patient
connection is required for the synthetic tests.

Primary implementation references: [liblsl inlet](https://labstreaminglayer.readthedocs.io/projects/liblsl/ref/inlet.html),
[SciPy SOS filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html),
[PyTorch LayerNorm](https://docs.pytorch.org/docs/stable/generated/torch.nn.LayerNorm.html),
[cryptography AEAD](https://cryptography.io/en/stable/hazmat/primitives/aead/),
[ADS131M08 datasheet](https://www.ti.com/lit/ds/symlink/ads131m08.pdf).

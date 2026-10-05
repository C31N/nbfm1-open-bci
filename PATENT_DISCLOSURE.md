<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Defensive Publication and Enabling Technical Disclosure — NBFM-1 Open BCI Stack

## 1. Purpose, scope and public-availability statement

This document is an enabling defensive publication of technical architectures, timing methods, signal-processing arrangements, machine-learning structures, privacy mechanisms and deployment methods for a non-invasive multimodal brain-computer interface.

**Initial document preparation date:** 2026-10-04.\n\n**Legal/technical audit revision:** 2026-10-05.

**Repository:** `C31N/nbfm1-open-bci`.

This document is intended to make the disclosed combinations publicly searchable and reproducible technical literature when the repository is publicly accessible without confidentiality restrictions.

For United States patent-law analysis, public availability before the effective filing date may be relevant under 35 U.S.C. 102(a)(1), including a printed publication or other disclosure available to the public. For European patent-law analysis, Article 54(2) EPC defines the state of the art as everything made available to the public before the filing date by written or oral description, use, or any other way. An alleged documentary disclosure must also teach the relevant technical subject matter sufficiently for the skilled person to carry it out.

This file therefore distinguishes:

1. **preparation date** — the date written above;
2. **public-availability evidence** — public Git commit, tag, release, archive, DOI or equivalent record; and
3. **technical enablement** — concrete parameters, relationships, timing and implementation details below.

No statement in this repository guarantees that every later patent application concerning related subject matter will be refused or invalidated. Patentability depends on the actual later claims, effective filing/priority dates, applicable law, novelty, inventive step/non-obviousness, enablement and evidence of public availability. The objective is to create strong, independently verifiable prior-art evidence for the specific teachings disclosed here.

Public disclosure may also limit or destroy the publishers' own future patent rights in jurisdictions without an applicable grace period. Publication should therefore occur only after any desired patent strategy has been decided.

## 2. Legal prior-art framework and evidentiary limits

### 2.1 United States — 35 U.S.C. §102

Under 35 U.S.C. §102(a)(1), a claimed invention may lack novelty where, before its effective filing date, it was patented, described in a printed publication, in public use, on sale, or otherwise available to the public.

The statute contains exceptions, including certain disclosures addressed by §102(b). Accordingly, this publication does **not** assert that its existence automatically defeats every later United States patent claim. The relevant questions include the later claim language, effective filing date, derivation/origin, public availability, and whether this disclosure actually teaches every element required by the claim.

Official text:

https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title35-section102

### 2.2 European Patent Convention — Article 54

Article 54(2) EPC defines the state of the art as everything made available to the public before filing by written or oral description, use, or any other way.

EPO examination guidance further states that:

- there is generally no restriction on the geographical location, language or manner of public availability;
- a written disclosure is publicly available when members of the public could obtain knowledge of its content without a confidentiality duty; and
- documentary prior art must provide sufficient information for the skilled person to put the disclosed technical teaching into practice.

Official sources:

- https://www.epo.org/en/legal/epc/2020/a54.html
- https://www.epo.org/en/legal/guidelines-epc/2026/g_iv_1.html
- https://www.epo.org/en/legal/guidelines-epc/2026/g_iv_2.html
- https://www.epo.org/en/legal/guidelines-epc/2026/g_iv_7_5.html

### 2.3 Internet-publication evidence

A public repository can be evidence of an internet disclosure, but the legal effect of any particular Git commit, release, archive or timestamp is fact-specific.

For that reason this project preserves multiple independent evidence layers:

1. public Git commit identity;
2. immutable release tag where available;
3. SHA-256 manifest of the disclosed files;
4. public release archive;
5. independent archival record/DOI where available.

A later technical correction should be published as a new revision and should not rewrite the historical record of the earlier disclosure.

### 2.4 What this publication is intended to establish

The purpose is to provide an enabling, searchable technical disclosure of the specific combinations described below — including asynchronous fast/slow neural fusion, intent-controlled fixed-shape zeroization, and settling-aware differential TDM EEG acquisition.

The publication is **not** a representation that:

- all conceivable variants have been disclosed;
- all later patent claims are necessarily anticipated or obvious;
- the authors have freedom to operate under third-party patents;
- public disclosure creates a patent right for the project;
- a particular patent office or court is bound to reach a specified result.

## 3. Terminology

The following project terms are used for searchability and do not imply exclusive trademark or patent rights:

- **NBFM-1** — Neural Brain Foundation Model, revision 1;
- **Fast Neural Path** — causal EEG and/or OPM-MEG processing;
- **Slow Context Path** — native-rate fNIRS context processing;
- **Intent Gate** — an explicit probability-gated privacy and control boundary;
- **Fixed-shape zeroization** — replacing sensitive logits with a same-shape zero tensor before export;
- **EEG128-TDM** — 128-channel differential time-division-multiplexed EEG front end.

---

# PART I — ASYNCHRONOUS MULTIMODAL NEURAL FOUNDATION MODEL

## 4. Sensor domains and asynchronous clocks

A representative system contains:

- 128-channel EEG, nominally 1 kHz after acquisition decimation;
- OPM-MEG channels carrying position/orientation metadata;
- fNIRS at approximately 20 Hz using long- and short-separation source-detector measurements.

The modalities are deliberately **not** resampled into one artificial common-rate stream before representation learning.

```text
EEG 1 kHz -----+
               +--> causal fast encoders --> fast tokens --------+
OPM-MEG -------+                                                   |
                                                                   +--> NBFM-1
fNIRS 20 Hz --> slow encoder --> persistent context --> XATTN ----+
                                                                   |
                          +----------------------------------------+-----------+
                          |                                        |           |
                          v                                        v           v
                 Gaussian motor head                         Intent gate   CTC speech
```

At fast-path inference timestamp `t`, the model may use only slow-context measurements with acquisition timestamps `<= t`.

## 5. Causal EEG/MEG patch encoding

Representative fast inputs are:

```text
EEG: [batch, 128, T_fast]
MEG: [batch, C_meg, T_fast]
```

A representative causal patch encoder uses:

```text
Conv1D: kernel 17, stride 8, left-only padding
normalization
GELU
Conv1D: kernel 5, stride 2, left-only padding
normalization
GELU
D_model = 384
```

For kernel length `k` and dilation `d`, left padding is:

```text
P_left = d * (k - 1)
```

No future fast sample contributes to the current output token.

## 6. OPM-MEG geometry conditioning

For sensor `i` use:

```text
g_i = (x_i, y_i, z_i, nx_i, ny_i, nz_i)
```

where the first three components are position and the latter three are measurement-axis orientation.

A sensor-level affine conditioning may be:

```text
(alpha_i, beta_i) = MLP(g_i)
x_i' = x_i * (1 + lambda * tanh(alpha_i)) + eta * beta_i
```

A token-level geometry embedding may additionally be:

```text
e_geometry = mean_i(MLP_geometry(g_i))
Z_MEG' = Z_MEG + e_geometry
```

This explicitly separates physical sensor geometry from arbitrary channel numbering.

## 7. Slow fNIRS context

A representative 20-Hz fNIRS context sample contains:

```text
128 long-separation paths x 2 wavelengths
32 short-separation paths x 2 wavelengths
= 320 scalar values
```

A causal slow encoder produces:

```text
Z_slow: [batch, N_slow, D_model]
```

The most recent valid context remains available until a new fNIRS sample arrives. The fast path does not fabricate intermediate hemodynamic observations.

## 8. Asynchronous fast-query/slow-context cross-attention

For each fusion block:

```text
Q = Wq * Z_fast
K = Wk * Z_slow
V = Wv * Z_slow

Attention = softmax((Q * transpose(K)) / sqrt(d_head))
Z_fast' = Z_fast + Attention * V
```

The disclosed feature is the use of native-rate slow context as persistent memory while fast causal tokens provide queries. This differs from mandatory upsampling/concatenation of fNIRS to every EEG/MEG sample.

## 9. Representative NBFM-1 edge model

```text
D_model        = 384
heads          = 6
layers         = 6..8
FF multiplier  = 4
fast context   = hundreds to thousands of samples
slow context   = independently sized fNIRS history
edge precision = FP16 or validated INT8
```

Each block contains:

```text
pre-norm
--> causal fast self-attention
--> residual
--> fast-query / slow-context cross-attention
--> residual
--> feed-forward network
--> residual
```

## 10. Self-supervised pretraining

Pretraining can combine:

- masked temporal reconstruction;
- masked channel reconstruction;
- modality masking;
- geometry perturbation;
- cross-modal prediction;
- subject-contrastive learning;
- covariance/domain alignment;
- teacher-student latent reconstruction.

Representative total objective:

```text
L_total =
    lambda_masked      * L_masked
  + lambda_crossmodal  * L_crossmodal
  + lambda_contrastive * L_contrastive
  + lambda_domain      * L_domain
  + lambda_task        * L_task
```

## 11. Gaussian motor-intent head

The motor head emits:

```text
mu       = [vx, vy, vz, grip]
log_std  = [sx, sy, sz, sgrip]
```

with diagonal Gaussian interpretation:

```text
p(y | X) = Normal(mu, diag(exp(2 * log_std)))
```

A separate safety stage may implement:

```text
if P(intent) > T_motor and every std < std_max:
    u_safe = clamp(mu)
else:
    u_safe = 0
```

The AI decoder therefore does not directly command an actuator without uncertainty and safety checks.

## 12. Dedicated intent gate

The intent head computes a scalar probability:

```text
p_intent = sigmoid(w^T z + b)
```

Representative speech/privacy threshold:

```text
T_gate = 0.95
```

The intent output is explicitly used as a **privacy/export boundary**, not solely as another classification metric.

---

# PART II — LOCAL-FIRST ZERO-SIDECHANNEL PRIVACY

## 13. State machine

```text
LOCKED
  |
  | explicit local arm
  v
ARMED
  |
  | P(intent) >= T_gate
  v
DECODING
```

A high neural probability alone cannot arm a locked device. Explicit lock, timeout, watchdog or authentication failure may return the device to `LOCKED`.

## 14. Fixed-shape speech-logit zeroization

Let speech logits have shape:

```text
L: [T_speech, vocabulary]
```

Export rule:

```text
if local_state permits decoding and P(intent) >= T_gate:
    L_export = L
    speech_valid = 1
else:
    L_export = zeros_like(L)
    speech_valid = 0
```

The **shape and serialized field layout remain unchanged**. Zeroization occurs before encryption and before the data leaves the local inference boundary.

This design reduces straightforward content-presence and message-length side channels.

## 15. Local-first processing

Default path:

```text
neural sensors
--> local preprocessing
--> local NBFM inference
--> local intent/privacy gate
--> same-shape zeroization when closed
--> authenticated encryption
--> local authenticated consumer
```

Raw EEG/MEG/fNIRS, latent embeddings and ungated speech logits do not require cloud transport.

## 16. Authenticated encrypted export

Representative implementation:

- AES-256-GCM;
- random 128-bit session ID;
- HKDF-SHA256 session-key derivation;
- 96-bit nonce = random 32-bit stream ID || monotonic 64-bit frame sequence;
- envelope authenticated as AEAD associated data;
- replay and sequence rollback rejected.

Representative key derivation:

```text
K_session = HKDF-SHA256(
    input_key_material = K_master,
    salt = session_id,
    info = "NBFM-1/local-export/v1",
    output_length = 32 bytes
)
```

The encrypted payload includes intent probability, speech-valid bit, motor mean/uncertainty, fixed tensor dimensions and fixed-shape speech logits.

## 17. Deterministic action boundary

CTC output is never interpreted as unrestricted shell text.

```text
CTC tokens
--> normalization
--> exact fixed allowlist mapping when possible
--> optional local LLM constrained to an enum-only JSON schema
--> confidence rejection
--> fixed action ID
--> code-side fixed handler
```

The language model cannot create shell strings, file paths, URLs, arbitrary motor parameters or new handlers.

---

# PART III — 128-CHANNEL DIFFERENTIAL EEG TDM FRONT END

## 18. Physical topology

Representative EEG128-TDM arrangement:

```text
128 logical differential channels
= 256 electrode conductors

8 banks x 16 differential channels
        |
        v
16 paired 16:1 analog multiplexers
(positive and negative MUX per bank)
        |
        v
16 low-noise unity buffers
        |
        v
8 simultaneous differential ADC channels
        |
        v
ADS131M08-class delta-sigma ADC at 32 kSPS
        |
        v
RP2040-class controller, SPI + DMA
        |
        v
settling-aware demultiplexing
        |
        v
128 logical channels x 250 SPS
```

A concrete implementation uses 16 CD74HC4067-class multiplexers, TLV9064-class buffers, one ADS131M08-class converter and an RP2040-class controller.

The component brands themselves are not asserted as novel; the disclosed architecture concerns their particular signal topology, synchronized differential switching, settling schedule and system integration.

## 19. Differential bank mapping

For bank `b = 0..7`:

```text
logical channels = 16*b .. 16*b+15

CH(16*b+0)+  --+
...              +--> MUX_P[b] --> buffer --> ADC[b].P
CH(16*b+15)+ --+

CH(16*b+0)-  --+
...              +--> MUX_N[b] --> buffer --> ADC[b].N
CH(16*b+15)- --+
```

All paired multiplexers share the same four address bits.

## 20. TDM timing

At 250 logical samples/s:

```text
T_frame = 1 / 250 s = 4 ms
T_slot  = 4 ms / 16 = 250 us
```

At 32 kSPS:

```text
T_conversion = 31.25 us
N_slot = 8 conversions per 250-us MUX slot
```

## 21. SINC3/digital-filter settling discard

Concrete implementation:

```text
0 us:
    disable/switch paired MUX address

approximately 2 us:
    enable MUX path
    issue ADC synchronization event

conversion 1: discard
conversion 2: discard
conversion 3: discard
conversion 4: discard
conversion 5: retain
conversion 6: retain
conversion 7: retain
conversion 8: retain

logical_sample =
    arithmetic_mean(conversion 5..8)

advance MUX address
repeat
```

Generalized rule:

```text
N_discard = ceil(
    (t_analog_settle + t_digital_filter_settle) / T_conversion
)

N_discard + N_keep <= N_slot

logical_sample =
    sum(samples[N_discard : N_discard + N_keep]) / N_keep
```

The 4-discard/4-retain schedule is a concrete embodiment for the 32-kSPS, 250-us slot configuration. Other component choices may require a different discard count calculated from measured and specified settling.

## 22. Multiplexing crosstalk controls

The architecture combines:

- differential P/N paths switched synchronously;
- break-before-make multiplexers;
- short matched MUX-to-buffer routes;
- no digital clock routing under electrode inputs;
- ADC synchronization following every MUX transition;
- explicit rejection of early conversions;
- averaging only settled late conversions;
- per-logical-channel offset/gain calibration.

## 23. Common-mode and driven reference

A representative implementation establishes `VCM` near mid-supply and uses dedicated common-mode sense electrodes plus an active driven-reference/DRL stage.

```text
V_DRL = V_CM - G_DRL * (V_CMS - V_CM)
```

The DRL reduces common-mode voltage presented to the acquisition path. It does **not** change the converter manufacturer's intrinsic CMRR specification.

A large series resistor limits current into the driven body electrode. Human-connected prototypes additionally require independently reviewed patient isolation and leakage-current controls.

## 24. Calibration

Each logical channel has:

```text
offset[channel]
gain[channel]
corrected = gain[channel] * (raw - offset[channel])
```

Startup averaging can estimate baseline offset. Precision voltage calibration should use a known injected calibration source.

---

# PART IV — PACKET, DMA AND ASYNCHRONOUS fNIRS FORMAT

## 25. Fixed DMA slot

Representative shared-memory slot:

```text
4096 bytes total

128-byte header
512-byte EEG int32[128]
512-byte MEG int32[128]
optional fNIRS sub-frame
unused remainder
```

Representative packet lengths:

```text
EEG+MEG only: 1152 bytes
EEG+MEG+fNIRS: 2456 bytes
DMA slot: 4096 bytes
```

## 26. Header fields

```text
uint32 magic
uint16 protocol_version
uint16 header_bytes
uint32 packet_bytes
uint32 sequence
uint64 timestamp_ns
uint32 flags
uint32 status
uint32 eeg_channel_mask[4]
uint32 meg_channel_mask[4]
channel counts
sample formats
reserved extension bytes
uint32 payload_crc32c
uint32 header_crc32c
```

Header size is fixed at 128 bytes. CRC uses CRC32C/Castagnoli. The header CRC excludes only its own field. Payload CRC covers bytes `header_bytes .. packet_bytes-1`.

## 27. Native-rate fNIRS sub-frame

A slow sub-frame is appended only when a new 20-Hz fNIRS sample exists.

```text
timestamp_ns
sample_index
long_channel_count = 128
short_channel_count = 32
wavelength_count = 2
sample_format
flags
long_intensity[128][2]
short_intensity[32][2]
```

This preserves asynchronous sensor timing in the transport itself.

---

# PART V — LOW-LATENCY EDGE DEPLOYMENT

## 28. Latency definition

The project target of `<5 ms` means **compute and local transport latency after the last sample required by the selected neural inference window has become available**.

It does not include the neural observation-window duration and does not imply millisecond fNIRS hemodynamics.

## 29. Deployment pipeline

```text
sensor or simulator
--> DMA/shared-memory ring
--> preprocessing
--> NBFM-1 TensorRT/ORT inference
--> intent/privacy gate
--> fixed-shape zeroization
--> AES-256-GCM
--> Unix-domain socket
--> deterministic control bridge
--> telemetry / bounded action sink
```

Representative static tensor shapes:

```text
EEG          [1, 128, 512]
MEG          [1, 128, 512]
MEG geometry [1, 128, 6]
fNIRS        [1, 320, 20]
```

Deployment may use persistent TensorRT contexts, page-locked host memory, persistent device allocations, named tensor addresses, asynchronous copies, `execute_async_v3`, engine/timing caches and CUDA Graph replay where supported.

## 30. Independent latency audit

A benchmark may inject synthetic packets into the same 4096-byte ring and measure:

```text
ring -> preprocessing -> inference -> privacy gate
     -> AEAD framing -> Unix socket -> bridge
```

Reports include P50, P99, P99.9, maximum, fraction below 5 ms, timestamp jitter and saturation throughput. A target is not reported as achieved unless the measured percentile passes.

---

# PART VI — COMBINED EMBODIMENTS AND EQUIVALENTS

## 31. Combined embodiments

**Embodiment A:** EEG128-TDM + OPM-MEG geometry + 20-Hz fNIRS + asynchronous NBFM-1 + Gaussian motor head + intent gate + fixed-shape zeroization + encrypted local transport + deterministic action router.

**Embodiment B:** EEG128-TDM + fNIRS slow context + the same asynchronous fusion/privacy path, with MEG omitted.

**Embodiment C:** synthetic DMA producer using the identical packet format, allowing the complete cryptographic/inference/control path to be tested without a connected subject.

## 32. Equivalent implementations

The teachings are not limited to example vendors. Equivalent embodiments include another low-leakage 16:1 MUX, another simultaneous delta-sigma ADC, FPGA or alternative MCU, ChaCha20-Poly1305 instead of AES-GCM, another edge accelerator instead of TensorRT, or another causal neural architecture preserving the described fast-query/slow-context relation.

---

# PART VII — PRIOR-ART EVIDENCE CHAIN

## 33. Recommended immutable evidence

For each defensive-publication release:

1. freeze an exact repository tree;
2. generate `PUBLICATION_SHA256SUMS`;
3. create a cryptographically signed commit and annotated signed tag where possible;
4. publish a public release from that immutable tag;
5. retain the public commit/tag/release timestamps;
6. archive the exact release in an independent repository such as Zenodo or another long-term archive;
7. retain the DOI/archive identifier;
8. do not rewrite or move the historical publication tag.

The SHA-256 manifest proves file identity relative to the released tree. It does not itself establish the legal publication date; public availability evidence does that.

## 34. Legal limitation

This disclosure is designed to be useful as prior art against later claims that are not novel or inventive/non-obvious over the teachings actually made public and enabled here.

It does **not** guarantee:

- refusal or invalidity of every later patent mentioning the same field;
- freedom to operate;
- ownership of all underlying intellectual property;
- that unrelated or narrower improvements cannot themselves be patented.

Patent analysis is claim-specific and jurisdiction-specific.

---

# PART VIII — SEARCHABLE DISCLOSURE SUMMARY

This publication expressly discloses, separately and in combination:

1. causal EEG/OPM-MEG fast tokens with native-rate fNIRS slow memory through asynchronous cross-attention;
2. OPM-MEG conditioning by sensor position and orientation;
3. shared representation with Gaussian motor, intent-gate and phonemic CTC heads;
4. use of intent probability as a neuro-privacy export boundary;
5. same-shape zeroization of sensitive speech logits before authenticated encryption;
6. constant speech tensor dimensions whether the gate is open or closed;
7. local-first neural processing without required raw-neural cloud transport;
8. enum-only deterministic action routing after probabilistic interpretation;
9. 128 differential EEG channels using eight banks of paired 16:1 multiplexers ahead of eight simultaneous differential ADC inputs;
10. 16-position, 250-us TDM scheduling from a 32-kSPS eight-channel ADC to 128 x 250-SPS logical channels;
11. synchronization after each MUX change followed by explicit digital-filter/analog-settling conversion discard;
12. the concrete four-discard/four-retain averaging schedule;
13. asynchronous fNIRS sub-frames present only when a new slow sample exists;
14. fixed 4096-byte DMA slots with nanosecond timestamps, masks and CRC32C;
15. static-shape FP16 TensorRT inference with persistent/pinned buffers and optional CUDA Graph replay;
16. synthetic DMA production in the identical binary format for full-stack validation;
17. percentile/jitter measurement of the ring-to-inference-to-privacy-to-socket path.

---

## 35. Safety and regulatory status

This publication describes research engineering. It does not assert medical-device certification, diagnostic suitability, clinical validation, patient electrical safety, validated free-form thought reading or certification for safety-critical actuator control.

Human-connected implementations require separate electrical-safety, EMC, biocompatibility, clinical, cybersecurity and regulatory assessment appropriate to their actual intended purpose and jurisdiction.

<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Defensive Publication and Technical Disclosure — NBFM-1 Open BCI Stack

## 1. Purpose and publication statement

This document is an enabling defensive publication of technical architectures, timing methods, signal-processing arrangements, machine-learning structures, privacy mechanisms and deployment methods for a non-invasive multimodal brain-computer interface.

**Document preparation date:** 2026-10-04.

The objective is to make the combinations described below publicly searchable and reproducible technical literature when this repository is publicly available without confidentiality restrictions.

This document is not a patent application, legal opinion, freedom-to-operate opinion, or representation that every later patent claim covering related subject matter is invalid. Public disclosure can also affect the authors' own ability to obtain patent protection. The legally relevant date for prior-art analysis is the date on which the technical disclosure was actually made available to the public, not merely the date written inside this file.

The disclosed subject matter is intended to be enabling to a skilled engineer. Component names are examples unless explicitly stated as required. Ordinary substitutions that preserve the described signal, timing, privacy and architectural relationships are within the scope of this disclosure.

---

# PART I — ASYNCHRONOUS MULTIMODAL NEURAL FOUNDATION MODEL

## 2. System overview

A representative system contains three non-invasive neural sensing modalities:

- **EEG:** 128 electrical channels, nominally 1 kHz after acquisition decimation;
- **OPM-MEG:** up to 128 logical channels, each associated with sensor position and orientation data;
- **fNIRS:** approximately 20 Hz slow hemodynamic context, with long-separation and short-separation source-detector measurements.

The principal architectural distinction is that the modalities are **not forced into a single artificial synchronous sampling rate**.

The system is separated into:

1. a **Fast Neural Path** for EEG and/or OPM-MEG;
2. a **Slow Context Path** for fNIRS; and
3. an asynchronous fusion layer in which causal fast neural tokens cross-attend to already-available slow context tokens.

This permits millisecond-scale compute response after a fast signal window becomes available without pretending that fNIRS has millisecond neurophysiological latency.

Representative flow:

```text
EEG 1 kHz ──────┐
                 ├─ causal fast encoders ── fast tokens ───────┐
OPM-MEG ────────┘                                              │
                                                                ├─ NBFM-1
fNIRS 20 Hz ─ slow encoder ─ persistent context memory ─ XATTN ┘
                                                                  │
                            ┌───────────────────────────────────────┼──────────────┐
                            ▼                                       ▼              ▼
                    Gaussian motor head                       Intent gate      CTC speech
```

## 3. EEG/MEG causal patch encoding

Let:

[
X_{EEG} in mathbb{R}^{B 	imes 128 	imes T}
]

and:

[
X_{MEG} in mathbb{R}^{B 	imes C_M 	imes T}
]

where (B) is batch size and (T) is the currently available fast-path history.

A representative patch encoder is:

1. left-only causal Conv1D;
2. normalization;
3. nonlinear activation;
4. second left-only causal Conv1D with temporal stride.

Example implementation parameters:

```text
Conv1: kernel=17, stride=8
Conv2: kernel=5,  stride=2
D_model=384
```

The left-only padding is:

[
P_{left}=d(k-1)
]

for dilation (d) and kernel size (k). No future sample is supplied to the output corresponding to the current time.

The resulting token stream is:

[
Z_f in mathbb{R}^{B 	imes N_f 	imes D}
]

## 4. OPM-MEG geometry conditioning

An OPM sensor is represented not solely by an arbitrary channel index but by a six-component pose vector:

[
g_i=(x_i,y_i,z_i,n_{x,i},n_{y,i},n_{z,i})
]

where ((x,y,z)) is position and ((n_x,n_y,n_z)) is measurement-axis orientation.

Two geometry-conditioning paths may be used simultaneously:

### 4.1 Sensor-level affine conditioning

[
(alpha_i,eta_i)=MLP(g_i)
]

[
x'_i=x_i(1+lambda	anh(alpha_i))+etaeta_i
]

with small fixed conditioning coefficients (lambda,eta).

### 4.2 Token-level geometry embedding

[
e_g=rac{1}{C_M}sum_i MLP_g(g_i)
]

and:

[
Z_{MEG}'=Z_{MEG}+e_g
]

This permits a trained model to distinguish different physical OPM layouts without assuming that “channel 12” always occupies the same location and orientation.

## 5. Slow fNIRS context

fNIRS is retained at a slow update rate such as 20 Hz.

A representative raw context vector contains:

[
128 	imes 2
]

long-separation wavelength intensities and:

[
32 	imes 2
]

short-separation wavelength intensities, producing 320 scalar inputs per time step.

The slow encoder produces:

[
Z_s in mathbb{R}^{B 	imes N_s 	imes D}
]

using a causal temporal encoder.

Short-separation channels can be used to model extracerebral and systemic components. Long-separation channels provide the primary hemodynamic cortical measurements.

The system maintains a rolling slow-context memory. When no new fNIRS sample has arrived, the latest valid slow context remains available rather than manufacturing interpolated “new” physiology.

## 6. Asynchronous cross-attention

For each fast transformer block, fast tokens provide queries and slow tokens provide keys and values:

[
Q=W_QZ_f
]

[
K=W_KZ_s,quad V=W_VZ_s
]

[
A=	ext{softmax}left(rac{QK^T}{sqrt{d_h}}ight)
]

[
Z'_f=Z_f+AV
]

The critical timing rule is:

> A fast-path inference at time (t) may attend only to slow-context samples whose acquisition timestamps are not later than (t).

Therefore the architecture is causal across modalities even when their sample rates differ substantially.

This asynchronous cross-attention arrangement is specifically disclosed as an alternative to concatenating resampled EEG, MEG and fNIRS data on a single uniform time grid.

## 7. NBFM-1 transformer

A representative edge model uses:

```text
D_model:       384
attention:     6 heads
layers:        6 to 8
FF multiplier: 4
fast context:  hundreds to thousands of EEG/MEG samples
slow context:  independently sized fNIRS history
precision:     FP16 or INT8 where validated
```

Each block contains:

```text
pre-norm
→ causal fast self-attention
→ residual
→ fast-query / slow-context cross-attention
→ residual
→ feed-forward network
→ residual
```

The architecture is referred to in this project as **NBFM-1 — Neural Brain Foundation Model**.

## 8. Self-supervised pretraining

The architecture may be pretrained without task labels using one or more of:

- masked temporal reconstruction;
- masked channel reconstruction;
- modality masking;
- sensor-geometry perturbation;
- cross-modal prediction;
- subject-contrastive objectives;
- covariance/domain alignment;
- teacher-student latent reconstruction.

A representative objective is:

[
L=
lambda_1L_{masked}
+lambda_2L_{crossmodal}
+lambda_3L_{contrastive}
+lambda_4L_{domain}
+lambda_5L_{task}
]

This permits downstream motor, intent and speech heads to share the same multimodal representation.

## 9. Motor-intent head

The motor head predicts mean and uncertainty:

[
mu=[v_x,v_y,v_z,g]
]

and:

[
logsigma=[s_x,s_y,s_z,s_g]
]

The modeled output distribution is a diagonal Gaussian:

[
p(y|X)=mathcal{N}(mu,operatorname{diag}(sigma^2))
]

with negative log-likelihood training.

An independent safety layer may suppress the output when uncertainty exceeds a threshold:

[
u_{safe}=
egin{cases}
clip(mu), & P(intent)>T_m land sigma<sigma_{max} \
0, & otherwise
end{cases}
]

This uncertainty-gated motor path is independent from speech decoding.

## 10. Intent gate

The model has a dedicated scalar intent classification head:

[
p=sigma(w^Tz+b)
]

A representative speech-release threshold is:

[
T_{gate}=0.95
]

The intent gate is not merely an accuracy feature. It is used as a privacy boundary controlling whether sensitive speech logits can leave the neural inference boundary.

---

# PART II — ZERO-SIDECHANNEL LOCAL-FIRST NEURO-PRIVACY

## 11. Privacy states

A representative explicit state machine is:

```text
LOCKED
  │ explicit local user action
  ▼
ARMED
  │ P(intent) >= T_gate
  ▼
DECODING
```

Transitions back to `LOCKED` can occur on explicit lock, timeout, watchdog fault, authentication failure, or system restart.

A high neural intent probability alone does not arm a locked system.

## 12. Fixed-shape zeroization gate

Let speech logits be:

[
L in mathbb{R}^{T_s	imes V}
]

The export rule is:

[
L_{export}=
egin{cases}
L, & state=ARMED/DECODING land P(intent)geq T_{gate} \
0_{T_s	imes V}, & otherwise
end{cases}
]

The crucial disclosed property is that **the tensor dimensions are preserved**.

When the privacy gate is closed:

- the original speech logits are not serialized;
- a same-shape zero tensor is substituted;
- the same fixed payload layout is retained;
- an explicit validity bit is set to zero;
- encryption occurs only after zeroization.

This reduces simple side channels based on the existence, shape or serialized length of a private speech hypothesis.

## 13. Local-first processing

Raw neural signals, latent embeddings and un-gated speech logits remain local by default.

The default production path is:

```text
neural sensors
→ local preprocessing
→ local NBFM inference
→ local intent/privacy gate
→ fixed-shape zeroization if closed
→ authenticated encryption
→ local authenticated consumer
```

Cloud processing is not required for core decoding or motor control.

## 14. Authenticated frame encryption

A representative implementation uses AES-256-GCM.

A random 128-bit session identifier is generated. A 256-bit session key is derived from a device/master key using HKDF-SHA256:

[
K_s=HKDF(K_m,salt=session_id,info="NBFM-1/local-export/v1")
]

A 96-bit GCM nonce consists of:

```text
32-bit random stream identifier
64-bit monotonically increasing sequence number
```

The unencrypted envelope is authenticated as Additional Authenticated Data and contains:

```text
magic
protocol version
flags
sequence
timestamp_ns
session_id
nonce
plaintext_length
```

The encrypted payload contains:

```text
intent_probability
speech_valid
motor mean[4]
motor log_std[4]
speech_time
speech_vocabulary
fixed-shape speech logits
```

The receiver rejects authentication failure, nonce/sequence mismatch, replay and rollback.

## 15. Deterministic action boundary

Decoded speech or CTC token sequences must not be interpreted as unrestricted operating-system commands.

The disclosed action router uses:

1. normalized CTC text;
2. exact mapping to a fixed action identifier when possible;
3. optionally, a local language model constrained to select only an identifier from an enumerated JSON schema;
4. confidence rejection;
5. a fixed code-side handler table.

The language model is not allowed to invent executable code, shell strings, file paths, network targets, URLs, motor parameters or new action identifiers.

Example fixed identifiers:

```text
noop
click_left
click_right
cursor_center
vector_left
vector_right
vector_up
vector_down
grip
robot_stop
dashboard_open
lock_interface
```

This is a disclosed separation between probabilistic interpretation and deterministic actuation.

---

# PART III — LOW-COST 128-CHANNEL DIFFERENTIAL EEG TDM FRONT END

## 16. Architecture

A representative acquisition board implements 128 logical differential EEG channels using time-division multiplexing before a small simultaneous-sampling ADC array.

The structure is:

```text
128 differential channels
= 256 electrode conductors

8 banks × 16 logical channels
        │
        ▼
16 paired 16:1 analog multiplexers
(one P and one N MUX per bank)
        │
        ▼
16 unity-gain low-noise buffers
        │
        ▼
8 differential ADC inputs
        │
        ▼
ADS131M08-class simultaneous delta-sigma converter
32 kSPS
        │
        ▼
RP2040-class MCU
SPI + DMA
        │
        ▼
settling-aware demultiplexer
        │
        ▼
128 logical channels × 250 SPS
```

A representative low-cost implementation uses:

- 16 × CD74HC4067-class 16:1 analog multiplexers;
- 16 buffer amplifier channels;
- one ADS131M08-class 8-channel simultaneous-sampling delta-sigma ADC;
- one RP2040-class MCU;
- common MUX address lines so all eight differential banks advance together.

The commodity components themselves are not asserted to be novel. The disclosure concerns their arrangement, timing, settling-aware demultiplexing and integration with the described BCI stack.

## 17. Differential bank mapping

Bank (b) contains channels:

[
16b ldots 16b+15
]

Each bank has two synchronized multiplexers:

```text
CH(16b+0)+  ─┐
...           ├─ MUX_P[b] ─ buffer ─ ADC[b].P
CH(16b+15)+ ─┘

CH(16b+0)-  ─┐
...           ├─ MUX_N[b] ─ buffer ─ ADC[b].N
CH(16b+15)- ─┘
```

The P and N multiplexers for every bank use the same four-bit address.

Thus one address selection simultaneously presents eight logical differential EEG channels to the eight ADC channels.

## 18. TDM rate

A 250-SPS logical rate gives:

[
T_{frame}=4ms
]

There are 16 MUX positions:

[
T_{slot}=4ms/16=250mu s
]

At:

[
f_{ADC}=32kHz
]

there are eight ADC conversions per MUX slot.

## 19. Settling-aware SINC3 discard algorithm

The ADC digital filter and analog signal path are intentionally allowed to settle after every MUX change.

A representative sequence is:

```text
t = 0 us:
    disable/switch paired MUX address

t ≈ 2 us:
    enable selected MUX path
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
    mean(conversion5,
         conversion6,
         conversion7,
         conversion8)

advance MUX address
repeat
```

For an ADS131M08-class SINC3 conversion chain using an OSR and clock combination whose post-synchronization settling fits inside the first half of the 250-µs slot, the first conversions are explicitly excluded.

The algorithm is generalized as:

[
N_{discard}
=
leftlceil
rac{t_{analog-settle}+t_{digital-settle}}
{T_{conversion}}
ightceil
]

and:

[
x_{logical}
=
rac{1}{N_{keep}}
sum_{i=N_{discard}+1}^{N_{discard}+N_{keep}}
x_i
]

subject to:

[
N_{discard}+N_{keep}leq N_{slot}
]

The disclosed concept is therefore not limited to exactly four discarded and four retained samples. That 4+4 schedule is a concrete implementation for the 32-kSPS/250-µs design.

## 20. Crosstalk control

Multiplexer crosstalk and charge injection are mitigated by the combination of:

- paired differential switching;
- break-before-make analog multiplexers;
- shared P/N address timing;
- short MUX-to-buffer traces;
- low-capacitance routing;
- ADC resynchronization after address changes;
- explicit discard of unsettled conversions;
- averaging only late settled conversions;
- independent offset calibration per logical channel.

This is materially different from treating every raw ADC conversion immediately after a MUX transition as a valid EEG sample.

## 21. Common-mode and DRL arrangement

The front end may use a center potential (V_{CM}) and a driven-reference/driven-right-leg loop.

A representative DRL implementation measures one or more dedicated common-mode sense electrodes, averages or sums them relative to (V_{CM}), inverts the error with bandwidth limiting, and returns the correction through a large current-limiting resistor to a dedicated body electrode.

Representative relation:

[
V_{DRL}=V_{CM}-G(V_{CMS}-V_{CM})
]

The DRL reduces the common-mode voltage presented to the ADC input chain. It does not convert a lower specified ADC CMRR into a guaranteed >100-dB intrinsic converter CMRR.

Human-connected implementations require independent electrical-safety analysis, battery operation and/or medically appropriate isolation.

## 22. Channel calibration

For each logical channel (c), store:

[
offset_c
]

and a gain correction:

[
g_c
]

Then:

[
x'_c=g_c(x_c-offset_c)
]

A startup calibration may estimate only DC baseline. Precision absolute calibration can instead inject known calibration voltages through a dedicated test path.

---

# PART IV — PACKET AND EDGE ACQUISITION ARCHITECTURE

## 23. Fixed DMA slot

A representative shared-memory/DMA slot is 4096 bytes.

The logical fast packet is:

```text
128-byte header
512-byte EEG int32[128]
512-byte MEG int32[128]
optional fNIRS sub-frame
unused remainder of 4096-byte DMA slot
```

Representative packet sizes:

```text
fast EEG+MEG packet:    1152 bytes
with fNIRS sub-frame:   2456 bytes
DMA slot:               4096 bytes
```

## 24. Header

The fixed header includes:

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

The header is fixed at 128 bytes.

CRC32C uses the Castagnoli polynomial.

The header CRC excludes only the header CRC field itself. The payload CRC covers bytes from `header_bytes` through `packet_bytes-1`.

## 25. Asynchronous fNIRS sub-frame

fNIRS is appended only when a new 20-Hz context sample is available. Fast EEG/MEG packets need not carry a duplicate fNIRS sample every millisecond.

A representative sub-frame contains:

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

This preserves the asynchronous acquisition model down to the hardware packet layer.

---

# PART V — LOW-LATENCY EDGE DEPLOYMENT

## 26. Compute-latency definition

The stated target of less than 5 ms refers to:

> compute and transport latency after the final sample required by the current neural inference window has become available.

It does not include the duration of the neural observation window and does not imply a sub-5-ms hemodynamic response from fNIRS.

## 27. Deployment structure

Representative process separation:

```text
sensor / simulator
    ↓
DMA shared-memory ring
    ↓
preprocessing + inference daemon
    ↓
TensorRT 10.x / ONNX Runtime
    ↓
privacy zeroization
    ↓
AES-256-GCM
    ↓
length-prefixed Unix-domain socket
    ↓
control bridge
    ↓
telemetry / deterministic actions
```

## 28. TensorRT static-shape execution

A representative edge deployment uses static tensor shapes for:

```text
EEG:          [1,128,512]
MEG:          [1,128,512]
MEG geometry: [1,128,6]
fNIRS:        [1,320,20]
```

The ONNX graph is compiled to an FP16 TensorRT engine when supported.

Runtime optimization includes:

- persistent execution context;
- page-locked host buffers;
- persistent device allocations;
- named tensor addresses;
- asynchronous H2D copies;
- `execute_async_v3`;
- asynchronous D2H copies;
- optional CUDA Graph replay where the platform supports stable address replay;
- TensorRT engine/timing cache.

## 29. System service separation

A representative Linux deployment has:

```text
bci-simulator.service
bci-inference.service
bci-bridge.service
bci-dashboard.service
bci-stack.target
```

The inference service may run with a high real-time scheduling priority and locked memory. Lower-priority telemetry/dashboard workloads must not share the highest real-time priority.

## 30. Latency audit

A complete benchmark can inject synthetic packets through the actual shared-memory ring and measure:

```text
DMA ring
→ preprocessing
→ TensorRT/ORT
→ privacy gate
→ AES-GCM
→ Unix socket
→ bridge
```

Reported statistics include:

- P50;
- P99;
- P99.9;
- maximum;
- fraction under 5 ms;
- timestamp jitter;
- saturation throughput in frames per second.

The benchmark reports a PASS only if the measured threshold is achieved. The architecture does not transform a target into an unmeasured performance claim.

---

# PART VI — COMBINED EMBODIMENTS

## 31. Combined embodiment A

A complete embodiment combines:

1. the 128-channel TDM EEG board;
2. OPM-MEG sensor input and geometry metadata;
3. 20-Hz long/short-separation fNIRS;
4. asynchronous NBFM-1 fast/slow fusion;
5. Gaussian motor output;
6. explicit intent gate;
7. fixed-shape zeroization;
8. AES-GCM local transport;
9. deterministic action routing.

## 32. Combined embodiment B

A reduced-cost embodiment omits MEG and uses:

```text
EEG128-TDM
+
fNIRS slow context
+
NBFM-1 compatible fast/slow encoders
+
privacy gate
```

The architecture remains asynchronous.

## 33. Combined embodiment C

A development embodiment replaces real neural hardware with a synthetic producer that emits the identical 4096-byte DMA slot format. The inference, cryptographic, IPC, action and telemetry layers are unchanged.

This permits end-to-end timing and privacy tests without a connected human subject.

## 34. Equivalent implementations

The disclosure is not limited to the literal component brands used in examples.

Equivalent implementations include:

- another 16:1 low-leakage analog MUX in place of CD74HC4067;
- another simultaneous-sampling multi-channel delta-sigma ADC;
- FPGA or another MCU in place of RP2040;
- ChaCha20-Poly1305 in place of AES-256-GCM;
- another local inference accelerator in place of TensorRT;
- another causal neural architecture implementing the disclosed asynchronous fast-query/slow-context relationship.

The invariant technical concepts are the relationships, timing methods, privacy boundary and dataflow described above.

---

# PART VII — PUBLICATION EVIDENCE

## 35. Recommended evidence chain

For a durable publication record:

1. publish this repository publicly;
2. retain the immutable commit identifier;
3. create a cryptographically signed annotated tag;
4. generate SHA-256 hashes of the released files;
5. create a public release from the tag;
6. archive the release in an independent public archival repository;
7. retain any DOI and archival metadata.

A later correction should be made as a new revision rather than rewriting the historical publication record.

## 36. Licensing

Hardware and device firmware in this project are intended to be distributed under:

```text
CERN-OHL-S-2.0
```

Software, inference, privacy, deployment and related project code are intended to be distributed under:

```text
AGPL-3.0-only
```

Third-party components remain under their own terms.

## 37. Safety and medical-use limitation

The disclosure describes research hardware and software.

It does not state that the system is:

- a certified medical device;
- suitable for diagnosis;
- clinically validated;
- electrically safe for human connection without additional engineering;
- a validated free-form thought reader;
- certified for direct control of safety-critical actuators.

Human-connected versions require appropriate isolation, leakage-current control, EMC review, electrical-safety assessment and applicable regulatory work.

---

# 38. Summary of specifically disclosed concepts

For searchability, this publication expressly discloses the following combinations and methods:

1. causal EEG/OPM-MEG fast tokens combined with native-rate slow fNIRS through asynchronous cross-attention;
2. OPM-MEG token conditioning from sensor position and orientation embeddings;
3. a shared neural foundation representation with Gaussian motor, intent-gate and phonemic CTC heads;
4. an intent probability used as a neuro-privacy export gate rather than only a classifier output;
5. fixed-shape zeroization of sensitive speech logits before authenticated encryption;
6. retention of identical serialized speech tensor dimensions whether the gate is open or closed;
7. local-first neural processing with no required raw-neural cloud transport;
8. enumerated, deterministic action identifiers separating probabilistic speech interpretation from execution;
9. 128 differential EEG channels implemented by eight banks of paired 16:1 multiplexing ahead of eight simultaneous differential ADC channels;
10. a 16-position, 250-µs TDM schedule producing 128 × 250-SPS logical channels from a 32-kSPS eight-channel ADC;
11. explicit post-MUX ADC synchronization followed by SINC/filter-settling conversion discard;
12. averaging only late conversions after settling, including the concrete 4-discard/4-retain schedule;
13. asynchronous fNIRS sub-frames carried only when new slow samples exist;
14. a fixed 4096-byte DMA-slot architecture with nanosecond timestamps, channel masks and CRC32C;
15. static-shape FP16 TensorRT execution with persistent pinned/device buffers and optional CUDA Graph replay;
16. a synthetic DMA producer using the identical packet format for end-to-end validation;
17. measurement of the full ring-to-inference-to-privacy-to-socket path using percentile latency and timestamp-jitter metrics.

These teachings may be implemented separately or in combination.

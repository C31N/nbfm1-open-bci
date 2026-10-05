# SPDX-License-Identifier: CERN-OHL-S-2.0
# EEG128-TDM A1 electrical validation plan

## Release rule

No value in this document is a simulated substitute for a physical measurement.
`noise_settling_validation_passed` and `human_connected_use_authorized` remain
false until a fabricated board has been measured with calibrated equipment.

## Required equipment

- isolated battery supply for the DUT;
- calibrated low-noise differential source or precision DAC + attenuator;
- shorting plugs / low-thermal short for all EEG inputs;
- isolated oscilloscope or differential probe;
- signal generator capable of 10 Hz, 50 Hz and 60 Hz common-mode injection;
- precision DMM;
- current meter/electrometer suitable for the intended leakage-current test range;
- fixture that does not connect the patient-side domain to protective earth.

## Test sequence

### 1. Power-domain bring-up

With no electrodes or human connected:

1. current-limit the isolated 5 V source;
2. verify no rail-to-ground short;
3. verify 3V3A and 3V3D;
4. verify RP2040 1.1 V core rail;
5. verify ADS131M08 CAP and REFIN nodes against the selected datasheet mode;
6. verify 8.192 MHz clock amplitude/frequency;
7. verify DRL output remains bounded with CMS inputs at VCM.

Pass criteria must be recorded with the measured values and instrument IDs.

### 2. TDM settling

Drive one selected differential input with a controlled step while adjacent channels
remain at zero differential input. Capture all eight raw ADS131M08 conversions after
each MUX address transition.

For each logical channel, record conversion indices 1..8 after the switch.

The production discard count is acceptable only if the first retained conversion and
all later retained conversions meet the specified settling error. The current firmware
proposal discards conversions 1..4 and averages 5..8; this is a hypothesis to be
validated, not a guaranteed property.

### 3. Input-referred noise

Short each P/N input pair at the connector fixture to the same low-impedance potential
compatible with the input common-mode range. Acquire at least 60 seconds per channel.

Post-process using the same 0.5–100 Hz BCI band definition used by the product
requirement. Report per-channel RMS and the 50th/95th/worst channel values.

Target:

```text
input-referred RMS noise < 1.5 µV RMS, 0.5–100 Hz
```

Do not claim this target until the physical result passes.

### 4. Crosstalk

Inject a known differential sine wave into one logical channel in each MUX bank.
Terminate all other channels identically. Measure the ratio of the driven-channel
amplitude to every non-driven channel after demultiplexing.

Report the worst adjacent-MUX-position and cross-bank coupling.

### 5. Common-mode rejection

Apply the same common-mode sine to P and N of the selected channel while maintaining
a near-zero differential component. Repeat with DRL disabled and enabled.

Calculate:

```text
CMRR_dB = 20 * log10(V_common_mode_rms / V_equivalent_differential_rms)
```

Any statement such as CMRR > 100 dB must be based on the measured system result,
including fixture limitations.

### 6. 50/60 Hz susceptibility

Run separate common-mode tests at 50 Hz and 60 Hz. Record raw performance before any
software notch filtering. A software notch is not a substitute for analog common-mode
performance.

### 7. DRL stability

Sweep representative electrode/contact impedances and capacitive loads. Verify no
sustained oscillation and no unsafe output under open CMS, shorted CMS, and single
component fault cases included in the engineering risk analysis.

### 8. Isolation/leakage

The project does not self-certify IEC 60601-1. Component isolation ratings such as an
ADuM3160 rating do not establish system Means of Patient Protection.

Perform system-level leakage, dielectric, creepage/clearance and single-fault tests
against the applicable standard and intended-use classification using competent
laboratory procedures before any clinical or patient-connected release.

## Evidence files

Store measured evidence outside the raw-neural-data exclusions using anonymized bench
fixture data only:

```text
hardware/eeg128-tdm/validation/
  equipment.json
  power-rails.json
  settling-summary.json
  noise-summary.json
  crosstalk-summary.json
  cmrr-summary.json
  drl-stability.json
  isolation-lab-reference.json
```

Do not commit human EEG recordings to the public repository.

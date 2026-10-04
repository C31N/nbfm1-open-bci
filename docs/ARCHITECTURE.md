<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Architecture Summary

## Fast path

EEG and OPM-MEG are sampled and preprocessed independently of the fNIRS hemodynamic timescale. Causal patch encoders produce aligned fast tokens. OPM-MEG tokens include sensor-pose embeddings.

## Slow context path

fNIRS remains at its native slow update rate. Long-separation and short-separation measurements feed a slow context encoder. Fast tokens cross-attend only to context already available at the inference timestamp.

## Decoder heads

NBFM-1 exposes a Gaussian motor head (`mu`, `log_sigma`), scalar intent gate and time-distributed CTC speech logits.

## Privacy boundary

Speech export requires both local `ARMED` state and an intent threshold. Closed-gate speech tensors are replaced by fixed-shape zero tensors before AEAD encryption. This avoids a message-length side channel.

## Hardware front end

The EEG128-TDM architecture maps eight 16-channel differential banks through sixteen paired analog multiplexers and sixteen buffers into eight simultaneous ADC inputs. At 32 kSPS, each 250 us slot contains enough conversions to discard digital-filter/analog settling and retain later conversions for the logical 250 SPS channel sample.

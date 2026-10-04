<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# EEG128-TDM Hardware Source

Reference architecture:

```text
128 differential logical channels
        -> 8 banks x 16 channels
        -> paired P/N 16:1 MUX per bank
        -> 16 unity buffers
        -> 8 simultaneous differential ADC channels
        -> 32 kSPS conversion stream
        -> settling-aware 16-position demultiplexer
        -> 128 x 250 SPS logical EEG
```

All source design files placed here are licensed under `CERN-OHL-S-2.0`.

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# BCI Device Firmware

Firmware in this tree implements hardware acquisition/bridge functions, including deterministic sensor sampling, CRC32C framing, transport and device-side timing. It is licensed as hardware Source under `CERN-OHL-S-2.0`.

The bridge packet extension uses the common 128-byte BCI packet header plus a compact payload for low-cost test hardware. Production 128-channel acquisition uses the 4096-byte DMA-slot protocol disclosed in `PATENT_DISCLOSURE.md`.

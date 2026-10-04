<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# EEG128-TDM RP2040 Firmware

This firmware drives the Rev A0 EEG128-TDM acquisition concept:

- 8 differential ADC paths;
- 16 shared MUX addresses;
- ADS131M08-class converter at 32 kSPS;
- four conversions discarded after each MUX change;
- four late conversions averaged;
- 128 logical samples per frame at 250 frames/s;
- SPI1 + DMA acquisition;
- per-logical-channel startup offset calibration;
- binary 1152-byte P1/P2 packets with CRC32C.

## RP2040 pins

| Function | GPIO |
|---|---:|
| MUX A0..A3 | 2..5 |
| MUX enable | 6 |
| ADS DOUT / SPI1 RX | 8 |
| ADS CS | 9 |
| ADS SCLK / SPI1 SCK | 10 |
| ADS DIN / SPI1 TX | 11 |
| ADS DRDY | 12 |
| ADS SYNC/RESET | 13 |

The ADS clock is supplied by the board's dedicated 8.192-MHz CMOS oscillator.

## Build

```bash
export PICO_SDK_PATH=/path/to/pico-sdk
mkdir -p build
cd build
cmake ..
cmake --build . -j
```

The firmware is research firmware and does not authorize human-connected use. Follow `docs/SAFETY_COMPLIANCE.md`.

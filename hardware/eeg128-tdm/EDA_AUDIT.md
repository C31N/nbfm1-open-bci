<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# EEG128-TDM A0 EDA Release Audit

## Status

**NOT RELEASED FOR FABRICATION OR HUMAN-CONNECTED USE**

This audit records the machine-observed state and deliberately separates source
availability from fabrication readiness.

## Audit evidence

Latest audited `main` commit before this correction:

```text
6be871c282195cb0d06d140834e3b46dde6e4b56
```

Native KiCad 8 Validation run `37419772760` used KiCad 8.0.9 on 2026-10-06.
Its placement export contains 642 component rows.

## Current machine-observed source state

```text
Generated KiCad connectivity schematic:
  instantiated component symbols: 642
  electrical wire stubs:          1875
  primary schematic parses:       yes
  native netlist export:          yes

Native ERC from the latest main run:
  errors:                         0
  warnings:                       1
  warning class:                  lib_symbol_issues (J9 embedded/library mismatch)

KiCad PCB:
  footprints / placement rows:    642
  copper tracks/segments:         0
  vias:                           0
  copper zones:                   0
  four copper layers declared:    yes

Native PCB DRC:
  unconnected items:              499
  DRC violations:                 1503
  DRC errors:                     897
  DRC warnings:                   606
  schematic-parity items:         0
```

## ERC warning interpretation

The corrected project-bound ERC run `37423367238` reports **0 errors and 1
warning**. The remaining warning states that J9's embedded generated USB-C symbol
(`GEN_20_6661cee1473b`) differs from the current `NBFM1_A0` library version.

This is an EDA generator/library consistency item. It is retained as an open
review item and is not converted into a waiver. Zero ERC errors does not imply
fabrication readiness.

## Schematic completeness

The current schematic is a deterministic connectivity representation derived
from PCB pad/net assignments. It uses generated symbols and is not yet a
manufacturer-symbol/pin-electrical-type reviewed circuit schematic.

Therefore:

```text
schematic_complete = false
```

until component pin semantics, power/reference networks and schematic intent have
been independently verified.

## PCB release blockers

The PCB is still a placement/net-assignment artifact. With no completed copper
routing, vias or zones, 499 unconnected items and 897 DRC errors remain
release-blocking. No Gerber package from this state is suitable for ordering.

## Architecture retained

```text
256 electrode conductors
        |
        v
8 differential banks x 16 logical channels
        |
        v
16 x CD74HC4067
        |
        v
16 low-noise buffer channels
        |
        v
ADS131M08, 8 simultaneous differential channels
        |
        v
32 kSPS conversion stream
        |
        v
RP2040 SPI/DMA
        |
        v
settling discard + averaging
        |
        v
128 logical channels x 250 SPS
```

## Package, grounding and reference review

The ADS131M08IPBSR footprint must be checked against the current TI PBS package
drawing before `footprints_verified=true`.

The logical source uses `AGND` and `DGND` names while the intended layout
uses a continuous low-impedance return plane. Resolve that explicitly without
creating an arbitrary split-plane slot merely to preserve names.

The ADS131M08 REFIN/reference network must be reviewed against the selected
low-noise operating mode and current manufacturer guidance.

## Mandatory fabrication-release evidence

- manufacturer-verified schematic symbols and pin mappings;
- zero release-blocking schematic ERC errors;
- completed routing, vias, power distribution and copper zones;
- zero PCB DRC errors and zero unconnected items;
- schematic/PCB parity review;
- manufacturer land-pattern verification for every footprint;
- final JLCPCB BOM/CPL and assembly-orientation cross-check;
- visual review of Gerber and drill outputs;
- isolated, current-limited bench bring-up;
- measured input-referred noise, TDM settling and crosstalk;
- common-mode/DRL stability and safety measurements;
- explicit release-gate update in `RELEASE_STATUS.json`.

## Prohibited shortcuts

Do not set release flags merely to make CI pass. Do not order the current board.
Do not connect a human subject while any uncontrolled galvanic path exists to
mains-referenced USB, test equipment or bench power.

See `docs/SAFETY_COMPLIANCE.md`.

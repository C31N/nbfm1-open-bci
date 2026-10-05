<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# EEG128-TDM A0 EDA Release Audit

## Status

**NOT RELEASED FOR FABRICATION**

This document records the engineering state of the physical A0 source. It intentionally prevents “source exists” from being mistaken for “board is production-ready”.

## Current machine-observed source state

After deterministic materialization and native KiCad 8.0.9 validation on 2026-10-05:

```text
KiCad schematic:
  instantiated circuit symbols: 640
  electrical wire stubs:         1875
  primary schematic parses:      yes
  native netlist export:         yes

Native ERC report:
  total findings:                3338
  errors:                        183
  warnings:                      3155

KiCad PCB:
  footprints:                    640
  copper tracks/segments:        0
  vias:                          0
  copper zones:                  0
  four copper layers declared:   yes

Native PCB DRC report:
  unconnected errors:            499
  DRC violations:                1503
  DRC errors:                    897
  DRC warnings:                  606
  schematic-parity items:        0
```

The primary schematic is now a KiCad-loadable, deterministic 640-component connectivity schematic generated from the PCB pad/net assignments. It uses conservative generic passive pin types and therefore still requires manufacturer-symbol/pin-type review before `schematic_complete` can be set true.

The PCB remains a placement/net-assignment review artifact. It is not routed.

## A0 architecture retained

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

## ADS131M08 package

Part:

```text
ADS131M08IPBSR
TI package drawing: PBS
pins: 32
body: approximately 5 x 5 mm
lead pitch: 0.50 mm
outer lead span: approximately 7 x 7 mm
```

The project shall verify the footprint against the TI PBS mechanical drawing before setting `footprints_verified=true`.

## Grounding release decision

Current logical sources use `AGND` and `DGND` names while the layout strategy calls for a continuous return plane.

Before copper generation, the designer must resolve this explicitly. Preferred A0 direction:

- continuous low-impedance ground plane;
- analog and digital current control by placement and routing;
- no arbitrary split-plane slot under the ADC;
- decoupling return loops kept local;
- digital clocks kept out of the electrode/MUX region.

## REFIN decision

The internal-reference network shall be explicitly reviewed before A0 fabrication. For low-noise operation, provision for a local 100 nF REFIN capacitor to the converter ground reference should be evaluated against the selected ADS131M08 operating mode and TI guidance.

## Mandatory release evidence

The following evidence must exist before manufacturing export is enabled:

- schematic ERC report;
- PCB DRC report;
- schematic/PCB parity report;
- footprint verification record;
- placement/orientation review;
- Gerber visual review;
- BOM/CPL cross-check;
- routing-complete evidence;
- ground strategy review;
- isolated bench bring-up procedure;
- noise and settling test plan;
- signed `RELEASE_STATUS.json` change.

## Prohibited shortcuts

Do not:

- set release flags true merely to make CI green;
- export/order the current unrouted PCB;
- infer electrical correctness from the presence of pad net names;
- treat distributor footprint drawings as authoritative over manufacturer package drawings;
- connect a human subject while USB, bench supplies, oscilloscopes or other earth-referenced equipment provide an uncontrolled galvanic path.


## Native KiCad 8 audit interpretation

The successful GitHub Actions job means KiCad 8.0.9 can parse the EDA sources and produce native reports. It does **not** mean ERC or DRC are clean.

ERC finding classes include:

- endpoint-off-grid warnings;
- generated-library symbol warnings;
- unconnected-pin errors;
- dangling-label errors.

PCB findings are dominated by the intentionally unrouted design and generated-footprint review state, including unconnected items, clearance/shorting, solder-mask, silkscreen and library-footprint findings.

Therefore `erc_passed=false`, `drc_passed=false`, `routing_completed=false` and `fabrication_release=false` remain mandatory.

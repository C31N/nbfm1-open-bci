<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# EEG128-TDM Hardware Source — Revision A0

## Architecture

```text
128 differential logical EEG channels
= 256 subject/electrode conductors
        |
        v
8 banks x 16 logical channels
        |
        v
16 paired CD74HC4067-class 16:1 multiplexers
        |
        v
16 TLV9064-class unity buffers
        |
        v
ADS131M08-class 8-channel simultaneous delta-sigma ADC
32 kSPS, external 8.192-MHz clock
        |
        v
RP2040 SPI1 + DMA
        |
        v
4 post-switch conversions discarded
4 late conversions averaged
        |
        v
128 logical channels x 250 SPS
```

## Source files

| File | Purpose |
|---|---|
| `design_spec.yaml` | Human-readable electrical/stack-up source of truth |
| `NETLIST.csv` | Detailed endpoint-to-endpoint logical connectivity |
| `BOM.csv` | JLCPCB/LCSC-oriented bill of materials |
| `CPL.csv` | JLCPCB-oriented component placement |
| `eeg128-tdm.kicad_sch` | KiCad 8 schematic/connectivity index |
| `eeg128-tdm.kicad_pcb` | KiCad 8 four-layer A0 placement/net board |
| `eeg128-tdm.kicad_pro` | KiCad project |
| `validate_eda.py` | Source/BOM/CPL/net validation |
| `generate_manufacturing.py` | Fail-closed KiCad 8 ERC/DRC/Gerber/JLCPCB export |
| `RELEASE_STATUS.json` | Machine-readable fabrication/human-use release gates |

## Current fabrication status

**Revision A0 is not released for fabrication.**

The board source currently contains component placement and logical pad-to-net assignment for A0 design review, but the copper routing is not complete, the KiCad schematic is presently a connectivity index rather than a fully instantiated circuit schematic, and generated footprint land patterns have not been independently verified. `RELEASE_STATUS.json` therefore keeps `fabrication_release=false`.

This is intentional. A large human-connected mixed-signal board must not become orderable merely because source files exist.

The manufacturing exporter refuses to run until all release gates are true.

## Validation

Repository-level structural validation:

```bash
python3 hardware/eeg128-tdm/validate_eda.py
```

Release validation additionally requires KiCad CLI 8:

```bash
cd hardware/eeg128-tdm
python3 validate_eda.py --kicad-release-checks
```

After independent routing/footprint/safety review and only after `RELEASE_STATUS.json` is intentionally signed off:

```bash
python3 generate_manufacturing.py
```

The script executes KiCad ERC and PCB DRC before exporting Gerber, drill and position data. Any failed release gate or KiCad violation stops the export.

## Four-layer intent

```text
L1  F.Cu   analog inputs, MUX/buffer/ADC and short local digital routes
L2  In1.Cu continuous return plane; analog/digital domains managed by placement/current paths
L3  In2.Cu 3V3A / 3V3D / VCM distribution
L4  B.Cu   high-speed digital, USB and controller-side routing
```

Do not create arbitrary AGND/DGND moat cuts that force return currents to detour. Domain control is primarily by placement/routing, with the ground-domain connection deliberately reviewed at the ADC/power boundary.

## Safety

This is research hardware, not IEC 60601-certified equipment.

No human-connected use is authorized by this repository revision. Follow `docs/SAFETY_COMPLIANCE.md`. In particular, a subject-connected analog domain must not have an uncontrolled galvanic path to mains-referenced equipment.

## License

Hardware source is covered by `CERN-OHL-S-2.0`.


## Package and grounding audit

### ADS131M08IPBSR

Use the TI **PBS** mechanical drawing as the authoritative footprint reference. The package has a nominal 5 mm square body with 0.50 mm lead pitch and approximately 7 mm overall lead span. Distributor summaries can describe these dimensions differently; release review must use the manufacturer drawing.

### Ground plane

The current logical source uses separate `AGND` and `DGND` names while the intended PCB strategy calls for a continuous return plane. This conflict must be resolved before routing release. Do not introduce an arbitrary split-plane slot solely to preserve naming.

### Internal reference

The selected low-noise reference network must be reviewed explicitly before A0 fabrication. The present logical netlist records `ADC_REFIN` as unpopulated; for EEG noise optimization, provision for local REFIN filtering must be evaluated against TI guidance and the chosen converter mode.

See `EDA_AUDIT.md` and `RELEASE_STATUS.json`.

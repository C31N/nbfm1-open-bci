# A2 controlled routing specification

## Layer assignment

- L1 / F.Cu: sensitive electrode and MUX input routing, ADC local analog, QSPI/clock and short digital escapes. All high-speed routing references the uninterrupted L2 plane.
- L2 / In1.Cu: one continuous AGND return plane. DGND and ISO_GND are intentionally merged into the local AGND net; the design does not split the ground plane.
- L3 / In2.Cu: non-overlapping power islands for 3V3A, 3V3D and 5V_ISO. VREG_1V1 remains a short local routed rail because cutting a separate island under the RP2040 would fragment the 3V3D reference/distribution region.
- L4 / B.Cu: TDM/control crossings, low-criticality digital routing and the AGND perimeter guard/stitch ring. Long electrode-input runs are avoided on L4 because L3 is a split power layer.

The physical stackup is the controlled 1.6 mm JLC3313 model in apply_board_constraints.py.

## Net classes

| Class | Nets | Width | Clearance | Via |
| --- | --- | ---: | ---: | ---: |
| TDM_ANALOG | CH*, BANK*, ADC*_P/N | 0.15 mm | 0.15 mm | 0.60/0.30 mm |
| ANALOG_REF | VCM, REFIN, ADS_CAP, DRL, CMS | 0.25 mm | 0.20 mm | 0.60/0.30 mm |
| QSPI_FAST | QSPI_CLK, QSPI_SD0..3, QSPI_SS | 0.20 mm target, 0.18 mm minimum | 0.15 mm | 0.60/0.30 mm |
| POWER | 3V3A, 3V3D, 5V_ISO, VREG_1V1 | 0.40 mm target, 0.30 mm minimum | 0.20 mm | 0.65/0.30 mm |
| USB_FS | USB_DP/DM and isolated-side DP/DM | 0.20 mm target | 0.15 mm | 0.60/0.30 mm |
| Default | remaining control/digital | 0.15 mm | 0.15 mm | 0.60/0.30 mm |

QSPI stays on L1 where possible, uses no vias where a clean escape is available, and is kept short. Engineering routing targets are <= 25 mm per QSPI net and <= 5 mm max-to-min bus skew; final impedance must be confirmed against the PCB fabricator's actual production stackup rather than inferred solely from nominal FR-4 values.

## Routing order

1. Preserve the L2 AGND plane and L3 power islands; only F.Cu and B.Cu are autoroutable.
2. Route QSPI/clock and the ADC local digital interface before dense TDM routing.
3. Route each 16-channel differential bank monotonically from connector -> series/bias network -> CD74HC4067, preserving P/N locality and avoiding blind straight-line cross-bank routes.
4. Route buffered bank outputs to the TLV9064/ADS131M08 analog core.
5. Route remaining controls, references and local power escapes.
6. Refill zones after every imported SES routing round.
7. Run native KiCad 8 DRC and score candidates as (violation_errors, unconnected, warnings). Only 0/0/0 may be promoted.

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Component and Assembly Source Audit — 2026-10-05

This document records identity checks for the A0 BOM. It is not a purchasing guarantee: stock, price, lifecycle and JLCPCB basic/extended classification can change at any time.

## Critical active components

| Ref | Manufacturer part | LCSC | Package used in BOM | Audit |
|---|---|---:|---|---|
| U1-U16 | TI CD74HC4067M96 | C496123 | SOIC-24-300mil | identity/package confirmed |
| U17-U20 | TI TLV9064IPWR | C779410 | TSSOP-14 | identity confirmed |
| U21 | TI ADS131M08IPBSR | C2862610 | TQFP-32, 5 mm body, 0.50 mm pitch | identity confirmed; verify against TI PBS drawing |
| U22 | TI OPA4171AIPWR | C529553 | TSSOP-14 | identity/package confirmed |
| U23 | Raspberry Pi RP2040 | C2040 | LQFN-56 7x7 | identity/package confirmed |
| U24 | TI TPS7A2033PDBVR | C2862740 | SOT-23-5 | identity/package confirmed |
| U25 | Diodes AP2112K-3.3TRG1 | C51118 | SOT-25-5 | identity/package confirmed |
| U26 | Winbond W25Q16JVSSIQ | C82317 | SOIC-8-208mil | identity/package confirmed |
| U27 | YXC OT2JI-111-8.192M | C7425393 | SMD3225-4P | identity/package confirmed |
| J1-J8 | HDGC 0.5K-QX-32PWB | C2919488 | 32P, 0.5 mm, right-angle FPC | identity/package confirmed |
| J9 | Korean Hroparts TYPE-C-31-M-12 | C165948 | USB-C 16P SMD | identity confirmed |
| J10 | JST S4B-PH-SM4-TB(LF)(SN) | C265102 | PH 4P, 2 mm, right angle | identity confirmed |
| J11 | JST S2B-PH-SM4-TB(LF)(SN) | C295747 | PH 2P, 2 mm, right angle | identity confirmed |
| Y1 | YXC X322512MSB4SI | C9002 | SMD3225-4P | identity/package confirmed |

## High-count input resistors

| Function | Manufacturer part | LCSC | Quantity/board | Audit |
|---|---|---:|---:|---|
| 10 MΩ electrode bias | Vishay RCS060310M0FKEA | C2092526 | 256 | identity/value/package confirmed |
| 100 kΩ series protection | UNI-ROYAL TC0325F1003T5F | C2989131 | 256 | identity/value/package confirmed |

These two line items dominate passive count and materially affect board cost and placement density.

## Manufacturer/distributor source hierarchy

Release verification shall use this precedence:

1. manufacturer datasheet and mechanical package drawing;
2. manufacturer product/package page;
3. JLCPCB/LCSC assembly record;
4. project BOM/CPL.

If a distributor description conflicts with a manufacturer mechanical drawing, the manufacturer drawing controls the footprint decision.

## Live-source references

- ADS131M08: https://www.ti.com/product/ADS131M08
- ADS131M08 datasheet: https://www.ti.com/lit/ds/symlink/ads131m08.pdf
- C2862610: https://www.lcsc.com/product-image/C2862610.html
- C496123: https://www.lcsc.com/product-detail/C496123.html
- C779410: https://www.lcsc.com/product-image/C779410.html
- C2040: https://www.lcsc.com/product-detail/C2040.html
- C82317: https://www.lcsc.com/product-detail/C82317.html
- C2092526: https://www.lcsc.com/product-detail/C2092526.html
- C2989131: https://www.lcsc.com/product-detail/C2989131.html
- C7425393: https://www.lcsc.com/product-detail/Oscillators_Yangxing-Tech-OT2JI-111-8-192M_C7425393.html
- C2919488: https://www.lcsc.com/product-detail/C2919488.html

## Cost target

The **< EUR 50 component-BOM target remains a target, not a guaranteed purchase quote**. The largest cost risks are:

- 512 high-count electrode resistors;
- 16 analog MUXes;
- the ADS131M08;
- electrode connectors;
- assembly surcharges for extended parts.

A manufacturing release must use a dated JLCPCB/LCSC quote at the intended production quantity. PCB fabrication, stencil, assembly setup, feeder/extended-part charges, shipping, VAT, isolation hardware and the electrode cap are not included in the component-BOM target unless a release explicitly says otherwise.

## 2026-10-15 source recheck

`COMPONENT_VERIFICATION_2026-10-15.json` binds the unchanged BOM/CPL hashes and
records 642 centroid/rotation matches in the 143er PCB's CAD frame. The four
requested active identities (RP2040, ADS131M08IPBSR, CD74HC4067M96, TLV9064IPWR)
and all 13 passive BOM line identities were rechecked against their primary
LCSC listings. All fitted passives in this revision are 0603; no unreviewed
0402 substitution was introduced. The existing 27-line BOM expands to 642
placements. These checks do not constitute JLCPCB import/assembly signoff.

`audit_bom_quote.py` evaluates a complete supplied EUR quote against the BOM,
rejecting missing parts, MPN mismatch, stale/future dates, invalid price tiers
or insufficient stock. It distinguishes component allocation from MOQ-rounded
purchase cost. Its JSON input requires `date`, `currency="EUR"`, and `parts`
indexed by LCSC ID; each part contains `mpn`, `unit_price_eur`, `multiple`,
`minimum`, `price_tier_minimum` and `stock`. No fabricated quote is bundled.
The <EUR 50 target has not been marked as a verified total without that quote.

JLCPCB's official source-format references:
https://jlcpcb.com/help/article/bill-of-materials-for-pcb-assembly and
https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly . Final
placement coordinates are regenerated from native KiCad output after release
gates, including its Gerber-compatible coordinate frame, with an explicit
JLC header/side/rotation conversion. Existing development coordinates are not
blindly copied into a final order. Independent visual orientation review is
still required.

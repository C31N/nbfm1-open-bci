<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# NBFM-1 engineering, license, patent and medical-safety audit — 2026-10-21

This is an engineering assessment and evidence index, not a patent opinion,
regulatory determination, IEC test certificate, or release authorization.

## Actual repositories and deliverables

- \`hardware/eeg128-tdm/eeg128-tdm.kicad_sch\`, \`generate_schematic.py\`,
  \`eeg128-tdm.kicad_pcb\`, and \`design_spec.yaml\` exist. They are research
  sources, not a finalized production build.
- Eight banks of 16 differential EEG channels use **16 CD74HC4067** (a P
  and N mux per bank), four TLV9064, one ADS131M08 and one RP2040.
  Do not treat "eight MUX ICs" or "two ADS131M08" as the current
  bill of materials without a reviewed schematic redesign.
- \`BOM.csv\` and \`CPL.csv\` already exist as non-released engineering source
  datasets with recorded LCSC IDs; neither proves present-day sourcing,
  pick-and-place acceptance or the under-EUR-100 assembled-price objective.
  \`audit_bom_quote.py\` requires a dated vendor quote.
- \`generate_manufacturing.py\` contains a fail-closed export path and
  \`--assert-blocked\`. Do not run the export path during this audit.
- The primary PCB is historic/pre-route, while the 139-airwire checkpoint is
  the SHA-pinned ZIP \`engineering/block2-ch019-electrode-closed139.zip\`.
  The 139 checkpoint is engineering-only, not a production candidate.

## Exact blocking gates

- Accepted routing: **139 open connections**, not 0; the proposed 136 result
  has not been natively qualified. \`routing_completed=false\`.
- \`fabrication_release=false\` and \`human_connected_use_authorized=false\`.
- The CH025 B.Cu bypass is blocked by protected VCM. In1.Cu AGND is excluded.
  F.Cu probes of four retained via pairs and three margins per pair returned
  no complete route. New UUID inventory is read-only.
- A generated CH022/CH025 combined route remains unverified.
- Exact **native** L3 directional polygon differences must both be empty:
  loss = 0.0 mm² and gain = 0.0 mm², not merely net area 0.
- Only after full neighbor restitution, no protected-UUID regression,
  KiCad 8.0.9 fill/DRC (0 errors, 0 warnings), schematic parity, identical
  replay, and 136 airwires may an engineering candidate be accepted.
  **None of these engineering partial gates authorizes fabrication.**

## Compliance assessment and boundary conditions

1. CI already runs \`ruff check\`, \`pytest\`, \`reuse lint\`,
   \`scripts/check_zero_debt.py\`, \`cffconvert --validate\`, the release
   manifest regeneration/verification and the manufacturing-block assertion.
   A green CI is not proof of circuit safety, interoperability, market
   availability or infringement freedom.
2. REUSE machine-readable labels (SPDX, \`.reuse/dep5\` and license texts)
   are a metadata-compliance test. They do not establish ownership of
   every contribution or resolve third-party vendor licensing automatically.
3. CERN-OHL-S-2.0 covers separately identified hardware/firmware sources;
   AGPL-3.0-only covers separately identified application and repository
   automation. Parallel distribution is not a legal determination of
   relicensing compatibility for files copied, linked, or combined across
   the boundary. Complete the actual derivative-work, notice, source
   disclosure, patent-license and third-party provenance review before
   redistribution. Consult qualified counsel for any contested combination.
4. \`PATENT_DISCLOSURE.md\` already describes relevant architectures with
   prior-art limits. A public release with stable commit, SHA-256, independently
   archived date/DOI and enabling details improves evidentiary value. It does
   **not** retroactively defeat earlier priority rights, establish
   freedom-to-operate or prevent all future related patent grants.
5. \`docs/SAFETY_COMPLIANCE.md\` already correctly rejects a generic
   FDA Class II/III exemption and unconditional liability waivers.
   Research-only labeling does not replace medical-device classification.
   ADuM3160 supports low/full-speed USB, not 480-Mbit/s high-speed USB,
   and alone is not an IEC 60601 Means of Patient Protection.
6. No person-connected operation, mains charging while attached,
   non-isolated bench gear or clinical claim is authorized. Require
   independent risk management, leakage-current and insulation testing,
   electrical/EMC review, and ethics/regulatory determination before
   a human-connected study. Use controlled isolated dummy loads for
   preclinical circuit bring-up.

## Primary law, specification and component references

- USA: https://uscode.house.gov/us/usc/119-121/t35/s102/
- EPC Art. 54: https://www.epo.org/en/legal/epc/2020/a54.html
- EPO online prior art: https://www.epo.org/en/legal/guidelines-epc/2026/g_iv_7_5.html
- EPO enabling disclosure: https://www.epo.org/en/legal/guidelines-epc/2026/g_iv_2.html
- REUSE 3.0: https://reuse.software/spec-3.0/
- CERN OHL: https://cern-ohl.web.cern.ch/
- EU MDR: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex:32017R0745
- FDA device classification: https://www.fda.gov/medical-devices/overview-device-regulation/classify-your-medical-device
- Analog Devices ADuM3160: https://www.analog.com/media/en/technical-documentation/data-sheets/ADuM3160.pdf

## Operational status

No Gerber, drill, BOM or CPL was generated or exported by this audit.
No routing checkpoint or medical clearance is promoted by this document.

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# CH019-P B.Cu/F.Cu blockers and selective bypass candidates

Source is a SHA-pinned unadopted joint-137 KiCad 8 diagnostic.
The verified engineering checkpoint remains 139 unconnected items.
No physical layout edits were introduced into the repository.

## Native copper obstacle inventory

The read-only obstacle survey from GitHub Actions
[39116770330](https://github.com/C31N/nbfm1-open-bci/actions/runs/39116770330)
measures disconnected CH019-P via-area B.Cu components at 9.009803 mm
separation; the corresponding F.Cu gap is 8.083590 mm.

Specific selectable B.Cu blocking segments near the direct corridor:
- CH019_N_MUX: `cbef8349-505c-5ce2-812b-299cf1e09ca5`,
  `0832ca70-347c-5b2d-b8d9-c8fff7096f8a`,
  `5515b1db-5793-53c0-a4f6-afb38886c550`,
  `de1cd9d0-a8ca-5513-b75d-fd8a2b88e503`.
- CH021_N_ELECTRODE:
  `56ab8fc8-eb17-4770-86ac-acdb41bcedf3`.
- VCM `f97de490-edba-5ed5-a5e1-1e32b0330049`: its isolated
  diagnostic deletion reduces the gap to 1.351917 mm. This is
  **not** a permissible copper edit. Overlapping long reference
  segments on X=34.75 mm from Y=13 to Y=36.4 and the horizontal
  VCM network make a single-segment removal electrically
  unsafe and incomplete. No VCM copper may be moved by this probe.

Front-layer interference near direct crossing includes selectable
CH026_P_MUX segments starting
`82a1c65b-3d26-4d1f-be55-3962e9e1f1db` (33.575,25.2) →
(33.575,31.95), and CH027_P_MUX
`bba58354-dd4e-400c-9bc1-df854fac72d8`
(35.4572,31.9291) → (35.4572,27.8903).
These are diagnostic candidates, **not** known DRC-clean routes.

## Scoped selective cross-layer trials

Separate ephemeral native KiCad copies attempt bounded single,
four-segment CH026, two-segment CH027, and joint combinations, preserving
all CH018_N_MUX and VCM tracks and all unrelated pads/vias.
Each trial proposes CH024_P_MUX across R49.1/U3.23/R305.2,
then the CH019-P existing-via bridge between (39.915/45.15) and
(32.70/23.40) with any legal cross-layer transitions.
Every removed segment must be individually rerouted and CH022-N
fully restored. If that full proposal succeeds, native DRC,
L3 power loss/gain and connectivity regressions are measured
before any independent replay is considered.

Zero acceptable diagnostic cases until complete CH019+CH024+CH022
and all displaced neighbors are physically connected, no DRC
violations/warnings, exact L3 0.0 mm² gain/loss, unchanged
zone contours, schematic parity, 70 hardware protection tests
and independent byte-identical replay. The diagnostic always
sets accepted=false/routing_completed=false/fabrication_release=false.
No Gerber, Drill, CPL or BOM.

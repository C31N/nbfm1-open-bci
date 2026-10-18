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

## Five F.Cu unlock models: full results

GitHub Actions run
[39117189731](https://github.com/C31N/nbfm1-open-bci/actions/runs/39117189731)
completed all five native-hosted *model-only* searches successfully.

| Selective F.Cu removal | CH024-P three pads proposed | CH019-P retained-via 3-layer path |
| --- | --- | --- |
| CH026-P single segment | yes | blocked |
| CH026-P four-segment trunk | yes | blocked |
| CH027-P two-segment pair | yes | blocked |
| CH026-P plus CH027-P | yes | blocked |
| CH026-P plus CH027-P plus MUX_EN | yes | blocked |

No geometrical CH019-P bridge was found. Hence none of these
models reached neighbor restitution or native candidate DRC/replay.
The test *job* conclusion `success` means the diagnostic ran,
not that routing succeeded. No new 136 unconnected engineering
checkpoint was formed.

The long VCM reference tracks and all CH018-N copper were
intentionally left intact. A separate strict upper-bound study
now probes whether even temporary relaxation of **all eligible
pad-safe local signal copper** permits a CH019-P path under the same
A2 and L3-power gates. Such a study never retains cut nets or
constitutes a valid candidate.

## Upper-bound existence and exact copper conflict minimization

The native KiCad-hosted local upper-bound run
[39117565729](https://github.com/C31N/nbfm1-open-bci/actions/runs/39117565729)
found **the same** combined geometric CH019-P B.Cu/F.Cu and
three-pad CH024-P path in both orders, with 36 signal tracks
temporarily omitted (including the three original CH019-P In2
trunk objects and two CH022-N F.Cu objects).
Both VCM and CH018-N remained byte-for-byte unaffected in board
geometry. This is only an upper bound: displaced signals were
**not** restored, no native candidate DRC was qualified and
accepted=false. The proposed CH019-P link length is about
76.776 mm (too long to treat as SI-qualified without analysis).

The refined same-input model
[39117992075](https://github.com/C31N/nbfm1-open-bci/actions/runs/39117992075)
identified 11 exact *foreign copper* conflicts for that fixed path:

- CH022_N_ELECTRODE (F.Cu, two):
  `a0a692e9-e4d4-4be1-b224-b0aa00b02815`,
  `e81c7523-9205-40fe-bcd4-374c112022ef`.
- BANK1_P_MUX_OUT (B.Cu, one):
  `7d5653c6-8ba9-40b9-afd5-266ed0ef4353`.
- CH019_N_MUX (B.Cu, two):
  `0832ca70-347c-5b2d-b8d9-c8fff7096f8a`,
  `cbef8349-505c-5ce2-812b-299cf1e09ca5`.
- CH026_P_MUX (F.Cu, five):
  `33bd3c0c-2cec-4190-a52a-baa0606f516c`,
  `6549b817-a68e-45d5-96b9-7cbabd2eacf3`,
  `82a1c65b-3d26-4d1f-be55-3962e9e1f1db`,
  `8becd9ff-318f-4161-8602-37776971617d`,
  `d3abb5e2-a155-421a-8a73-4d1ef441d576`.
- MUX_EN (F.Cu, one):
  `8b6baf5a-aa8f-4eea-9681-7cdc57183397`.

Three removed CH019-P In2 segments remain a distinct restoration
design concern. These 11 UUIDs describe only collisions against
the **fixed upper-bound** CH024/CH019 geometrical proposal and
cannot be assumed to be the globally minimal physical reroute.

## Eleven-conflict selective outcome

GitHub Actions
[39118254794](https://github.com/C31N/nbfm1-open-bci/actions/runs/39118254794):
the 11-conflict experiment geometrically proposes **both**
all three CH024-P pads and the existing-via CH019-P multilayer
bridge with unmodified VCM/CH018. A control releasing the
eight CH019 bridge conflicts but leaving the MUX_EN CH024
obstacle failed to route CH019.

The 11-conflict experiment fails complete neighbor restitution:
first unresolved `CH022_N_ELECTRODE` segment
`a0a692e9-e4d4-4be1-b224-b0aa00b02815`.
**No 136 checkpoint can be accepted.**

Further diagnostic variants attempt pad-connected CH022 topology
in different orders instead of mandating regeneration of its
obsolete copper piece. These remain unadopted until all affected
neighbors are complete, DRC=0/0, no power gain/loss at exact
0.0 mm², A2 0.25 mm and 0.505 mm L3 keepouts,
native schematic parity, 70 guards and independent byte-identical
replay. Gerber, NC-Drill, CPL and BOM exports are forbidden.

## CH022-N pad-topology follow-up — exact 11-neighbor candidate

GitHub Actions
[39118605334](https://github.com/C31N/nbfm1-open-bci/actions/runs/39118605334)
executed all three models on disposable KiCad 8 boards:

| Variant | CH022 pad route | CH024 3-pad | CH019 existing-via bridge | Blocker |
| --- | --- | --- | --- | --- |
| CH022 pad-driven before CH024 | geometrically proposed | blocked | not attempted | U3.23 CH024 target |
| CH022 pad-driven after both targets | blocked | proposed | proposed | R302.1 CH022 target |
| CH022 after targets, discard obsolete CH019 In2 pieces | blocked | proposed | proposed | R302.1 CH022 target |

The alternative pad-driven sequence therefore does **not**
solve the joint-net restitution. The common unresolved geometry
is the competition between the CH022_N_ELECTRODE connection to
**R302.1** and the CH024_P_MUX approach at **U3.23**.
These failures occur *before* complete restoration of the other
displaced MUX/control tracks.

Next investigation must selectively reconfigure the shared
CH022/R302 approach with a guaranteed retained J2.23/source
escape and plan the CH024 U3.23 ingress simultaneously,
rather than reroute one of the nets through the other's only
free resource. The 76.776 mm CH019 diagnostic remains
long and unqualified for SI/length matching.

No native candidate with full restoration exists; there are no
qualified DRC numbers or byte-identical replay for promotion.
Keep 139 confirmed and 137 diagnostic only.
`accepted=false`, `routing_completed=false`,
`fabrication_release=false`. No Gerber, Drill, CPL or BOM.

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: CH029-P electrode closure, 142 → 141

## Accepted engineering checkpoint

Parent commit: `89331c96db1c266da794c974ff5049e5cd28900c`.
Parent: `block2-ch018n-closed142.zip`, SHA-256
`d084ed667e46e542b6dfe780e01f4f735e12f507e27492fc2226f9f194acd1d7`.

| Native KiCad 8.0.9 check | Result |
| --- | --- |
| Geometric DRC errors / warnings | 0 / 0 |
| Open connections | 141 (75 MUX, 66 electrode/RC) |
| Open Block-2 connections | 8 MUX, 3 electrode/RC |
| Diagnostic schematic parity findings | 0 |
| Additional filled L3 power loss / gain | exactly 0 / 0 mm² |
| Regressed nets | none |
| Footprints, zone outlines, project rules | unchanged |
| Independently replayed PCB / ZIP | byte-identical |

Accepted archive: `block2-ch029-electrode-closed141.zip`.
SHA-256: `a69aadf1bdd2436aadd7b9ae80e2796f1b5937b816389b44a11582685b2699a1`.
PCB SHA-256: `a5a961817e2c7b61f673114b6def0ce14ca33445f6f128a53075a0f7a7ec438e`.
The archive contains only the PCB, project and design rules. It is an engineering checkpoint, not a manufacturing release.

## Copper changes

CH029_P_ELECTRODE now connects R315.1 (41.150 / 26.000 mm) to
J2.14 (39.250 / 7.600 mm), using F.Cu endpoint necks and an In2.Cu
(L3) trunk. Its two new through vias are at (41.314750 / 24.999900 mm)
and (38.081263 / 9.027757 mm), diameter 0.6 mm, drill 0.3 mm.
Every new via has trace support on two copper layers before the apply process writes the board.

The source corridor is opened by replacing the CH025_P_MUX local F.Cu/B.Cu
trunk with a complete In2.Cu connection between its existing vias at
(38.755 / 24.999999 mm) and (41.855 / 16.500 mm). Six original objects
are removed, including the redundant via at (41.155 / 24.999999 mm).
There are 102 new copper objects across the two nets, including the two
electrode vias. The replacement uses no new CH025-P vias. Both L3 routes
remain above the power-zone boundary; the native filled-polygon comparison
proves exact zero power change. VCM at R38 stays at X = 39.650 mm.

`followup-2026-10-15-electrode141/ch029e141-recipe.json` binds every removed
and added copper object and every baseline project member. The replay
allows only CH025_P_MUX and CH029_P_ELECTRODE and rejects L2 mutations,
wrong baseline bytes, modified recipes and incomplete vias before writing.

## CH018-P: explored, electrically closed, rejected by the power gate

CH018_N_MUX remains closed. CH018_P_MUX remains **open in the accepted board**.
The search first opened an F.Cu goal neck by detouring MUX_S1 below the U3
pads, then replaced the left VCM rail with a complete F.Cu/B.Cu bridge.
After removal of dangling stubs and an explicit VCM feed reconnection,
this intermediate board passed 0/0/142, parity zero and exact zero power change.
A counterfactual removal of the whole VCM feed increased the open count and
was discarded. None of these CH018 experiments enters the accepted archive.

A connected-free-space graph found a complete two-via CH018-P route using
F.Cu/B.Cu and vias at (33.637364 / 19.491039 mm) and
(29.742500 / 38.564150 mm). Native DRC and parity passed at 141, but fresh
zone fill changed the L3 power polygons. Five further target-via positions
also passed connectivity and DRC but failed the exact power comparison:

| Target via X / Y mm | L3 power loss mm² |
| --- | --- |
| 29.7425 / 38.56415 | 4.128740874676033e-08 |
| 29.75 / 38.50 | 4.699130448778885e-08 |
| 29.75 / 38.40 | 2.8259999696690064e-08 |
| 29.70 / 38.50 | 7.939230377004291e-08 |
| 29.80 / 38.50 | 5.9136886983743395e-08 |
| 29.75 / 38.70 | 4.6801880706169845e-08 |

These differences are small but nonzero; the gate applies no rounding or
numerical tolerance. Combining the 29.75 / 38.40 candidate with the accepted
electrode closure produced 0/0/140 and parity zero, but retained the same
nonzero power loss. That combined candidate is also rejected.
The result motivates a CH018-P endpoint corridor outside the filled-power
region, or a replacement through already present vias; merely moving a new
via within an existing antipad window has not met the gate.

## Remaining electrode analysis

Exact F.Cu free-component / via-center intersections on the 142 parent
showed no complete source-and-target pair for CH019_N, CH021_N or CH025_P.
CH029-P had a usable target window but required the accepted source-corridor
replacement. The first attempt to move the CH025-P via to 40.500 / 24.600 mm
caused six native DRC errors against adjacent CH027_P_MUX and
CH030_P_ELECTRODE copper and was rejected. The complete trunk replacement
above removes those collisions.

The three remaining Block-2 electrode nets are CH019_N_ELECTRODE,
CH021_N_ELECTRODE and CH025_P_ELECTRODE. A CH027-P B.Cu dogleg model at the
CH025-P electrode target still leaves zero usable via-window area; it was
not promoted or described as a validated route. Next work must open an
actual endpoint corridor, preserving the neighboring complete nets and the
hard L3 power keepout.

## Replay, diagnostics and gates

Run with native KiCad 8.0.9, its matching pcbnew module, NumPy and Shapely:

```sh
/usr/bin/python3 -m unittest discover -s hardware/eeg128-tdm -p test_ch029_electrode_replay.py -v
/usr/bin/python3 hardware/eeg128-tdm/replay_ch029_electrode.py --output-dir /tmp/ch029-reviewed-replay
```

Apply runs in a separate child process and exits before fresh fill/DRC.
Schematic parity runs in a separate native CLI invocation. The independently
replayed output is compared against the reviewed PCB and deterministic ZIP
hashes. CI repeats this new replay in addition to the existing 143→142 replay
and checks both output directories for forbidden manufacturing exports.

Successful native JSON, plans, exact electrode-window analysis and the
updated inventory are under `followup-2026-10-15-electrode141/`.
`block2-142-followup-rejected-diagnostics.zip` contains raw native DRC,
parity and geometry diagnostics for the rejected CH018-P/combined probes,
the rejected via move and clean intermediate routes. A clean intermediate
route is not itself an adopted closure. `probe-summary.json` identifies the
individual diagnostic runs. These diagnostics carry no fabrication authority.

The historical 142 report and archive remain intact. Its manifest bindings
for the mutable current-status pointer and the extended native workflow are
refreshed; the immutable 142 PCB/archive hashes do not change.

`routing_completed=false` and `fabrication_release=false` remain enforced.
No Gerber, NC drill, CPL or BOM is generated. The primary pre-route board and
its historical release status are not promoted by this engineering checkpoint.

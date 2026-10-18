<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2 CH024-P coordinated restitution, permutation search

Basis: immutable diagnostic joint-137 (CH018-P and CH021-N closed) with
S0 and CH025-P preparation, archive SHA256
`a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041`.
Mainline checkpoint stays 139 unconnected, and no PCB is changed by this
search. All trials are model-only, accepted=false, routing_completed=false,
fabrication_release=false.

The previous 3-layer model found an R49.1→U3.23 path and the
R49.1→R305.2 third terminal on both CH018-N and CH019-P options,
but complete CH022-N plus In2-neighbor restitution failed. CH024-P-first
left CH022-N at J2.23 open, and CH022-N-first prevented the In2
neighbor's U3/U4 escape.

The new search examines six permutations of CH024-P, CH022-N
and either CH018-N or CH019-P. It writes model JSON after each trial
to enable postmortem inspection of failed native runs. The shared
CH031-N corridor remains gated until its own full restitution is found.
No independent four-target promotion is attempted.

Safety: full 0.505 mm L3 plane-outline exclusion for new through
vias and In2.Cu centreline, conservative 0.25 mm A2 edge,
no source modifications, no Gerber/NC-Drill/BOM/CPL.
A complete proposal remains unaccepted until native refill,
0 DRC errors/warnings, 136 unconnected, zero net regressions,
exact 0 mm² L3 loss AND gain, schematic parity, all 70 legacy
hardware protection tests and independent byteidentical PCB+ZIP replay.

## Native model results: all CH024-P path orders

Results from `block2-ch024p-full-order-diagnostic`, GitHub Actions run
[39109787395](https://github.com/C31N/nbfm1-open-bci/actions/runs/39109787395).
All twelve deterministic three-layer permutations were tested on the pinned
diagnostic joint-137 fixture. No complete restitution or native PCB candidate
was produced. The matched CH024-P R49.1→U3.23 and R49.1→R305.2 geometry
is only a model, **not** a native DRC-validated or SI-qualified route.

| Removed In2 neighbor | Order (P=CH024-P, E=CH022-N, X=removed MUX) | Proposed before failure | Failing terminal |
| --- | --- | --- | --- |
| CH018_N_MUX | P-E-X | P | E: J2.23 |
| CH018_N_MUX | P-X-E | P | X: U4.7 |
| CH018_N_MUX | E-P-X | E | P: U3.23 |
| CH018_N_MUX | E-X-P | E | X: U4.7 |
| CH018_N_MUX | X-P-E | none | X: U4.7 |
| CH018_N_MUX | X-E-P | none | X: U4.7 |
| CH019_P_MUX | P-E-X | P | E: J2.23 |
| CH019_P_MUX | P-X-E | P | X: U3.6 |
| CH019_P_MUX | E-P-X | E | P: U3.23 |
| CH019_P_MUX | E-X-P | E | X: U3.6 |
| CH019_P_MUX | X-P-E | none | X: U3.6 |
| CH019_P_MUX | X-E-P | none | X: U3.6 |

Four model-only trials fully proposed all three CH024-P pads, but zero
fully restored both displaced neighbors. No 136 candidate exists.

## Shared CH031-N corridor

Read-only model: GitHub Actions
[39110109121](https://github.com/C31N/nbfm1-open-bci/actions/runs/39110109121).
CH031_N_MUX including R320.2 was geometrically proposed on F.Cu.
Its reroute then blocked CH020_P_MUX at U3.5; no four-target closure.

Three targeted CH031 routing-avoidance models were then executed on
[39110767717](https://github.com/C31N/nbfm1-open-bci/actions/runs/39110767717).
The protected nominal via patches were:
`(48.1259, 33.8786)` mm and `(46.3236, 27.4653)` mm.
Each was reserved individually or together with a 0.70-mm obstacle
on all selected signal layers for CH031-N only. Each model
reconnected CH031-N but failed CH020_P_MUX at U3.5.
No shared-target route was accepted.

## Next route-engineering requirement

The sequence-only strategy with wholesale removal of CH022-N and
CH018-N/CH019-P is insufficient. Subsequent experiments must
preserve completed F.Cu/B.Cu escapes and replace only the interfering
In2.Cu trunk and local CH022-N copper, with native connectivity
confirmation for all retained components. Existing hole-free L3 power
outlines and 0.505-mm centreline restrictions remain hard blockers.
Every candidate also requires full zero-error DRC, 0 schematic parity,
zero net regressions, exact 0.0 mm² L3 loss *and* gain, strict
0.25-mm board-edge clearance, 70 protection tests and a separately
implemented byteidentical PCB+ZIP replay before any candidate may
claim accepted=true. No manufacturing exports are permitted.

This record is diagnostic only; the confirmed 139 checkpoint and
released board geometry remain unchanged.

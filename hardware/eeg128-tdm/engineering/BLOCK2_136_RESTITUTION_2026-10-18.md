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

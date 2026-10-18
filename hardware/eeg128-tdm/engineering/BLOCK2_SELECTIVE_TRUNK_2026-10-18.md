<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2 selective local trunk-replacement experiment

Parent `147faf629c5c5a958b234f214fd4000c24f36887`.
Confirmed engineering checkpoint 139, unadopted joint diagnostic 137.
The pinned diagnostic baseline is checked by ZIP and PCB SHA256 before loading.

This program deliberately **does not** remove entire CH022_N_ELECTRODE,
CH018_N_MUX, or CH019_P_MUX. It tests only nearby copper segments
that intersect a reviewed three-pad CH024-P model path:
- CH022-N: a bounded set of F.Cu segments, excluding pad and via escapes
  (1.0 mm pad guard and 0.65 mm same-net via guard).
- CH018-N or CH019-P: In2.Cu segments only. All F.Cu/B.Cu trunks, pads
  and existing vias remain untouched.
- All removed segments are held as live SWIG objects and their endpoints
  are queued for individual rerouting after the three-terminal CH024-P path.

Guides are pinned from the prior 12-order model, GitHub Actions
[39109787395](https://github.com/C31N/nbfm1-open-bci/actions/runs/39109787395).
The third required pad is R305.2 at (42.75, 13.0) mm.
The complete physical re-route must also include R49.1 and U3.23.

Strict keepouts belong to `escape_mesh_505.py`: all new via
locations and In2.Cu copper avoid the 0.505 mm L3-plane outline exclusion;
0.25 mm A2 edge is mandatory. This code makes no manufacturing exports.

When a *model-only* route reaches all three CH024 pads and all selected
neighbor segment ends, a temporary KiCad PCB is inspected with a fresh
native DRC and compared against its baseline for unconnected-regressions,
zone-outline differences, L3-power loss and gain. Such an artifact is
not promoted; it remains accepted=false regardless of native numbers.
A genuinely accepted 136 engineering checkpoint would additionally
require independent byte-identical replay, 70 safeguards, schematic parity,
unmodified non-scoped copper, zero DRC errors/warnings, 0 net regressions,
and exactly 0.0 mm² power loss/gain. Both release flags remain false.

CH031_N shared corridor remains priority two after CH024-P selective
restoration. Prior reserves (top1/top2/both) failed to free U3.5 for
CH020_P; the next search must preserve CH031-N and locally reroute the
F.Cu obstacle, rather than merely reserve holes.

This is research diagnostics only. Mainline checkpoint and manufacturer
release remain untouched.

## First native model findings

The initial 4-segment-per-net budget found two CH022-N F.Cu objects
`a0a692e9-e4d4-4be1-b224-b0aa00b02815` and
`e81c7523-9205-40fe-bcd4-374c112022ef`.
CH018-N trial was blocked while routing CH024-P to U3.23.
CH019-P trial geometrically reached the complete CH024-P three-pad
network, but the remaining CH019-P segment
`752f59d7-57f9-46ee-b7cc-b45beae0a553`
(start 41.75/31.58, end 43.25/33.08 on In2.Cu)
could not be restored. These are native KiCad-hosted model observations,
not a DRC-approved full candidate.

Follow-up experiments vary segment budget (4 or 8) and try both
target-first and neighbors-first with guide-corridor reservations.
The outer routed copper escapes remain immutable.

## Expanded selective-native modeling: restored connectivity still blocked

GitHub Actions run
[39112282388](https://github.com/C31N/nbfm1-open-bci/actions/runs/39112282388)
tested both CH018-N and CH019-P neighbors with cut budgets 4 and 8,
and both target-first and neighbors-first-with-reservations. The
diagnostic JSON was saved by each worker despite a post-processing
shell quoting error; therefore the job's overall result is a failure,
not a successful workflow qualification.

The eight actual model outcomes are:

| Neighbor | Budget | Order | Native-hosted geometry status |
| --- | --- | --- | --- |
| CH018_N_MUX | 4 | target-first | CH024-P U3.23 unreachable |
| CH018_N_MUX | 8 | target-first | CH024-P U3.23 unreachable |
| CH018_N_MUX | 4 | neighbors-first-reserved | CH018-N segment `b5afe736-387f-4c3d-8365-286cac5f8f4d` unrestored |
| CH018_N_MUX | 8 | neighbors-first-reserved | same segment unrestored |
| CH019_P_MUX | 4 | target-first | CH024-P geometrically reaches 3 pads; CH019-P segment `752f59d7-57f9-46ee-b7cc-b45beae0a553` unrestored |
| CH019_P_MUX | 8 | target-first | same segment unrestored |
| CH019_P_MUX | 4 | neighbors-first-reserved | CH019-P segment `752f59d7-57f9-46ee-b7cc-b45beae0a553` unrestored |
| CH019_P_MUX | 8 | neighbors-first-reserved | same segment unrestored |

The guide-conflict filter selected only four CH018-side or five
CH019-side local segments even when its maximum increased to eight;
the unchanged results are therefore expected. All F.Cu/B.Cu MUX
escapes and all pad-adjacent existing vias remained on the model
board. No complete three-pad and full-neighbor-restoration candidate
exists, so no 136 checkpoint or native replay was attempted.

## CH031-N baseline copper inventory and interpretation

Native model run
[39112693751](https://github.com/C31N/nbfm1-open-bci/actions/runs/39112693751)
enumerated the protected CH031-N copper in the pinned joint-137
baseline: eight copper segments, all on F.Cu. No corresponding
CH031-N via or In2.Cu segment was present. The nearest F.Cu
segment to CH020-P endpoint U3.5 is 5.870715 mm away.
The examined pad-safe local track-radius search (1.2 mm around
U3.5 or the two prior target patches) yielded zero selectable
segments under the 0.85-mm pad and 0.65-mm via guards.

The previous full-net-removal experiment could free distant geometric
corridor resources, but the current old CH031-N copper does *not*
lie directly beside U3.5. The actual obstruction must be diagnosed
from connected copper components, keepouts and the geometry of
the **replacement** path, not assumed to be the baseline CH031
segment at the target. Do not alter pad-adjacent CH031-N copper
merely to force this search.

## Release and quality controls

No native PCB file was committed on this branch; it carries
only scoped probe code, guard tests, read-only Action workflows,
reference path points and a SHA-256 publication manifest.
The 139 baseline remains the confirmed checkpoint. Joint 137
is a diagnostic only (accepted=false).

Acceptance of a new engineering 136 requires complete CH024-P
physical connectivity and restitution of *every* touched neighbor,
a new native 8.0.9 DRC with zero violations/warnings and 136
unconnected items, zero net regressions and schematic-parity findings,
0.0 mm² L3 power **loss and gain**, unchanged rules, zone outlines
and protected nets, 0.505-mm via/In2.Cu exclusion, 0.25-mm A2
edge clearance, all existing hardware guards (at least 70) and
independent byte-identical PCB and archive replay. The diagnosis
here satisfies none of those full promotion conditions.
`accepted=false`, `routing_completed=false`,
`fabrication_release=false`. Never export Gerber, NC-Drill,
CPL or BOM in these tests.

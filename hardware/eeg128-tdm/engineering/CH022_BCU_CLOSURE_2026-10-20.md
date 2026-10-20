<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# CH022-N guarded B.Cu trunk closure, 20 October 2026

Baseline: SHA-pinned unadopted 137-geometry archive; immutable
engineering checkpoint: **139 airwires** at parent 9f5bc5f6.

The retained CH022 F.Cu via endpoints after opening the proven
CH026-P E3C4 segment are approximately (38.6868645,16.9487341)
and (44.0260496,9.2087679) mm. Both F.Cu escapes and legal vias
are seeded before CH024-P and CH019-P are routed. CH026-P's
displaced segment is geometrically restored *early*, retaining its
same-net pad/via escapes.

The first additional experiment clears only interior B.Cu signal
segments within 0, 0.6, 1.2 or 2.0 mm of the direct via-to-via
axis. Candidate segmentation is verified against native net/layer
identity, with >=1.0 mm pad and >=0.65 mm existing via escape
guards. CH022-N, CH026-P, CH024-P, CH019-P, CH018-N, VCM,
and power nets cannot be touched. J2.23 original same-net copper
must remain byte-identical.

If CH022 B.Cu geometrical proposal succeeds, every eligible
displaced neighbor must be restored and independent native
KiCad 8.0.9 DRC and zone power comparison undertaken, with
0.0 mm2 L3 gain AND loss, 0 errors and warnings, schematic parity,
zero connectivity regressions and independent byte-identical PCB+
archive replay before any 136 checkpoint adoption.

No manufacturing exports of any kind; always accepted=false,
routing_completed=false, fabrication_release=false in these probes.

## Protected B.Cu straight-corridor experiments (native KiCad)

Run [39448180473](https://github.com/C31N/nbfm1-open-bci/actions/runs/39448180473)
executed KiCad 8.0.9 with corridor selections 0.0, 0.6,
1.2, and 2.0 mm. All four jobs completed successfully **as
diagnostics**, but every outcome was
`ch022_interleaved_BCu_blocked`. Existing CH026-P early
restitution, CH024-P three-pad geometry and CH019-P retained-via
bridge remain proposed, but none achieved CH022 end-to-end copper.

| Corridor | Interior B.Cu signal segments removed | Result |
| --- | --- | --- |
| 0.0 mm | 0 | CH022 B.Cu path blocked |
| 0.6 mm | 0 | CH022 B.Cu path blocked |
| 1.2 mm | 2 | CH022 B.Cu path blocked |
| 2.0 mm | 2 | CH022 B.Cu path blocked |

The only additional pad/via-safe B.Cu candidates are from
`CH017_N_ELECTRODE`:
- `d04ea811-0e34-5d4f-8320-88b489821ec6`:
  (37.547194,16.955987) → (37.867747,18.785154) mm.
- `4aa24dbb-0a8d-5bc6-afe9-6f73d285e716`:
  (37.584236,20.819041) → (37.547194,16.955987) mm.

Neither segment has been permanently moved. The removable-neighbor
model retains the entire CH018-N, CH026-P, CH024-P, CH019-P, VCM,
CH022-N and J2.23 escape copper. Any displacement requires full
CH017-N restitution; this was not reached because the CH022
bridge failed beforehand.

## B.Cu and In2.Cu source-of-blockage diagnostic

A read-only native investigation separately measures B.Cu/In2
free-component connectivity, effective minimum gap, available legal
new-via centers and all relevant foreign-track UUIDs within 3 mm
of the direct CH022 via-to-via path. It compares the untouched
trunk against the two-segment CH017-N release. Only the complete
native JSON report can authorize a concrete next rerouting target;
job success alone never represents a valid 136 candidate.

All candidates remain `accepted=false`,
`routing_completed=false`, `fabrication_release=false`.
No production files or primary board edits.

## Native residual B.Cu/In2 copper-barrier evidence

[Actions 39449538473](https://github.com/C31N/nbfm1-open-bci/actions/runs/39449538473)
completed both 0.0 mm and 2.0 mm B.Cu-selection models and
saved per-net UUID copper inventories from the blocked complete
CH024-P/CH019-P geometry.

- B.Cu via-anchor free regions do **not** connect; gap
  `2.396210 mm`, unchanged by the two CH017-N temporary cuts.
- In2.Cu free regions do **not** connect under the complete
  0.505 mm power-outline guard; gap `2.237707 mm`.
- Native inventory confirms a board-wide AGND B.Cu track
  UUID `20fed9e0-4919-489f-9b11-33dab311a133`
  from (5.8,11.0) to (194.2,11.0) mm, directly
  intersecting the straight CH022 via-to-via corridor.
  **It is not eligible for displacement or a gap cut.**
- Unchanged analog VCM B.Cu tracks
  `3f39ff0c-4c8e-445d-8e0d-ea5f28918940` and
  `45c65a13-251f-4cbd-b03c-81e52f7f8ff6`
  at X=39.45 mm, plus CH028-P, CH030-P and CH031-P
  electrode tracks, further constrain entry regions.
- Nearby In2 copper includes CH025-P, CH029-P and CH020-N
  electrodes; it cannot be crossed in violation of
  the L3 power outline.

The *next viable hypothesis* is an F.Cu crossing of the AGND
B.Cu barrier with only legal new-via centers on both sides,
or coordinated fully restituted signal rerouting. Existing
native evidence does not yet demonstrate a legal complete
three-layer CH022 route.

**Acceptance remains blocked.** No new candidate has passed
zero-native-DRC, zero-connectivity-regression, exact 0.0 mm²
L3 gain/loss, schematic parity and byte-identical independent
replay jointly; no 136 checkpoint is claimed or committed.

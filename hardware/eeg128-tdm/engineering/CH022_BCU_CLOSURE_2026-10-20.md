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

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Routing completion and manufacturing boundary — 2026-10-15

**Verified continuation: 142 open connections.** CH018_N_MUX is closed by the
reviewed CH019-N trunk exchange, with native 0 errors / 0 warnings / 0 parity
findings and exactly zero additional filled-L3-power loss and gain. CH018_P_MUX
remains open. The immutable 143 checkpoint below remains the replay input;
the current engineering artifact and queue are identified in
[`engineering/current-routing-status.json`](engineering/current-routing-status.json).
See [`BLOCK2_SOURCE_FOLLOWUP_2026-10-15_CH018142.md`](engineering/BLOCK2_SOURCE_FOLLOWUP_2026-10-15_CH018142.md)
for exact neighbor changes, rejected probes and the independent replay proof.

## Authoritative input

Use `engineering/block2-electrode-closed143.zip`, SHA-256
`e8d60a9835aea686af2d34d9e0e31b3a948b8c7dd2caae81c2c24786e4a3a8e1`.
Its PCB SHA-256 is
`497b588e580caf24766d5d60e9753def8dfe10ad3495b75faf5cd3fdd6276f24`.
The primary pre-route PCB and older `latest-pcb.zip` are different artifacts.
Neither may silently replace this engineering baseline.

KiCad 8.0.9: 143 open connections, 0 geometric DRC violations/warnings,
0 diagnostic parity findings, 0 additional L3-power displacement. Native parity
uses the PCB-derived diagnostic schematic; independent schematic/LVS approval
is still required for manufacture. `routing_completed` and
`fabrication_release` remain false. This plan does not claim 143→0 completion.

## CH018 source and target must both close

R38 source is 38.250/26.000 mm. Preserve the approved VCM via at
39.650/26.000 mm. The legal isolated source point at approximately 38.750/26.000
is not an escape: do not save a new via without two-layer copper support and
a complete connection. Retain `via_dangling` and clearance checks.

The recorded clean diagnostic reroute moves CH025-P to 38.500/24.999999,
replaces its local L4 connection by L3 copper in already empty power space,
and shifts the CH019-N L4 stem to X=37.950. It gives 0/0/143 with zero power
loss, but its 1.966515 mm² source component remains bounded. It is not accepted
working copper. See `engineering/followup-2026-10-15-corridor143/` for exact
UUID-bound deltas and a byte-identical diagnostic replay.

The next controlled F.Cu/B.Cu search must include the entire closed contour,
not only the nearest three segments: CH025-P via 38.155/22.399999,
CH027_P_ELECTRODE via 38.750/21.779999, CH017_N_ELECTRODE L4 stem and VCM
also bound the region. First identify the connected free-space component at
0.15-mm signal width/clearance and 0.20-mm clearance to power/reference nets.
Then reserve a continuous CH018 centerline from source neck to a genuinely
reachable external component. Reroute the limiting neighboring net between
its existing connected endpoints around that reserved corridor. Prefer a
trace-only F/L4 substitution; relocating a via additionally requires checking
its drill and copper on every traversed layer and the complete filled L3 map.
Reject a contour change that only enlarges the pocket.

At the other end, U4.7 is 41.135/58.150 mm. The previously rejected target via
at 41.135/59.650 cuts L3 power. Reopen the target F.Cu neck by controlled
neighbor copper changes before routing a trunk. A source-only corridor does
not close CH018. Treat CH018_P and CH018_N as a pair, review final path lengths,
via symmetry, coupling and return paths; summed network copper is not skew.

## Queue for the remaining 143 connections

`engineering/followup-2026-10-15/inventory143.json` is the exact net queue.
There are 76 MUX and 67 electrode/RC connections; Block 2 has nine and four.

1. Probe CH018 source/target contour substitutions without adding copper.
2. Revisit CH019_N_ELECTRODE, CH021_N_ELECTRODE, CH025_P_ELECTRODE and
   CH029_P_ELECTRODE sequentially on the newest accepted baseline. Use L1/L3
   in existing power-free regions and a 0.20-mm hard clearance to baseline
   filled power copper. Restore the baseline immediately after rejection.
3. Close complete Block-2 MUX pairs CH018, CH020 and CH024 before considering
   isolated CH028_N, CH029_N and CH030_N. Inspect both endpoint access regions
   before running long A* trunk searches; bounded search failure is not proof
   of impossibility. Do not relax foreign-pad or drill clearances.
4. Process Blocks 3–8 using the exact inventory, ranked by reachable endpoint
   components, then pair completeness, then shortest conflict-free trunk.
   Review remaining Block-1 electrode connections by the same policy. Each
   closure reduces only its own reported open-net count, with no regressions.

Keep L2 as the ground reference. Preserve all power/clock/control closures.
Wider local redesign requires a separate exact copper allowlist and new
endpoint/geometry review. Never weaken the additions-only protection in
`replay_mux147_routes.py` to accept an arbitrary neighbor mutation.

## Every accepted cut

Hash-bind PCB/PRO/DRU and the recipe; apply in a process that exits; refill
zones and run native DRC in a fresh process; run parity independently; compare
per-net connectivity, unchanged protected objects, footprints, rules and
zone outlines. Require zero DRC findings, zero warnings and exactly zero
additional filled-L3-power loss. Reject incomplete vias before writing.
Replay accepted copper independently and require identical PCB/archive hashes.
Update inventory only from the native report, never from a router estimate.
The existing 147→143 replay chain remains unchanged.

## Manufacturing gate

`generate_manufacturing.py` checks explicit boolean release approvals before
invoking any CLI or creating an output directory. Strings such as `"false"`
are rejected. A reviewed `manufacturing_source_sha256` mapping must cover PCB,
SCH, PRO, DRU, BOM, CPL and NETLIST; `baseline_l3_power_loss_mm2` must be numeric
zero. Missing approval evidence blocks export. No approval flags were changed.

On a frozen copy it requires KiCad 8, exactly four copper layers, deterministic
zone refill, fresh native DRC with no violations, no warnings, no unconnected
items and no parity items. A separate `audit_release_power.py` process compares
filled power polygons against the hash-bound 143er reference and rejects any
nonzero loss. Export uses the reviewed snapshot, not a live
mutable source board. Only after those checks can four copper Gerbers,
mask/silkscreen/outline layers, Excellon drill and assembly files be generated.
Existing output directories are never deleted or overwritten.

Current safe check, which does not export:

```bash
python3 hardware/eeg128-tdm/generate_manufacturing.py --assert-blocked
```

The existing BOM/CPL remain development source data. Their 642 references,
centroids and rotations match the engineering PCB in its CAD coordinate frame.
JLCPCB import orientation, Gerber/placement origin and independent visual
assembly review remain release gates. Do not submit these source CSVs as a
manufacturing release while 143 connections remain open.

## Follow-up: verified 141-airwire checkpoint (2026-10-15)

CH029_P_ELECTRODE is closed by a complete CH025_P_MUX neighbor replacement;
native KiCad 8.0.9 confirms 0 errors, 0 warnings, 141 open connections,
zero parity findings and exactly unchanged filled L3 power. CH018_P_MUX
remains open: electrically successful probes fail the exact power gate.
See [the 141 follow-up](engineering/BLOCK2_SOURCE_FOLLOWUP_2026-10-15_ELECTRODE141.md)
and `engineering/current-routing-status.json` for the authoritative checkpoint.
Release flags remain false; no manufacturing exports are authorized.

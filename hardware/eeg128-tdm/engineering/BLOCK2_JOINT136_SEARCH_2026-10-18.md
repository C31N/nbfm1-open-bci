<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2 coordinated 136 search — diagnostics only

Branch: `codex/block2-joint136-search-2026-10-18`. Baseline: confirmed engineering 139, unadopted joint 137.
This branch does not promote or replace either checkpoint. The new probe reads
the existing 137 + S0/CH025-P preparation archive, SHA-256
`a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041`,
and checks contained PCB SHA-256
`cac02064d9926676f6368536c4c104cb36295961333de6074e65fa1fa60a814c`.

## Coordinated models

- CH024_P_MUX with both CH022_N_ELECTRODE and CH018_N_MUX
  hypothetically released and planned for complete restitution.
- CH024_P_MUX with both CH022_N_ELECTRODE and CH019_P_MUX
  hypothetically released and planned for complete restitution.
- CH031_N_MUX first, then the shared CH020_P_MUX, CH028_N_MUX,
  CH029_N_MUX, CH030_N_MUX targets. No independent target is promoted.
- CH020_N_MUX and CH024_N_MUX retain analysis-only status until their
  electrode and F.Cu/B.Cu neighbor corridors are qualified.

The input PCB is never modified. All removals and route additions exist only
in memory; JSON is the only output. New In2.Cu and via positions must honor
0.505 mm from the full L3-power outline; the 0.25 mm A2 board edge remains
protected. The existing 3-layer proposal engine enforces these keepouts.

The native workflow executes six new guard tests and a window-only pass
(`--skip-mesh`). Optional full mesh modeling requires Shapely 2.1 in a
KiCad-8 Python environment. It remains `model_only=true`,
`accepted=false`, `routing_completed=false`, `fabrication_release=false`.
No hardware/fabrication files are produced.

A future 136 engineering acceptance must have exactly 136 unconnected items,
zero native DRC violations and warnings, target and all displaced neighbors
fully reconnected, no network regressions, zero parity findings, exactly
0.0 mm² L3 copper loss *and* gain, all 0.505 mm/0.25 mm geometry checks,
unmodified footprints/zone outlines/rules, byte-identical independent PCB
and ZIP replay, and all 70 hardware safety guards. Remaining SI, length and
hardware-validation blockers keep both release flags false. There is **no
qualified 136 candidate yet**.

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# CH019-P protected B.Cu/F.Cu obstacle inventory – October 18, 2026

Base: `a328414691275cdc9e4cc12a854dc59a6ac499cf`
from `codex/ch019p-return-136-2026-10-18`. Engineering
checkpoint 139 remains immutable. The joint-137 diagnostic baseline
must match archive and PCB SHA256 before any geometry is computed.

Prior complete B.Cu bridges between (39.915,45.15) and (32.70,23.40)
failed. The present job ranks **specific foreign copper segment UUIDs**
near the corridor on B.Cu/F.Cu and excludes all CH018_N_MUX,
CH022_N_ELECTRODE, pad-adjacent (1 mm), via-adjacent (0.65 mm),
and non-track objects from any selectable set. All found hard
obstacles, including vias and component pads, are reported separately.

No actual routing change is made. Individual read-only sensitivity
trials remove precisely one eligible copper object **in memory** and
restore the identical held SWIG object in finally. The goal is to
identify which concrete displaced-neighbor topology is worth testing
for fully restored connectivity and DRC.

All model results are accepted=false, no Gerber, NC-Drill, CPL or BOM.
A subsequent candidate can be promoted only with complete CH024-P,
CH019-P and CH022-N connectivity, every neighbor restored, 0 KiCad
violations/warnings, exactly 0.0 mm² L3 gain and loss, 0.505 mm
new-via/In2 exclusion, A2 0.25 mm board-edge clearance, 70 guard
tests, parity, and independent byte-identical replay. No change
to release flags is permitted by this diagnostic.

# A2 engineering routing checkpoint

This board is a continuation candidate, not the primary manufacturing PCB. Fabrication release remains blocked. The primary PCB and RELEASE_STATUS are unchanged.

The checkpoint starts from round 6 of Actions run 37465707022, artifact 11419324691. That candidate had 450 unconnected items, zero geometric errors and one dangling-track warning.

Changes to the candidate:

- Removed the two segments of the dangling BANK0_N_BUFFER stub, without increasing the open count.
- Added 21 short local F.Cu connections (at most 3 mm). Tracks use the existing routing widths; candidate connections that failed native DRC were rejected.
- Added 97 short F.Cu-to-inner-plane escapes, each with a 0.65/0.30 mm through via. Via centers are outside all component pad bounding boxes expanded by the via radius plus 0.20 mm. Ground tracks are 0.15 mm, power tracks 0.40 mm. Only positions already inside the corresponding filled ground/power plane were considered. Candidate groups that failed native DRC were rejected completely; no clearance, width, thermal or warning rule was relaxed.

Native KiCad 8.0.9 checks after zone refill, using the unchanged project and custom rules with all severities and all track errors:

| Stage | Geometric errors | Warnings | Open connections |
| --- | ---: | ---: | ---: |
| Original primary board | 0 | 0 | 499 |
| Source round 6 | 0 | 1 | 450 |
| Stub cleanup | 0 | 0 | 450 |
| Short local connections | 0 | 0 | 429 |
| Plane escapes | 0 | 0 | 335 |
| One CI continuation round | 0 | 0 | 330 |
| Targeted MUX/signal paths | 0 | 0 | 321 |
| Additional signal path | 0 | 0 | 320 |
| Router candidate (rejected by analog-layer review) | 0 | 0 | 314 |
| Accepted continuation after analog restoration | 0 | 0 | 316 |

Remaining groups: 64 ground/power connections, 22 MUX controls, 230 signal connections. These are real release blockers.

`STATUS.json` records provenance and PCB/project/rule hashes. A complete primary-board geometry/connectivity signature permits harmless KiCad footprint reordering, UUID regeneration and numeric serialization rounding; actual primary routing, placement, zone or net changes invalidate the checkpoint. `drc-checkpoint.json` is the full native report. All 642 footprint bodies, geometry and pin assignments match the primary PCB, allowing only generated UUID changes and 10 nm numeric serialization rounding; BOM/CPL and all critical pin/footprint checks pass.

The A2 workflow verifies the checkpoint, footprint identity and native baseline before routing. A push starts one bounded routing round (15-minute router limit plus 16-minute subprocess limit), rather than repeating six rounds from scratch. Manual dispatch can select 1–6 rounds. Existing strict-zero primary promotion remains in force. A successful workflow execution is not a completed PCB route.

Recheck from the repository root:

```sh
/usr/bin/python3 hardware/eeg128-tdm/verify_routing_checkpoint.py \
  --source hardware/eeg128-tdm/eeg128-tdm.kicad_pcb \
  --checkpoint hardware/eeg128-tdm/routing/checkpoint.kicad_pcb \
  --metadata hardware/eeg128-tdm/routing/STATUS.json
/usr/bin/python3 hardware/eeg128-tdm/verify_hardware_identity.py \
  --pcb hardware/eeg128-tdm/routing/checkpoint.kicad_pcb
```

For native DRC, copy the checkpoint and unchanged .kicad_pro/.kicad_dru to one directory under the same filename stem, refill zones with fill_zones.py, then run `kicad-cli pcb drc --format json --severity-all --all-track-errors`.

## Targeted signal continuation

The updated checkpoint starts from artifact 11422017642 of run 37481327819. A local obstacle search produced native-clean routes for eight MUX connections and two CH signal connections (330 to 320 opens). Long CH signal routing stays on F.Cu; proposed B.Cu crossings were limited to 2 mm total per signal route. MUX controls may use B.Cu with two 0.65/0.30 mm transition vias. All paths were rejected as complete groups if native DRC reported any geometric error or warning. Footprints, pin mappings, project rules and primary manufacturing PCB were preserved. Intermediate accepted path vectors are recorded in targeted-signal-paths.json.

A pinned FreeRouting 2.4.1 round from the 320-open intermediate candidate used one pass, a 120-second limit, fanout/automatic neckdown/optimizer disabled, and strict_drc=true. Its imported and refilled SES passed native DRC with 314 opens and zero geometric violations/warnings, but introduced 10.10 mm and 30.56 mm of new B.Cu routing on CH110_N_MUX and CH113_N_MUX. These two nets were restored exactly from the native-clean 320-open input, yielding 316 opens with zero geometric violations/warnings. The 314-open candidate was rejected by the analog-layer review. router-validation.json records the router manifest and native result. The source DSN loaded with 21 router warnings; native verification after import was therefore required rather than trusting its internal score.

FreeRouting still reports hundreds of internal clearance violations on the native-clean board. Their cause remains unproven; the strict_drc=false comparison was not completed and no result from that comparison was accepted. The production workflow retains strict_drc=true and strict-zero native promotion. Dense CH signal routing remains the main blocker; completed workflow executions must not be reported as routing completion.

The 2026-10-06 continuation run 37491021373 reached 311 opens with zero geometric violations/warnings, but the ignore_net_classes option did not prevent four long B.Cu analog routes; the layer gate rejected the round and retained 316 opens. The exact settings propagation failure is not established. The workflow now constrains TDM_ANALOG directly in each exported DSN circuit scope with (use_layer "F.Cu"), which the pinned router reads into active net-class trace layers. Other net classes, all net/pin assignments, existing copper and native design rules are preserved. The optimizer remains disabled. After every SES import it checks the change in B.Cu length for CH/BANK/ADC differential nets against round 0. More than 2 mm of added B.Cu per analog net rejects that candidate, regardless of its DRC/connectivity score; the previous accepted board is restored. Native geometric and strict-zero promotion gates remain unchanged. check_analog_layer_policy.py was checked against the real rejected 314-open board and the accepted 316-open restoration.

Run 37496972920 (commit 069f667) validated the DSN F.Cu analog restriction: 316 → 313 native unconnected items, zero geometric violations/warnings, no added B.Cu analog length. Artifact 11429011974 is the saved engineering checkpoint; strict-zero release promotion remains blocked.

Run 37500557398 produced 312 native opens with one MUX_EN track_dangling warning; no new bottom analog length. The accepted checkpoint stayed at 313. Continuation now removes only unlocked segment UUIDs explicitly identified by native track_dangling warnings, refills zones and reruns full native DRC. Cleanup is reverted if connectivity or errors worsen, or warnings do not improve. Before-cleanup boards/reports remain in artifacts. Native confirmation of this cleanup is pending the next run.

Run 37503135045 removed one native dangling segment but native DRC still reported a dangling warning after refill. The single-step cleanup was reverted and the accepted board remains at 313 opens. Cleanup now performs at most eight native-report-driven removal/refill/DRC steps, retaining each intermediate report. The aggregate rollback guard still requires fewer warnings and no connectivity/error regression before accepting the cleanup.

Run 37505590814 again retained the clean 313-open baseline. The pre-rollback cleanup result was not retained, so the exact rollback cause is unresolved. A dedicated native diagnostic reads pinned artifact run 37505590814, saves every cleanup board/report and prints complete violation details; it does not reroute or promote a PCB.

Diagnostic run 37509238110 artifact 11435265071 closed the cleanup investigation. Eight native-report-driven removals on the dead-end MUX_EN branch (six tracks and two vias) yielded 312 opens, zero geometric violations/warnings and no added analog B.Cu length. Step 8 board/report are the accepted engineering checkpoint. No manufacturing/release promotion occurred.

Run 37511237149 saved 310 native opens, zero geometric violations/warnings and no added analog B.Cu routing. The validated engineering checkpoint continues from 310; strict-zero release promotion remains blocked.

Run 37513734597 (commit 7fc21f1), artifact 11436384031, reduced native opens from 310 to 308 after guarded dangling cleanup. The accepted board has zero geometric violations/warnings and no added analog B.Cu length. Artifact SHA-256 and checkpoint/report hashes are recorded in STATUS.json. All 642 footprints and BOM/CPL identity checks pass. The validated engineering checkpoint continues from 308; strict-zero release promotion remains blocked.

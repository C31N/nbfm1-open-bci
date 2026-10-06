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

Remaining groups: 65 ground/power connections, 34 MUX controls, 236 signal connections. These are real release blockers.

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

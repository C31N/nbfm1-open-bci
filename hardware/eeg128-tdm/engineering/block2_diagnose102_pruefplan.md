<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Diagnose #102 – MUX_S2-Zeugenabgleich und CH030-Ausweichroute

**Status: NOCH NICHT NATIV AUSGEFÜHRT.** Es fehlen hier die #101-Original-PCB/State-/DRC-Dateien und das native KiCad 8.0.9.

1. Alle #101-Originalartefakte in `/workspace/scratch/diagnose101/` einlesen, SHA-256 der Dateien sichern. Die **fünf** Tiefe-18-Routen, **57** offenen Zustände und die beiden abgebrochenen vierten ROI-Aufträge brauchen ihre vollständigen nativen Koordinaten-/Objektexporte. Keine fehlenden Pfade aus Zahlen erraten.
2. Post-201-Cut-Scratch-Board byteweise gegen `19d5cfbd…703dc` und vollständiges 201er-Schnittinventar prüfen; U3/13, U3/14, U3/15, MUX_EN-Tracks, U4-/Target-Escapes, CH027, CH038_P_MUX, VCM, Block 1, In1.Cu und L3 unverändert; **0 neue Vias**.
3. Abgelehnten CH028-Vorschlag Nr. 2 isoliert wiederholen. **Warm- und CLI-Kandidat müssen identische PCB-/Projekt-/DRU-Bytes und Zonenzustand haben.** In KiCad 8.0.9 Positionen, DRC-Typ, Layer, Netze, Spur-/Pad-/Via-UUID und Layerpaar vergleichen. B.Cu-Track vs. Via wird nicht wegen ähnlicher Koordinaten weggewunken. Bei Widerspruch: `BLOCKED_ATTRIBUTION_MISMATCH`, nicht requeue.
4. Die zwei vierten Prüfaufträge mit bisheriger unveränderter 4-s-Grenze als `INDETERMINATE_TIMEOUT` behandeln, nicht verlängern und nicht als geometrisch erfolgreich ausgeben.
5. CH030 bei Nr. 4 aus **vollständiger bestätigter Routenhistorie**, zuletzt (47,265 / 37,510) mm, fortsetzen. Alle drei Netzpaare, F.Cu-Kupfer-Clearance >= 0,150 mm, Pitch >= 0,300 mm, ROI, Keepouts, Masken und Zielankernähe prüfen. Der gemeldete Restweg war um 0,175940 mm schlechter, nicht besser. Blocker mit Koordinate, Netz, Layer, echter UUID und Defizit dokumentieren.
6. Kandidat Nr. 2 mit den **zwei** sauber bestätigten CH028-Pfaden, Kandidat Nr. 4 mit CH029/CH030, unter denselben Expansions- und Zeitbudgets getrennt fortsetzen; keine neuen Vias, keine 201er-Restitution.
7. **Harte Abschluss-Gates:** 3/3 nachgewiesene vollständige Source-to-Target-F.Cu-Routen vor jeder separaten Restitutionsprüfung, vollständiger nativer DRC 0 Fehler/0 Warnungen, unveränderte geschützte Objekt-Hashes und L3-Power Loss/Gain exakt 0,0/0,0 mm². Trotz Fortschritten `accepted=false`, `routing_completed=false`, `fabrication_release=false`, `restoration_attempted=false` und `victims_restored=0/201`.

Die Details stehen im lokal erzeugten Prüf- und Reconciliation-Paket. Weder dieses Dokument noch synthetische Tests sind ein nativer Lauf #102.

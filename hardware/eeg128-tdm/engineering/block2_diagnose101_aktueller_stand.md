<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2 – aktueller Stand, 24.11.2026

**Diagnose #101 ist der neueste vom Projektverantwortlichen gemeldete lokale Scratch-Lauf.** Die Originaldateien in `/workspace/scratch/diagnose101/` sind hier nicht verfügbar. Diese Daten sind **nicht unabhängig aus #101-Dateien verifiziert**. Der letzte unabhängig über GitHub geprüfte Block-2-Actions-Lauf ist [#79](https://github.com/C31N/nbfm1-open-bci/actions/runs/44659874632) (SUCCESS), dazu [CI #1107](https://github.com/C31N/nbfm1-open-bci/actions/runs/44659874554) und [KiCad #962](https://github.com/C31N/nbfm1-open-bci/actions/runs/44659874510) (SUCCESS).

| Kennzahl | Gemeldete lokale Diagnose #101 |
|---|---|
| Native geprüfte Zustände | 5 auf Tiefe 18, geometrisch und im nativen ROI-DRC / CLI-Gegentest laut Bericht bestätigt |
| Kandidat Nr. 2 | 2 CH028-Fortsetzungen, min. Kupferabstand 0,823726 mm, 27 Queue-Zustände |
| Kandidat Nr. 4 | 2 CH029- und 1 CH030-Fortsetzung, min. Kupferabstand 0,563212 mm, 30 Queue-Zustände |
| CH030-Ausweichast, Nr. 4 | (47,045 / 37,510) -> (47,265 / 37,510) mm, Abstand zu U3/13 0,563212 mm |
| Entfernung zum linken ROI-Rand | Auf 5,052055 mm **gestiegen**, Delta +0,175940 mm |
| Ausgeschlossener Vorschlag | Nr. 2 CH028: Warm-DRC nennt B.Cu-Track, CLI ein Via am MUX_S2; UUID/Layer-Zuordnung widersprechen sich |
| Zeitüberschreitungen | Bei beiden Kandidaten der vierte Prüfauftrag am unveränderten 4-s-ROI-DRC-Limit, Ergebnis **unbestimmt** |

**Schutzstatus:** Ausgangs-Checkpoint 139 Luftlinien; keine vollendete Zielverbindung (0/3), keine neuen Vias (0), keine Restitution (0/201). `accepted=false`, `routing_completed=false`, `fabrication_release=false`, `restoration_attempted=false`. Die 57 offenen Queue-Zustände sind nicht 57 Luftlinien.

**Verifizierte Referenzen:** `main=085823dc2092edaef43ae17c98b9879f53283495`; Entwicklungsbranch `cb922695983f93db918957283096b11c3ba080fa`. #79-JSON SHA-256 `64bbb8c3224f07aecdf499afe95e2b2ceb552469f26c298b72a034bd0215ff60`; #79 protokollierter Scratch-Byte-SHA `19d5cfbde9adcffebcf68860be7317185b781a82dc0f15fb5a8f70800eb703dc`.

Siehe [nicht-desktruktiver Prüfplan #102](block2_diagnose102_pruefplan.md). Eine separate Prüfung der 201er-Restitution ist nur **nach 3/3 vollständig geschlossenen nativen F.Cu-Routen** überhaupt zulässig; keine automatische Freigabe.

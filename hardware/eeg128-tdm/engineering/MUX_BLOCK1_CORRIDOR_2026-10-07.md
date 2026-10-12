> Historischer Bericht. Aktueller 167er-Checkpoint: [MUX_BLOCK1_LEFT_VCM_2026-10-07.md](MUX_BLOCK1_LEFT_VCM_2026-10-07.md).

# MUX-Block 1: Connectivity-Checkpoint — 2026-10-07

**Nativer KiCad 8.0.9 DRC: 0 Verletzungen / 0 Warnungen / 174 offene Verbindungen.** Vier weitere Luftlinien geschlossen, gegenüber dem verifizierten 178er-Checkpoint. Die erste Block-Tranche bleibt unvollständig; die neuen Verbindungen sind noch nicht als kompakte, symmetrisch gekoppelte Analogpaare qualifiziert.

| Gruppe | Vorher | Jetzt | Geschlossen |
|---|---:|---:|---:|
| MUX global | 101 | 97 | 4 |
| Elektroden/RC global | 77 | 77 | 0 |
| Gesamt | 178 | 174 | 4 |
| MUX CH000–CH015 | 8 | 4 | 4 |
| Elektroden/RC CH000–CH015 | 14 | 14 | 0 |

POWER, AGND, MUX_CONTROL, QSPI und BANK0_N_BUFFER bleiben ohne offene Verbindung. Alle 174 offenen Items betreffen unterschiedliche Analognetze.

## Angenommene Kupferänderungen

Geschlossen: CH011_N_MUX, CH002_N_MUX, CH010_N_MUX und CH014_N_MUX. Mit den zuvor vorhandenen P-Leitungen sind vier weitere MUX-P/N-Verbindungen vollständig angeschlossen. Kein zusätzlicher vollständiger Connector→RC→MUX-P/N-Kanal wurde geschlossen: CH002_N_ELECTRODE, beide CH010-Elektrodenleitungen, CH011_P_ELECTRODE und CH014_P_ELECTRODE bleiben offen.

Die B.Cu-VCM-Trasse bei Y=36,4 mm und ihre überlappende erste Bankstrecke wurden nur lokal ersetzt. Breite bleibt 0,25 mm, Abstand zu CH-Kupfer bleibt mindestens nach den unveränderten nativen 0,20-mm-Referenzregeln. Außenstücke: X=11,75→24,80 und X=30,00→188,75 mm bei Y=36,4 mm. Die Ersatzstrecke führt über (24,80;33,00) und (30,00;33,00) zurück nach (30,00;36,40) mm. Bestehender VCM-Abzweig: (27,75;36,40)→(30,00;36,40) mm. Alle VCM-Ersatzsegmente liegen auf L4, ohne neue VCM-Vias. Hauptumweg 12,0 statt 5,2 mm, also +6,8 mm; VCM-Last, Einschwingverhalten und Übersprechen bleiben zu prüfen. Keine Änderung an Zonen-Umrissen, Pad-Netzen, Footprint-Positionen oder DRC-Regeln.

CH011_N verlässt R24.1 bei (25,75;20,80) mm auf L1, läuft über (26,55;20,80) nach (26,55;34,50) mm und wechselt dort mit Ø0,60/0,30 mm auf L4. Ziel-Drop: U2.20 bei (15,595;48,850) mm, ebenfalls Ø0,60/0,30 mm. Weitere Wegpunkte und Wechsel sind in `mux-block1-ch011n-path.json` dokumentiert. Die Signalbreite beträgt 0,15 mm. Die übrigen drei Wege verwenden ebenfalls L1/L4 und Ø0,60/0,30-mm-Vias; sämtliche Wegpunkte in `mux-block1-corridor-paths.json`, tatsächliche Kupferblöcke in der hashgebundenen Recipe. Zwei redundante über vorhandenen 0,20-mm-RC-Stubs liegende 0,15-mm-Segmente wurden vor dem Replay entfernt. Der notwendige CH002_N-Escape blieb erhalten.

## Analogqualifizierung bleibt offen

Gemessene gesamte Netzkupferlängen, einschließlich RC-Stubs/Abzweigen; keine elektrischen Laufzeitlängen:

| MUX-Paar | P mm | N mm | Vias P / N |
|---|---:|---:|---:|
| CH002_MUX | 24.049247 | 70.919647 | 0 / 10 |
| CH010_MUX | 26.829068 | 57.536436 | 0 / 8 |
| CH011_MUX | 21.737741 | 42.764688 | 6 / 6 |
| CH014_MUX | 8.175646 | 44.159792 | 0 / 8 |

Diese Unterschiede sind ausdrücklich **kein P/N-Längen-/Kopplungs-PASS**. Die N-Wege reduzieren den Connectivity-Restbestand, müssen aber für die geforderte kompakte Paarführung mit ihren bestehenden P-Gegenleitungen gemeinsam optimiert werden. Der Audit dokumentiert geometrische P/N-Abstände und die L2/L3-Projektion mit ≤0,05-mm-Abtastung; er ersetzt keinen Impedanz-, Kopplungs- oder Rückstromnachweis. `compact_pair_routing_qualified`, `pair_coupling_qualified`, `return_current_qualified` und `guard_ring_qualified` bleiben false. Via-in-pad-Endpunkte benötigen vor Freigabe die Prüfung des Löt-/Füll-/Kappenprozesses.

Der zuvor angenommene kurze AGND-Streifen bleibt angebunden; kein zusätzlicher vollständiger Guard-Ring wurde qualifiziert. L2-AGND: eine Insel, 151 gleichnamige Via-Kontakte. L3: je eine Insel, 3V3A=39, 5V_ISO=8, 3V3D=23 Via-Kontakte; keine gefüllte Insel ohne Via-Kontakt. Eine globale Insel beweist keinen lokalen störungsarmen Rückstrompfad. ADC6/ADC7-Kupfer ist blockweise bytegleich zum 178er-Baseline-Kupfer; Via-Y-Ausrichtung und Kupferlängendifferenzen <0,001 mm bleiben erhalten. Elektrische ADC-Qualifizierung bleibt offen.

## Verbleibender Blocker

Im ersten Block verbleiben CH004_N_MUX, CH005_N_MUX, CH008_P_MUX und CH008_N_MUX sowie 14 Elektroden-/RC-Verbindungen. F→F-, F→B- und B→F-Kandidaten mit lokalen Escapes wurden mit unveränderten Regeln geprüft. Die CH011_P_ELECTRODE-RC-Tasche umfasst im konservativen 0,05-mm-Suchmodell 1.257 erreichbare L1-Punkte und keinen erlaubten Via-Wechsel auf L4. Das ist ein konkreter Hinweis auf den lokalen Escape-Engpass, kein Beweis der Unlösbarkeit mit nativer interaktiver Führung. Die CH008-MUX-Padbereiche besitzen in den untersuchten Drop-Fenstern keinen freien Ø0,60-mm-Via-Platz.

Nächste lokale Arbeit: linke VCM-Sammeltrasse und bestehende CH-Pin-Escapes zusammen mit den offenen CH004/005/008-Gegenleitungen neu führen; Elektroden-RC-Taschen gezielt öffnen. Bereits geschlossene P-Leitungen müssen dabei in die kompakte Paarplanung einbezogen werden. Keine globale Abstandslockerung oder zusätzliche unqualifizierte Freigabe.

## Reproduktion und Gates

Unabhängiger Replay: 178→174, 0 Fehler/0 Warnungen, bytegleiches PCB-Ergebnis. Per-Netz-Regressionstest: keine andere Verbindung wieder geöffnet. Der Replay erlaubt die VCM-Entfernung ausschließlich für die beiden konkret identifizierten alten B.Cu-Trunks; sieben negative Guard-Fälle werden abgewiesen. Mutation, Zonen-Fill und nativer DRC laufen in getrennten Prozessen.

Native PCB-generierte Diagnose-Parität: 0 Befunde; XML-Abgleich: 2.054/2.054 Pin-/Netzzuordnungen. Unabhängiger Primärschaltplan-LVS weiterhin ausstehend. Hardware-/BOM-/CPL-Identität: 642 Positionen, PASS.

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T13:21:56+0200",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 174,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

`routing_completed=false`, `fabrication_release=false`, `schematic_parity_passed=false`. Keine Promotion in den primären Fertigungspfad, keine Erzeugung/Überschreibung von Gerber, Drill, Pick&Place oder BOM. PUBLICATION_SHA256SUMS bleibt unverändert.

Vom Repository-Root, mit KiCad-8-Python und nativer kicad-cli; neue Ausgabeordner verwenden:

```sh
unzip hardware/eeg128-tdm/engineering/mux-block1-vcm-baseline-178.zip -d /tmp/eeg128-block1-base
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-block1-base/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/mux-block1-corridor-recipes.json \
  --output-dir /tmp/eeg128-block1-replay
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-block1-replay/
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-block1-replay/drc-parity.json /tmp/eeg128-block1-replay/eeg128-tdm.kicad_pcb
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der Replay führt `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` in separaten Prozessen vor/nach der Mutation aus; zusätzliche manuelle Fill-Versuche sind zur Reproduktion nicht nötig. KiCad 8.0.9 bietet in dieser Runtime keinen `pcb fill-zones`-CLI-Unterbefehl. Der korrekte Projekt-/Regelsatz wird bei jedem Fill/DRC bewahrt. KiCad-Audits desselben Projekt-Basenamens werden seriell ausgeführt; parallele Prozesse benötigen getrennte Projektkopien, um Projekt-Lock-Konflikte zu vermeiden.

105 Einträge in `CHECKPOINT_SHA256SUMS` sind nach der Archivprüfung erfolgreich verifiziert.

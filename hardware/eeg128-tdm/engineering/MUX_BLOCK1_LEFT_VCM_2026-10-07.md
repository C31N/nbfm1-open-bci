# Block CH000–CH015: VCM-Überarbeitung und sieben Anschlüsse — 2026-10-07

**KiCad 8.0.9, nativ und aus dem Archiv erneut geprüft: 0 DRC-Verletzungen / 0 Warnungen / 167 offene Verbindungen.** Der verifizierte 174er-Checkpoint wurde um sieben Anschlüsse reduziert. Das Routing bleibt unvollständig.

| Gruppe | 174er-Einstieg | Jetzt | Geschlossen |
|---|---:|---:|---:|
| MUX global | 97 | 95 | 2 |
| Elektroden/RC global | 77 | 72 | 5 |
| Gesamt | 174 | 167 | 7 |
| MUX CH000–CH015 | 4 | 2 | 2 |
| Elektroden/RC CH000–CH015 | 14 | 9 | 5 |

Alle 167 offenen Items liegen auf unterschiedlichen Analognetzen. POWER, AGND, MUX_CONTROL, QSPI und BANK0_N_BUFFER bleiben ohne Luftlinie. Geschlossen wurden CH008_P_MUX, CH008_N_MUX, CH004_N_ELECTRODE, CH006_N_ELECTRODE, CH006_P_ELECTRODE, CH010_N_ELECTRODE und CH012_N_ELECTRODE. **CH006 und CH008 sind zusätzlich über beide P/N-Zweige von Connector → RC → MUX vollständig verbunden.** Das ist ein Connectivity-Nachweis, kein elektrischer P/N-Signoff.

## VCM- und Pin-Escape-Änderungen

Die 24 überlappenden B.Cu-VCM-Segmente an X=11,75 / 16,45 / 22,25 mm wurden durch nicht überlappende 0,20-mm-Spaltenabschnitte zwischen den bestehenden RC-Via-Reihen ersetzt. Spalten-Y: 13,0 / 15,6 / 18,2 / 20,8 / 23,4 / 26,0 / 28,6 / 31,2 / 33,0 mm. Zusätzlich wurden genau der alte 0,25-mm-Quertrunk (11,75;36,40)→(24,80;36,40) und sein Tail (24,80;36,40)→(24,80;33,00) entfernt. Neue 0,25-mm-Verbindungen koppeln die drei Spalten an den vorhandenen VCM-Trunk bei (24,80;33,00). Die erste Verbindung umgeht bestehendes CH-Kupfer und erreicht lokal Y=36,4 mm; vollständige Koordinaten stehen in `mux-block1-left-vcm-paths.json`. **Sämtliches neues VCM-Kupfer liegt auf L4; keine neuen VCM-Vias.** Bestehende RC-VCM-Vias und die zuvor gesicherte rechte VCM-Umleitung bleiben erhalten. Referenz-Einschwingen und Übersprechen sind weiterhin zu qualifizieren.

CH008_P_MUX: RC-Drop bei (20,15;13,00), oberer L3-Ausgang bei (23,279999;33,729999), MUX-Drop bei (11,70;35,85) mm. CH008_N_MUX: L1-Escape von (25,75;13,00) nach (24,55;11,90), L3-Ausgang bei (8,029999;34,679999), MUX-Drop bei (11,40;48,85) mm. Die N-Drop-Position ist gegenüber dem Padzentrum (11,785;48,85) um −0,385 mm auf X versetzt und hält die bestehende CH012_N_MUX-L4-Spur frei. Alle neuen Signalvias sind Ø0,60 / Bohrung0,30 mm, alle neuen Signaltraces 0,15 mm. P hat insgesamt drei, N fünf Vias; diese Asymmetrie bleibt ein Qualifizierungsblocker. Der redundante neue P-RC-Stummel über dem vorhandenen 0,20-mm-Trunk wurde vor dem Replay entfernt.

Für die neuen Elektroden-Verbindungen wurden native geprüfte L1-Pin-Escapes und jeweils zwei Ø0,60/0,30-mm-Endpunkt-Vias eingesetzt; der Zwischenweg liegt im oberen, bereits freien L3-Korridor. Auch CH006_P/N ist damit angeschlossen, aber noch nicht längen-/kopplungsqualifiziert. Via-in-Pad-Endpunkte bleiben Gegenstand der Assembly-Prüfung.

## L3-Nachweis und Plane-Anbindung

Der L1/L4-Hauptansatz wurde lokal um L3 ergänzt, ausschließlich oberhalb der bestehenden 3V3A-Fläche. Die neuen L3-Signale schneiden **kein zuvor gefülltes Power-Kupfer**. Die tatsächliche Signal-Kupferkante wurde geometrisch gegen die gefüllten L3-Polygone des hashgebundenen 174er-Baselines geprüft, einschließlich Aussparungen. Erforderlicher Referenzabstand: 0,20 mm; kleinster gemessener Abstand: 2,245001 mm. Globale Clearance-Regeln und die bereits vorhandenen Engineering-Neckdown-Regeln bleiben bytegleich zum 174er-Stand.

| Neues L3-Netz | Kupferlänge mm | Kleinster Abstand zum alten Power-Kupfer mm |
|---|---:|---:|
| CH004_N_ELECTRODE | 14.832052 | 16.128307 |
| CH006_N_ELECTRODE | 12.866367 | 21.327501 |
| CH006_P_ELECTRODE | 9.200072 | 22.825000 |
| CH008_N_MUX | 32.068338 | 2.245001 |
| CH008_P_MUX | 22.152318 | 3.201278 |
| CH010_N_ELECTRODE | 11.912942 | 18.729980 |
| CH012_N_ELECTRODE | 17.226546 | 12.825002 |

Die native Zone-Refill-Prüfung findet weiterhin je eine gefüllte Insel auf L2-AGND und den drei L3-Power-Netzen. Gleichnamige Via-Kontakte: AGND151, 3V3A39, 5V_ISO8, 3V3D23. Keine gefüllte Insel ohne Kontakt. Der bestehende 0,70-mm-AGND-Streifen bleibt angebunden. Es wurde **kein zusätzlicher vollständiger Guard-Ring** qualifiziert. Signal-Via-Antipads und lokale Rückstromführung müssen elektrisch geprüft werden; eine globale Insel genügt dafür nicht. Projektion und P/N-Abstände sind in `mux-block1-reference-geometry.json` dokumentiert. ADC6/ADC7-Kupfer ist unverändert; die zuvor bestätigten Via-Y-Ausrichtungen und Kupferlängendifferenzen <0,001 mm bleiben erhalten.

## P/N-Kompaktierung und offene Blocker

Für CH002, CH010, CH011 und CH014 wurden isolierte gemeinsame P/N-Korridorversuche nach paarweisem Rückbau durchgeführt. Untersucht wurden 0,50-mm-Bundles (2×0,15 mm Kupfer, 0,20 mm Paarlücke) auf L1 beziehungsweise L4 mit unveränderten Nachbarabständen. Keine angenommene kompakte Paarroute entstand. Der Rückbau war auf verworfene Kandidaten beschränkt; die bestehenden vier P/N-Verbindungen sind im Checkpoint unverändert geschlossen. Die Suche war begrenzt und beweist keine geometrische Unlösbarkeit. Ein separater Rip-up-/Wiederherstellungsversuch mit 217 nativen Fehlern wurde verworfen.

Gesamte Netzkupferlängen einschließlich RC-Stubs/Abzweigen, **keine elektrischen Pfadlängen**:

| MUX-Paar | P mm | N mm | Vias P / N |
|---|---:|---:|---:|
| CH002_MUX | 24.049247 | 70.919647 | 0 / 10 |
| CH008_MUX | 36.000322 | 50.147122 | 3 / 5 |
| CH010_MUX | 26.829068 | 57.536436 | 0 / 8 |
| CH011_MUX | 21.737741 | 42.764688 | 6 / 6 |
| CH014_MUX | 8.175646 | 44.159792 | 0 / 8 |

Das geforderte <0,001-mm-P/N-Ziel ist für diese MUX-Paare nicht erreicht. `compact_pair_routing_qualified`, `pair_coupling_qualified`, `return_current_qualified` und `guard_ring_qualified` bleiben false. Ein bloßes Hinzufügen von Kupferloops würde keinen belastbaren Pfad-Längennachweis liefern und wurde nicht als Matching gewertet.

Die folgenden elf Verbindungen bleiben in Block 1 offen:

- CH000_N_ELECTRODE
- CH004_N_MUX
- CH004_P_ELECTRODE
- CH005_N_ELECTRODE
- CH005_N_MUX
- CH010_P_ELECTRODE
- CH011_P_ELECTRODE
- CH012_P_ELECTRODE
- CH014_P_ELECTRODE
- CH015_N_ELECTRODE
- CH015_P_ELECTRODE

CH004/CH005 wurden zusätzlich mit versetzten MUX-Endpunkt-Via-Fenstern untersucht; kein sauberer äußerer Anschluss an den freien oberen Korridor entstand. Für CH011_P_ELECTRODE und CH012_P_ELECTRODE wurden weitere lokale Drop-Kombinationen geprüft; beide bleiben offen. Bei mehreren übrigen J1-Pins liefert das konservative 0,05-mm-Fenstermodell noch keinen direkten L1-Escape zu einem freien Ø0,60-mm-Via. Der nächste Layout-Schritt erfordert die gemeinsame lokale Neuführung der benachbarten Connector-/MUX-Pin-Escapes und beider P/N-Wege, einschließlich genauer Pfadlängenanalyse; weitere identische globale Suchläufe lösen diesen Konflikt nicht.

## Replay, Diagnose-Parität und Release-Gates

Hashgebundener Replay: **174→167**, 0 Fehler/0 Warnungen, keine Per-Netz-Regression, bytegleiche PCB nach nativem Fill. Genau 26 alte VCM-Blöcke werden entfernt; alle Signaländerungen sind additiv und auf CH000–CH015 beschränkt. Die neue Scope-Prüfung weist 13 negative Fälle zurück, unter anderem ADC-/Fremdnetz-Zugriffe, geänderte Baselines, unzulässige Layer/Breiten/Bohrungen und doppelte UUIDs. ADC-Kupfer, alle Footprints, Zonen-Umrisse, Projekt und Regeln sind analytisch unverändert. Mutation, Fill und CLI-DRC laufen in getrennten Prozessen.

PCB-generierte Diagnose-Parität: 0 Befunde, native XML-Zuordnungen 2.054/2.054 identisch. **Unabhängiger Primärschaltplan-LVS steht weiterhin aus.** Hardware-/BOM-/CPL-Identitätsprüfung: 642 Positionen, PASS. Der Checkpoint wurde aus `latest-pcb.zip` erneut extrahiert und mit nativen Fill/DRC geprüft; die PCB bleibt bytegleich.

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T18:08:19+0100",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 167,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

`routing_completed=false`, `fabrication_release=false`, `schematic_parity_passed=false`. Primäre KiCad-Dateien und Fertigungsartefakte werden nicht promotet; PUBLICATION_SHA256SUMS, BOM und CPL bleiben unverändert. Keine Gerber-, Drill- oder Pick&Place-Erzeugung.

## Reproduktionsbefehle

Vom Repository-Root mit KiCad-8-Python, kicad-cli, numpy und shapely; neue Ausgabeordner verwenden:

```sh
unzip hardware/eeg128-tdm/engineering/mux-block1-left-vcm-baseline-174.zip -d /tmp/eeg128-vcm-base
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-vcm-base/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/mux-block1-left-vcm-recipes.json \
  --output-dir /tmp/eeg128-vcm-replay
/usr/bin/python3 hardware/eeg128-tdm/audit_block1_corridor_geometry.py \
  --baseline /tmp/eeg128-vcm-base/eeg128-tdm.kicad_pcb \
  --board /tmp/eeg128-vcm-replay/eeg128-tdm.kicad_pcb \
  --output /tmp/eeg128-vcm-replay/L3-geometry.json
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-vcm-replay/
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-vcm-replay/drc-parity.json /tmp/eeg128-vcm-replay/eeg128-tdm.kicad_pcb
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der Replay ruft `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` in separaten Prozessen auf und bewahrt `.kicad_pro`/`.kicad_dru`. Für einen zusätzlichen Fill einer Archivkopie: `/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-vcm-replay/eeg128-tdm.kicad_pcb`. KiCad 8.0.9 bietet in dieser Runtime keinen `pcb fill-zones`-CLI-Unterbefehl.

Archiv-SHA256: `6e1cdbed22dc50aa286acfdd1eb2af3ee142170e48502ca2d088ab8d653b99b6`. PCB-SHA256: `79b30a218cf4913f67c5515e707e362799c5ef3cef080a310c24c15f8f357f68`. Die abschließende CHECKPOINT_SHA256SUMS-Prüfung ist separat dokumentiert.

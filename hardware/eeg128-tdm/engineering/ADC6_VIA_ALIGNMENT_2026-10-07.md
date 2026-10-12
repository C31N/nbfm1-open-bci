> Historischer ADC6-Checkpoint. Aktuelle erste MUX-Tranche: MUX_BLOCK1_CLOSURE_2026-10-07.md.

# ADC6-Via-Ausrichtung und erster MUX-Pass — 2026-10-07

**KiCad 8.0.9: 0 DRC-Verletzungen / 0 Warnungen / 179 offene Verbindungen.** ADC6-Via-Zeilen ausgerichtet und Kupferlängengleichheit <0,001 mm wiederhergestellt. Restbestand unverändert: 102 MUX- und 77 Elektroden-/RC-Verbindungen. Es wurde keine weitere MUX-Luftlinie geschlossen.

## Angenommene ADC6-Geometrie

| Übergang | P-Via X / Y mm | N-Via X / Y mm | Y-Versatz mm | X-Abstand mm |
|---|---|---|---:|---:|
| Oben | 125,100 / 69,000 | 133,300 / 69,000 | 0 | 8,200 |
| Unten | 123,800 / 72,000 | 132,000 / 72,000 | 0 | 8,200 |

Alle vier Vias durchgehend F.Cu–B.Cu, Ø0,60 mm / Bohrung0,30 mm. P und N haben damit identische geometrische Verschiebung zwischen oberem und unterem Via: ΔX=−1,300 mm und ΔY=+3,000 mm. Die Via-Anordnung bildet ein Parallelogramm. Der Abstand von 8,20 mm ist **kein definierter gekoppelter Paarabstand**.

Die ADC6-F.Cu- und B.Cu-Ketten wurden in zuvor geprüften freien Korridoren neu geführt, bei unveränderter 0,15-mm-Breite. ADC6_N erhielt eine L4-Längenführung mit 45°-Eckabschrägungen. Alle exakten Kupferblöcke und entfernten UUIDs stehen in `adc6-via-recipes.json`; die neuen N-L4-Eckpunkte in `adc6-via-length-path.json`. Kein Pad, Netz, Footprint, Projektparameter oder Zonen-Umriss wurde geändert. ADC7-Kupfer bleibt unverändert.

| Paar | P-Kupferlänge mm | N-Kupferlänge mm | Unterschied mm |
|---|---:|---:|---:|
| ADC6 | 18.532260578 | 18.532264685 | 0.000004107 |
| ADC7 | 11.190463331 | 11.190462468 | 0.000000862 |

Die Zahlen sind analytische Kupfer-Mittellinienlängen aus KiCad, ohne vertikale Via-Länge, Impedanz- oder Ausbreitungszeitmodell. Die einzelnen Ketten sind im auf 0,001 mm zusammengefassten Endpunktgraphen unverzweigt. Die N-L4-Längenführung ist geometrisch einfach, ohne Selbstschnitt. Für ADC6 verteilen sich die Längen weiterhin unterschiedlich auf die Layer: P etwa 14,994 mm L1 + 3,538 mm L4; N etwa 9,644 mm L1 + 8,888 mm L4. Gleiche Gesamtlänge und eine ausgerichtete Via-Anordnung beweisen deshalb keine elektrische Paarsymmetrie.

## Kopplungs-, Rückstrom- und Guard-Audit

Die Prüfung der gefüllten Kupferprojektion erfolgt mit maximal 0,05-mm-Abtastung. AGND/L2 bleibt eine zusammenhängende gefüllte Insel mit 149 Via-Kontakten. L3 enthält je eine angebundene Insel für 3V3A (39), 5V_ISO (8) und 3V3D (23 Via-Kontakte). Keine dieser vier gefüllten Inseln ist ohne gleichnamigen Via-Kontakt.

| L4-Netz | L2-AGND unter Mittellinie % | Projektion auf L3-3V3A mm | Ohne gefüllte L3-Zone mm |
|---|---:|---:|---:|
| ADC6_P | 73,42 | 2,498 | 1,041 |
| ADC6_N | 88,58 | 7,774 | 1,114 |
| ADC7_P | 85,60 | 5,181 | 0,987 |
| ADC7_N | 88,86 | 6,995 | 0,988 |

Die Aussparungen umfassen legitime Signal-Via-Antipads. Ein fehlender Kupfer-Treffer beweist keinen Plane-Split; eine einzige globale Insel beweist umgekehrt keinen ununterbrochenen lokalen Rückstrompfad. Die unmittelbar benachbarte L3-Referenz unter den L4-Signalen ist überwiegend 3V3A, nicht L2-AGND. Referenzwechsel und Entkopplungs-/AGND-Rückwege benötigen noch eine elektrische Prüfung.

Auf L4 sind die abgetasteten ADC6-P/N-Mittellinienabstände ungefähr 6,54–8,57 mm; bei ADC7 0,80–2,25 mm. Die Werte schließen Pads/Vias aus und sind kein Kopplungs- oder Impedanznachweis. Ein geschlossener lokaler Guard-Ring wurde nicht hergestellt oder qualifiziert. `ADC6_symmetry_qualified`, `ADC7_pair_geometry_qualified`, `return_current_qualified`, `pair_coupling_qualified` und `shielding_guarding_qualified` bleiben `false`.

## Erste MUX-Paare und konkrete Blockaden

Ein separater automatischer Pass für CH011, CH075 und CH016 (P/N gemeinsam ausgewählt, 240-s-Budget, 0,05-mm-Raster, L1/L4) hat keine Verbindung geschlossen. Für CH075 und CH011 wurden anschließend lokale Pad-Escapes und Drop-Vias mit unterschiedlichen Endpositionen sowie ein zusätzlicher Layer-Wechsel-Pass untersucht. Für CH075 wurden auch alle vier Kombinationen der Start-/Ziellayer mit erweitertem 20-mm-Suchrand untersucht. Keine dieser vollständigen Verbindungen wurde gefunden bzw. angenommen; keine MUX-Escape-Vias wurden in den Checkpoint übernommen.

Beispiel CH075_P_MUX: R407.2 bei (111,750;20,800) mm ist mit R151.1 verbunden, U9.20 bei (107,595;35,850) mm bleibt offen. Eine CH076_P_ELECTRODE-L4-Trasse bei X=112,058 mm liegt nur 0,233 mm vom ursprünglichen R407-Padzentrum bis zu ihrer Kupferkante entfernt; ein Ø0,60-mm-Drop-Via kollidiert dort mit der erforderlichen Clearance. Am U9-Pad liegt die VCM-L4-Trasse Y=36,400 mm mit nur 0,425 mm Kupferkantenabstand zum Padzentrum; für Via-Radius0,30 + VCM-Clearance0,20 mm reicht dies ebenfalls nicht. Verschobene Drop-Kandidaten und mehrlagige Pfadsuche lieferten weiterhin keine komplette Verbindung. Dies sind geometrische Engpässe, kein Anlass zur Lockerung der DRC-Regeln.

Nächster konkreter MUX-Schritt: die angrenzenden CH076-Elektroden-/VCM-Trunks auf eine lokal reproduzierbare Umführung prüfen und anschließend CH075 vollständig verbinden; für CH011 beide Seiten gemeinsam planen. Ein Rückbau bestehender Trunks darf nur mit erneutem DRC und per-Netz-Regressionsprüfung übernommen werden.

## Parität und Release

Native Diagnose-Parität: 0 Befunde. Die bisherigen 2.054 Pin-/Netzzuordnungen bleiben unverändert und werden erneut gegen den nativen XML-Export geprüft. Der Diagnose-Schaltplan stammt aus PCB-Daten; er liefert weiterhin **keinen unabhängigen Primärschaltplan-LVS-PASS**. Der Primärschaltplan wurde nicht durch Diagnose-Daten ersetzt.

`routing_completed=false`, `fabrication_release=false`, `schematic_parity_passed=false`. Keine Fertigungsartefakte erzeugt oder überschrieben; PUBLICATION_SHA256SUMS, BOM, CPL und die primären KiCad-Dateien bleiben unverändert.

## Reproduktion

Mutation, Zonen-Fill und nativer DRC laufen in getrennten Prozessen. Der unabhängige Replay reproduziert die PCB bytegenau mit 0/0/179 und ohne Regression anderer Netze. Die Löschfreigabe ist auf ADC6_P/ADC6_N-Segmente und den Austausch von exakt zwei Ø0,60/0,30-mm-Vias je Seite in `ADC6_VIA_GEOMETRY` begrenzt. Ungescopte Löschversuche werden zurückgewiesen. Das Eingangsarchiv bleibt als `adc6-via-baseline-179.zip` gesichert; frühere Längen- und Paritätsrezepte bleiben historisch erhalten.

Vom Repository-Root, mit KiCad-8-Python, kicad-cli, numpy und shapely; Ausgabeordner müssen neu sein:

```sh
unzip hardware/eeg128-tdm/engineering/adc6-via-baseline-179.zip -d /tmp/eeg128-adc6-via-base
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-adc6-via-base/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/adc6-via-recipes.json \
  --output-dir /tmp/eeg128-adc6-via-replay
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-adc6-via-replay/
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-adc6-via-replay/drc-parity.json /tmp/eeg128-adc6-via-replay/eeg128-tdm.kicad_pcb
/usr/bin/python3 hardware/eeg128-tdm/audit_adc_pair_geometry.py \
  --board /tmp/eeg128-adc6-via-replay/eeg128-tdm.kicad_pcb \
  --output /tmp/eeg128-adc6-via-replay/pair-geometry.json
/usr/bin/python3 hardware/eeg128-tdm/audit_analog_return_geometry.py \
  --board /tmp/eeg128-adc6-via-replay/eeg128-tdm.kicad_pcb \
  --output /tmp/eeg128-adc6-via-replay/return-geometry.json
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der Replay führt bereits den nativen Python-Zonen-Fill vor und nach der Mutation aus. Für eine separate aktuelle Archivkopie kann dieser explizit aufgerufen werden:

```sh
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-adc6-via-replay/eeg128-tdm.kicad_pcb
```

## Nativer DRC-Kopfbericht

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T15:06:20+0500",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 179,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

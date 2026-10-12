> Historischer ADC6/ADC7-Paritätscheckpoint. Aktuelle ADC6-Längenanpassung: ADC6_LENGTH_CLOSURE_2026-10-07.md.

# ADC6/ADC7 und Diagnose-Parität — 2026-10-07

**KiCad 8.0.9: PCB-DRC 0 Verletzungen / 0 Warnungen / 179 offene Verbindungen.** Der Routing-Restbestand bleibt bei 102 MUX- und 77 Elektroden-/RC-Netzen. POWER, AGND, MUX_CONTROL, QSPI und BANK0_N_BUFFER bleiben geschlossen.

## ADC6: Kollision aufgelöst, Symmetrie weiterhin offen

Der frühere N-L4-Versuch kollidierte mit BANK-/ADC-Trunks und einem ADC0_N-Via. Statt dieser Endpunkte wurde ein freier Übergangskorridor gewählt. ADC6_N hat jetzt zwei echte F.Cu–B.Cu–F.Cu-Übergänge mit Vias Ø0,60 mm / Bohrung0,30 mm bei (130,250;71,003443) und (133,500;68,626700) mm. Die N-Leiterbahn bleibt 0,15 mm breit. Ein Teil der bestehenden L1-Diagonale und des oberen L1-Segments wurde ersetzt; der L4-Korridor ist in den hashgebundenen Kupfermutationen vollständig beschrieben.

ADC6_P bleibt mit seinen beiden Vias bei (123,843;74,400) und (125,862;67,9187) mm unverändert. P/N haben dieselbe Via-Anzahl und Geometrie. Ihre Übergangspositionen sind weiterhin deutlich versetzt. Das ist **kein symmetrischer Paarabschluss**.

## ADC7: Via-Paare ausgerichtet und Kupferlängen angepasst

| Übergang | P-Via X/Y mm | N-Via X/Y mm | Y-Versatz mm |
|---|---|---|---:|
| Oben | 134,201 / 69,1857 | 135,001 / 69,1857 | 0 |
| Unten | 131,900 / 74,400 | 133,700 / 74,400 | 0 |

Alle vier Vias: Ø0,60 / Bohrung0,30 mm, durchgehend L1–L4. Der Via-Abstand beträgt oben 0,80 mm und unten 1,80 mm. Die unteren RC-Fanouts sind mit jeweils etwa 0,70 mm zu den Padzentren ausgerichtet. ADC7_N erhält auf L4 eine zusätzliche Längenführung über (135,001;72,700) → (136,361140;72,800) → (133,700;74,400) mm. Ein vorheriger Abstimmungsversuch kollidierte mit BANK7_N_BUFFER und wurde verworfen; weitere Versuche kollidierten mit 3V3D/ADC3_N. Nur der native fehlerfreie Korridor ist angenommen.

| Paar | P-Kupferlänge mm | N-Kupferlänge mm | Unterschied mm |
|---|---:|---:|---:|
| ADC6 | 19,247 | 12,244 | 7,003 |
| ADC7 | 11,190 | 11,190 | <0,001 |

Diese Zahlen sind analytische Kupfer-Mittellinienlängen aus dem nativen Board, keine Messung an Hardware und kein Ausbreitungszeit-/Impedanznachweis. Beide ADC-Ketten bilden im mit 0,001 mm zusammengefassten Endpunktgraphen unverzweigte Verbindungen. Es sind keine freigegebenen Längen-/Kopplungstoleranzen definiert. ADC7 ist hinsichtlich Via-Y-Position und Kupferlänge verbessert; variable Paarabstände, Rückstrompfade, Abschirmung und AGND-Guards bleiben zu qualifizieren. ADC6 bleibt ein konkreter Layout-Blocker.

## Die 398 ursprünglichen Paritätswarnungen

| Kategorie im ursprünglichen JSON-Bericht | Anzahl |
|---|---:|
| Wertabweichung PCB ↔ Symbol | 99 |
| Footprint-ID-Abweichung PCB ↔ Symbol | 100 |
| Pad-/Symbol-Netzkonflikt | 199 |
| Gesamt | 398 |

Die Metadatenbefunde betreffen 100 Referenzen (C1–C64, J1–J11, R1–R25); die im Bericht sichtbaren Netzkonflikte betreffen C1–C64 und J1–J3. Dieser Bericht bildet nicht alle zugrunde liegenden Abweichungen ab: Der vollständige originale native XML-Netzlistenvergleich zeigt nach Normalisierung des Hierarchiepräfixes 2.017 falsche Zuordnungen unter 2.026 verbundenen Pins.

Ursachen und ausgeführte Korrekturen im **Engineering-Diagnosepfad**:

1. Symbolbibliothek und Schaltplanblatt verwenden entgegengesetzte Y-Richtungen. Die Anschlusslabels wurden mit `sheet_y = origin_y - library_pin_y` korrigiert; PCB-Signalnetze und nummerierte Signalpads wurden nicht vertauscht.
2. Globale Labels erhalten die tatsächlichen PCB-Netznamen. Die vorherigen lokalen Labels erzeugten unpassende `/NET`-Namen.
3. 641 PCB-Wertfelder wurden aus der vorhandenen unveränderten BOM übernommen. Die Diagnose-Symbol-Footprintfelder verwenden die tatsächlichen PCB-IDs; physische Gehäuse/Padgeometrien wurden nicht ersetzt.
4. 28 geprüfte unbenutzte Pins erhalten jeweils einen eigenen KiCad-NC-Netznamen. Die Symbole behalten No-Connect-Markierungen; kein NC-Netz besitzt Traces oder Zonen. Unnummerierte Montage-/Pastefeatures bleiben unverändert.
5. Drei bislang netzlose PTH-Schirmtabs von J9 mit derselben Pinnummer S1 werden dem vorhandenen SHIELD-Netz zugeordnet und auf L4 mit 0,20-mm-Traces verbunden: (181,87;72,68) → (186,05;72,68) → (186,05;81,32) → (181,87;81,32). SHIELD wird dabei nicht mit AGND verbunden.

Diagnosestufen: **398 → 199 → 31 → 0 native Paritätsbefunde**. Der abschließende vollständige native XML-Export stimmt in allen **2.054 nummerierten Pin-/Netzzuordnungen** mit dem Engineering-Board überein.

**Grenze des Nachweises:** Der korrigierte Diagnose-Schaltplan wird aus PCB-Padzuordnungen erzeugt. Seine fehlerfreie Parität ist ein Konsistenznachweis, kein unabhängiger Schaltungs-LVS-Signoff. Die primäre PCB und der primäre Schaltplan wurden nicht übernommen/ersetzt; das globale `schematic_parity_passed` bleibt daher `false`.

## Routing und Prozessnachweise

Ein 120-s-Diagnosepass für CH002_MUX/CH004_MUX mit beiden P/N-Netzen und 0,05-mm-Raster hat keine weiteren Verbindungen geschlossen. Er wurde nicht übernommen. Der bisherige Analog-Restbestand bleibt vollständig dokumentiert.

Alle angenommenen Mutationen und Zonen-Fill/native DRC liefen in getrennten Prozessen. Die Kupfermutationen wurden aus dem exakten 179er-Baselinearchiv wiederholt, mit 0/0/179 und ohne andere Netze wieder zu öffnen. Projekt-Netzklassen und Custom-Rules wurden vor jedem maßgeblichen DRC aus dem unveränderten Projekt wiederhergestellt. Zwei unabhängige Durchläufe der Paritätsvorbereitung erzeugen byteidentische PCB-, Projekt-, Regel- und Diagnose-Schaltplandateien.

Die vier Versorgungsflächen bleiben angebunden: AGND/L2=149 Via-Kontakte; L3: 3V3A=39, 5V_ISO=8, 3V3D=23. Keine gefüllte Insel ohne gleichnamigen Via-Kontakt. Hardware-/BOM-/CPL-Identität: 642 Positionen, PASS. Die einzige Erweiterung der Identitätsprüfung akzeptiert für explizit unbenutzte Pins exakt ihren eigenen KiCad-NC-Namen; beliebige Versorgungs-/Signalnetze sind weiterhin unzulässig.

`routing_completed=false`, `fabrication_release=false`. Keine Erzeugung/Überschreibung von PUBLICATION_SHA256SUMS, Gerber, NC Drill, Pick&Place oder BOM. Der PCB-ZIP enthält weiterhin genau PCB, Projekt und Regeln; der zugehörige Diagnose-Schaltplan liegt separat in `engineering/eeg128-tdm.kicad_sch`.

## Reproduktion und Prüfungen

Vom Repository-Root, mit KiCad-8-Python, kicad-cli, numpy und shapely:

```sh
unzip hardware/eeg128-tdm/engineering/analog-baseline-179.zip -d /tmp/eeg128-base-179
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-base-179/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/adc67-geometry-recipes.json \
  --output-dir /tmp/eeg128-adc67-replay
/usr/bin/python3 hardware/eeg128-tdm/prepare_native_parity.py \
  --board /tmp/eeg128-adc67-replay/eeg128-tdm.kicad_pcb \
  --output-dir /tmp/eeg128-parity-replay
/usr/bin/python3 hardware/eeg128-tdm/audit_adc_pair_geometry.py \
  --board /tmp/eeg128-parity-replay/eeg128-tdm.kicad_pcb \
  --output /tmp/eeg128-parity-replay/adc67-geometry.json
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Die Ausgabeordner müssen neu sein. `prepare_native_parity.py` schreibt keine primären PCB-/Schaltplan-/Fertigungsdateien. Es verweigert die Übernahme bei DRC-/Paritätsfehlern, erhöhten Luftlinien oder unpassender vollständiger Pin-Netzliste.

Prüfung des aktuellen Archivs:

```sh
unzip hardware/eeg128-tdm/engineering/latest-pcb.zip -d /tmp/eeg128-current
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-current/
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-current/eeg128-tdm.kicad_pcb
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-current/drc.json /tmp/eeg128-current/eeg128-tdm.kicad_pcb
```

## Nativer Kopfbericht

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T14:19:25+0500",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 179,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

> Historischer ADC6-Längencheckpoint. Aktuelle Via-Ausrichtung: ADC6_VIA_ALIGNMENT_2026-10-07.md.

# ADC6-Längenanpassung — 2026-10-07

**KiCad 8.0.9: 0 DRC-Verletzungen / 0 Warnungen / 179 offene Verbindungen.** ADC6-Kupferlängendifferenz: zuvor 7,002799 mm, jetzt <0,001 mm. Keine weitere Luftlinie geschlossen: weiterhin 102 MUX- und 77 Elektroden-/RC-Verbindungen. POWER, AGND, MUX_CONTROL, QSPI und BANK0_N_BUFFER bleiben geschlossen.

## Angenommene Kupfermutation

Nur die L4/B.Cu-Segmente von ADC6_N wurden ersetzt (13 entfernt, 23 hinzugefügt). Die L1-Traces, Pads, Netze, Vias und Designregeln bleiben unverändert. Leiterbahnbreite 0,15 mm; Faltungsraster 0,40 mm; 45°-Eckabschrägungen mit 0,10-mm-Schenkeln. Der neue L4-Pfad ist geometrisch einfach, ohne Selbstschnitt, und verbindet dieselben N-Vias (130,250 / 71,003443) und (133,500 / 68,626700) mm. Alle Eckpunkte stehen in `adc6-length-path.json`, alle UUID-gebundenen Änderungen in `adc6-length-recipes.json`.

| Paar | P-Kupferlänge mm | N-Kupferlänge mm | Differenz mm |
|---|---:|---:|---:|
| ADC6 | 19,246844151 | 19,246844226 | 0,000000074 |
| ADC7 | 11,190463331 | 11,190462468 | 0,000000862 |

Die Zahlen sind analytische Kupfer-Mittellinienlängen, ohne vertikale Via-Länge oder Ausbreitungszeitmodell. Die Faltung kompensiert die geometrische Länge, stellt aber keine kontrollierte Paarkopplung her. Insbesondere unterscheiden sich die Längenanteile auf L1/L4 zwischen P und N; gleiche Gesamt-Kupferlänge beweist keinen gleichen elektrischen Delay. Beide P/N-Ketten sind im auf 0,001 mm zusammengefassten Endpunktgraphen unverzweigt verbunden. Es wurden keine Schaltungs-Toleranzen erfunden oder globale DRC-Regeln gelockert.

ADC6 hat weiterhin je zwei Vias Ø0,60 / Bohrung0,30 mm. Die Übergänge bleiben versetzt: oben ΔX=7,638 mm / ΔY=0,708 mm; unten ΔX=6,407 mm / ΔY=3,396557 mm. Vollständige Paarsymmetrie bleibt **offen**. ADC7 bleibt gegenüber dem Eingang unverändert: P/N-Via-Y-Positionen stimmen überein, variable Abstände bleiben zu qualifizieren.

## Rückstrom, Kopplung und Guard-Anbindung

`audit_analog_return_geometry.py` prüft gefüllte Kupferprojektionen mit ≤0,05-mm-Abtastung. L2-AGND bleibt eine gefüllte Insel mit 149 Via-Kontakten; L3 enthält je eine angebundene Insel: 3V3A=39, 5V_ISO=8, 3V3D=23 Via-Kontakte. Keine dieser gefüllten Inseln ist ohne gleichnamigen Via-Kontakt.

Die Stichproben unter den L4-Mittellinien zeigen 85,60–91,95 % AGND-Kupfer auf L2. Antipads an Signal-Vias sind legitime Aussparungen; eine nicht bedeckte Probe beweist keinen Plane-Split. Die unmittelbar benachbarte L3-Referenz unter den L4-Signalen ist überwiegend **3V3A**:

| L4-Netz | Länge über gefülltem L3-3V3A mm | Länge ohne gefüllte L3-Zone mm |
|---|---:|---:|
| ADC6_P | 6,330 | 0,988 |
| ADC6_N | 10,611 | 1,031 |
| ADC7_P | 5,181 | 0,987 |
| ADC7_N | 6,995 | 0,988 |

L2-Kupferprojektion ist kein dreidimensionaler Rückstromnachweis. Die L3-Referenzwechsel, Entkopplungswege und lokalen AGND-Rückwege müssen noch elektrisch qualifiziert werden. Auf L4 liegen die abgetasteten ADC6-P/N-Mittellinienabstände bei ungefähr 5,37–8,55 mm; ADC7 bei 0,80–2,25 mm. Das ist keine durchgehend gekoppelte Paarführung. Die Auswertung schließt Pads/Vias aus und ersetzt keine Impedanz-/Kopplungsanalyse.

Ein geschlossener lokaler AGND-Guard wurde nicht hergestellt. Der Faltungskorridor wird durch BANK6_N- und ADC7_P-Trunks begrenzt; ein Guard benötigt eine eigene Kollisionsprüfung und gegebenenfalls deren Umbau. `return_current_qualified`, `pair_coupling_qualified` und `shielding_guarding_qualified` bleiben `false`.

## Weiterer Analogpass und Schaltplanparität

Ein separater, auf 120 s begrenzter Routingpass für CH060_MUX/CH061_MUX (beide P/N-Netze, 0,05-mm-Raster, L1/L4) hat keine weiteren Verbindungen geschlossen und wurde nicht übernommen. Der Restbestand bleibt 179.

Native Diagnose-Parität bleibt bei 0 Befunden; der erneute native XML-Export verifiziert alle 2.054 Pin-/Netzzuordnungen gegen das aktuelle Engineering-Board. Da der Diagnose-Schaltplan aus PCB-Daten erzeugt wurde, ist dies **kein unabhängiger LVS-PASS**. Die primären Schaltungsdateien wurden nicht durch den Diagnose-Schaltplan ersetzt. Für einen unabhängigen Signoff müssen die bereits dokumentierten 99 Wert-, 100 Footprint- und 199 Pad-Netzbefunde gegen eine unabhängige Schaltungsreferenz fachlich aufgelöst werden; eine erneute PCB-generierte Kopie kann diese Referenz nicht liefern. `schematic_parity_passed=false` bleibt bestehen.

## Prozess und reproduzierbarer Checkpoint

Mutation, Zonen-Fill und nativer DRC wurden in getrennten Prozessen ausgeführt. Ein unabhängiger Replay erzeugt dieselbe PCB bytegenau und weist 0/0/179 ohne Regression eines anderen Netzes nach. Die Löschfreigabe im Replay ist auf ADC6_N-L4-Segmente in `ADC6_LENGTH_GEOMETRY` begrenzt; ein ungescopter Löschversuch wurde zurückgewiesen. Das vorige Archiv bleibt als `adc6-length-baseline-179.zip` erhalten. Der aktuelle ZIP enthält genau PCB, Projekt und Regeln; der unveränderte Diagnose-Schaltplan liegt daneben.

`routing_completed=false`, `fabrication_release=false`. Primäre PCB-/Schaltplandateien, PUBLICATION_SHA256SUMS, BOM und CPL bleiben unverändert; keine Fertigungsartefakte erzeugt oder überschrieben.

Vom Repository-Root, mit installiertem KiCad-8-Python, kicad-cli, numpy und shapely:

```sh
unzip hardware/eeg128-tdm/engineering/adc6-length-baseline-179.zip -d /tmp/eeg128-adc6-base
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-adc6-base/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/adc6-length-recipes.json \
  --output-dir /tmp/eeg128-adc6-replay
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-adc6-replay/
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-adc6-replay/drc-parity.json /tmp/eeg128-adc6-replay/eeg128-tdm.kicad_pcb
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Ausgabeordner müssen neu sein. Der Replay führt vor und nach der Mutation einen separaten nativen Python-Zonen-Fill und DRC aus. Der direkte Fill-Befehl für eine separate Board-Kopie lautet:

```sh
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-adc6-replay/eeg128-tdm.kicad_pcb
```

## Nativer Kopfbericht

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T14:48:26+0500",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 179,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

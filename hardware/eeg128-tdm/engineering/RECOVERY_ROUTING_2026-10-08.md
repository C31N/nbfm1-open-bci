# Routing-Wiederherstellung – 2026-10-08

## Ergebnis und Herkunft

Der verfügbare 167er-Checkpoint wurde erneut nativ geprüft und auf **149 offene Verbindungen** reduziert. KiCad **8.0.9** bestätigt **0 geometrische DRC-Verletzungen, 0 Warnungen, 149 Unconnected Items**. Alle 149 Luftlinien betreffen unterschiedliche analoge Netze; die Begriffe Netze und Luftlinien stimmen nur für diesen geprüften Stand zahlenmäßig überein.

Die in der Übergabe genannten 138-/137er-Dateien waren nach der Wiederaufnahme weder lokal noch im verfügbaren Archiv wiederzufinden. Dieser Stand ist eine neue, überprüfte Rekonstruktion ab 167; er stellt keine Wiederherstellung der verlorenen 138-/137er-Geometrie dar. Historische Berichte vom 2026-10-07 bleiben als solche erhalten. `STATUS.json` und `drc-head.json` beschreiben den aktuellen Stand.

Das ursprüngliche Manifest ergab **117/118 Treffer**: `../route_targeted_closure.py` wich ab. Das 167er-PCB-Archiv war intakt; Originalmanifest und Baseline sind erhalten (`recovery167-original-manifest.txt`, `recovery-baseline167.zip`). Das neue Manifest bindet die tatsächlich verwendeten Skripte und aktuellen Artefakte.

## Fortschritt

| Gruppe | Baseline 167 | Neuer Stand | Geschlossen |
|---|---:|---:|---:|
| MUX | 95 | 78 | 17 |
| Elektroden/RC | 72 | 71 | 1 |
| POWER / AGND / MUX_CONTROL / QSPI | 0 | 0 | 0 |
| Gesamt | 167 | 149 | 18 |

- Block 1: `CH004_N_MUX`, `CH005_N_MUX`, `CH011_P_ELECTRODE` geschlossen; 0 MUX- und 8 Elektroden/RC-Luftlinien verbleiben.
- Block 2: P/N von CH016, CH017, CH019, CH021, CH022 und CH023 sowie CH025_N/CH026_N geschlossen. 9 MUX- und 8 Elektroden/RC-Luftlinien verbleiben.
- Block 3: `CH040_P_MUX` geschlossen. 9 MUX- und 11 Elektroden/RC-Luftlinien verbleiben.

Block-2-Rest: CH018_P/N, CH020_P/N, CH024_P/N, CH028_N, CH029_N und CH030_N_MUX. Versuche für CH018/CH020/CH028/CH029 schlossen teilweise das Signal, öffneten nach dem Zonen-Fill jedoch die **3V3A-Anbindung an U3** erneut und wurden verworfen. Die kritische L3-Zuleitung beginnt bei (33,515; 35,600) mm. Reservierte Versorgungskorridore verhinderten diese Regression, ließen im begrenzten Suchlauf aber keinen vollständigen Pfad zu. CH024 hat kein freies lokales Via-Fenster; CH030 bleibt am Ziel-Escape blockiert.

Block-3-Versuche für CH037_N, CH043_N und CH044_N fanden keinen akzeptierten Pfad. Die detaillierten Ergebnisse stehen in `recovery167-block2-search.json`, `recovery167-guard-search.json` und `recovery167-block3-search.json`. Suchpfade sind in `recovery167-accepted-paths.json` gespeichert; das gebundene Kupfer-Rezept ist die portable Reproduktionsautorität.

## Geometrie und offene Qualifizierung

Neue Signalbreite 0,15 mm, Through-Vias Ø 0,60 mm / Drill 0,30 mm, L1/L3/L4. Es wurden keine L2-Signalzüge hinzugefügt. Projektregeln, Footprints, Zonen-Umrisse sowie ADC6/ADC7-Kupfer bleiben gegenüber der Baseline unverändert. Die globale Clearance wurde nicht reduziert; das native DRC prüft die bestehenden Regeln einschließlich 0,20 mm gegenüber Referenz-/Power-Netzen.

Die neue L3-Signalführung verdrängt **207,659279781 mm²** bisheriges Power-Kupfer; 1,601882107 mm² werden lokal wiedergewonnen. Die Verlustfläche außerhalb des geprüften Bereichs X=5…86 / Y=5…65 mm beträgt 0,000000702 mm² und liegt innerhalb der 0,00001-mm²-Rundungstoleranz. Der explizite 250-mm²-Grenzwert ist eine interne Begrenzung dieses Engineering-Experiments, kein elektrischer Power-Integrity-Signoff. Der strengere 150-mm²-Versuch wurde überschritten und ist nicht als bestanden dargestellt.

Alle gefüllten Zoneninseln haben mindestens einen passenden Via-Kontakt; die Versorgung und AGND weisen nativ keine Luftlinien auf. Dies ersetzt keine Spannungsabfall-, Stromtragfähigkeits- oder Rückstromanalyse. Der Rückstrom-Audit zeigt L2-Abdeckungslücken und große P/N-Abstände; vollständige Guard-Ringe und Kopplung sind nicht qualifiziert.

ADC6 ΔKupferlänge = 0,000004107 mm, ADC7 = 0,000000862 mm. Je P/N liegen zwei Vias gleicher Geometrie mit 0 mm Y-Versatz vor. ADC6 hat weiterhin 8,2 mm P/N-Abstand der Via-Reihen. Gleiche Gesamt-Kupferlänge bedeutet keinen vollständigen Symmetrie-, Impedanz- oder Rückstrom-Signoff. Auch die gemeinsam geschlossenen MUX-Paare sind elektrisch angeschlossen, aber nicht kompakt gekoppelt oder auf <0,001 mm Skew qualifiziert; siehe `recovery167-pair-geometry.json`.

Die native Diagnose-Schaltplanparität hat 0 Befunde; der XML-Abgleich bestätigt alle **2.054** belegten Pin-/Netzzuordnungen. Dieser Schaltplan ist aus PCB-Daten erzeugt. Der unabhängige Primärschaltplan-LVS bleibt ausstehend; `schematic_parity_passed=false`.

## Nachweis und Reproduktion

Kupfermutationen und native Zonen-Füllung/DRC laufen in getrennten Kindprozessen. Das vollständige Rezept umfasst 283 geprüfte Entfernungen ausschließlich auf CH002_N_MUX/CH004_N_ELECTRODE plus die erforderlichen Wiederanschlüsse und neuen analogen Züge. Es schützt ADC, Power-Kupferobjekte, Netzzuteilungen, Layer, Breiten, Via-Geometrie und den räumlichen Umfang. Drei gezielte Tests bestehen; 14 schädliche Rezeptvarianten werden abgewiesen.

Replay und frisch entpacktes Archiv bestätigen identische PCB-/PRO-/DRU-Bytes. Nach nativem Zonen-Fill änderte sich kein Archiv-Mitglied. Die folgenden Befehle sind vom Repository-Root unter einer eingerichteten KiCad-8.0.9-Python/CLI-Umgebung auszuführen; jedes Prüfverzeichnis muss neu sein:

```bash
cd hardware/eeg128-tdm/engineering
sha256sum -c CHECKPOINT_SHA256SUMS
cd ..
/usr/bin/python3 -m unittest test_recovery167_replay test_routing_layer_constraints
/usr/bin/python3 verify_recovery167.py --output-dir /tmp/eeg128-recovery-verify-NEU
```

Der Verifier entpackt die erhaltene Baseline und den neuen Checkpoint, prüft alle Mitgliedshashes, führt native Prüfung und Replay in getrennten Prozessen aus und vergleicht alle drei Mitglieder byteweise. Keine Primär-PCB oder Fertigungsdatei wird beschrieben.

Einzelfill und DRC auf einer Arbeitskopie:

```bash
/usr/bin/python3 fill_zones.py /tmp/eeg128-arbeitskopie/eeg128-tdm.kicad_pcb
kicad-cli pcb drc --format json --severity-all --all-track-errors   --output /tmp/eeg128-arbeitskopie/drc.json   /tmp/eeg128-arbeitskopie/eeg128-tdm.kicad_pcb
```

KiCad 8.0.9 hat in der verwendeten CLI keinen `pcb fill-zones`-Unterbefehl. `fill_zones.py` nutzt `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` und erhält die Projektregeln.

## Release und Sicherung

`routing_completed=false`, `fabrication_release=false`, `drc_passed=false`, `schematic_parity_passed=false`. Primär-PCB und Fertigungspfad sind unverändert. Es wurden keine Gerber-, Drill-, Pick&Place-, BOM- oder Publikations-Manifeste erzeugt oder überschrieben.

Der neue Checkpoint wird in einem lokalen Git-Recovery-Branch und einem Git-Bundle gesichert. Ein Remote-Push wurde noch nicht ausgeführt. Die automatische Freigabeprüfung lehnte bereits den Push-Dry-Run wegen fehlender ausdrücklicher Autorisierung der Repository-/Ref-Metadatenübertragung ab.

Nächster Routing-Schritt: den 3V3A-U3-Zuführungsengpass bei CH018/CH020 durch koordinierte lokale Escape-Anpassung lösen, ohne Versorgung erneut zu öffnen; anschließend CH024-Via-Fenster und die restlichen RC-Escapes. Jeder Kandidat benötigt per-Netz-Regressionsprüfung, Zonen-Fill, natives DRC und die dokumentierte L3-Flächenkontrolle. Vor Fertigung sind 0/0/0 und die unabhängigen analogen/LVS-Qualifizierungen erforderlich.

### Gebundene Hashes

```text
PCB bb2b1bc7b3baeb3586a7d9c65246fcc80c666e38ebe3cc9cee89decebf8ffa0c
Archiv 71ffc3d06dd38d3c2c9434549f711e8356cba4ee8acaa54fb52f92140443c2b0
```

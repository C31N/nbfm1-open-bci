# Native Routing Closure — U23 POWER und Analog-Fortsetzung, 2026-10-07

**Gespeicherter, nach Zonen-Fill frisch geprüfter Stand: 0 Fehler / 0 Warnungen / 180 offene Verbindungen. Keine Fertigungsfreigabe.**

## Fortschritt seit 188

| Gruppe | Vorher | Geschlossen | Verbleibend |
|---|---:|---:|---:|
| POWER | 6 | 6 | 0 |
| AGND | 0 | 0 | 0 |
| TDM_ANALOG | 182 | 2 | 180 |
| MUX_CONTROL | 0 | 0 | 0 |

8 Luftlinien sind geschlossen; seit dem 265er-Ausgang insgesamt 85. Die Werte zählen Verbindungsdefizite, nicht generell unterschiedliche Netznamen. Alle übrigen Netze sind gegenüber dem 188er-Checkpoint unverändert angeschlossen. Die Änderungen sind lokal; bestehende Remote-CI-Ergebnisse sind kein Nachweis für diesen neuen Stand.

## U23: sechs POWER-Restverbindungen geschlossen

Alle neuen Vias sind Durchgangsvias F.Cu–B.Cu, Ø0,65 mm / Bohrung 0,30 mm, radialer Kupferring 0,175 mm. Es wurden keine Mikro-Vias eingesetzt. Die bestehenden Regeln bleiben unverändert: lokale U23-Power-Escapes 0,15 mm im Courtyard; Verteilung außerhalb dieser Ausnahme 0,30 mm; Power-/Referenz-Clearance 0,20 mm und CH-Clearance 0,15 mm.

| Anschluss | Neuer Via X / Y mm | Verbindung |
|---|---|---|
| 3V3D Pins48/49-Cluster | 170,475 / 74,5375 | Lokaler F.Cu-Escape aus Pin48 zum L3-3V3D-Kupfer |
| 3V3D Pin10 | 162,5875 / 77,775 | F.Cu-Neck mit breiterem äußeren Abschnitt, L3-Drop |
| 3V3D Pin1 | 163,7075 / 74,400 | F.Cu-Neck, L3-Drop; zwei lokale L4-Umwege |
| 3V3D Pin22 | 168,500 / 82,300 | F.Cu-Escape zwischen XOUT und neuem VREG-Escape, L3-Drop |
| VREG_1V1 Pin45 | 169,800 / 72,550 | F.Cu-Neck zur eigenen 0,30-mm-L3-Verbindung |
| VREG_1V1 Pin50 | 168,000 / 74,520 | F.Cu-Neck zur gleichen 1,1-V-Verbindung |
| VREG_1V1 Pin23, neu geführter Escape | 168,850 / 81,420 | Kurzer F.Cu-Escape; eigener L3-Abzweig |

VREG_1V1 besitzt keine Split-Power-Zone. Es wurde über eigene Leiterbahnen auf In2.Cu (L3) verbunden und nicht an 3V3D angeschlossen. Der Zone-Fill erzeugt die vorgeschriebenen Abstände zur umgebenden 3V3D-Fläche. Der alte VREG-Via (167,219999 / 82,537499) mm und seine Verbindung zu den Kondensatoren bleiben erhalten. Fünf frühere F.Cu-Segmente von Pin23 zu diesem Via wurden durch den neuen Escape ersetzt.

Der eigene L3-Trunk führt vom oberen VREG-Escape über (169,4 / 73,2), (168,8 / 75,0), (169,6 / 75,4), (170,3 / 75,8), den expliziten Abzweig bei (170,3 / 81,42), (170,3 / 83,3), (167,219999 / 83,3) zum alten VREG-Via. Seine Breite ist 0,30 mm. Der neue Pin50-Via ist bei (169,4 / 73,2) angeschlossen; der Pin23-Abzweig führt von (168,85 / 81,42) nach (170,3 / 81,42).

Lokale Freiräumungen:

- MUX_EN: L4-X von 163,194 auf 163,094 mm im U23-Pin1-Korridor; Endpunkte unverändert.
- XOUT_12M: L4-X von 164,145 auf 164,345 mm im gleichen Korridor; Endpunkte unverändert.
- USB_DM_IC: drei lokale Knoten um 0,12 mm nach links; USB_DP_IC: ein Knoten um 0,08 mm nach links. Pads bleiben unverändert.
- 3V3D Pin44: vorhandener Top-Escape wird nach rechts geführt; der padnahe Abschnitt bleibt innerhalb der lokalen 0,15-mm-Ausnahme.
- QSPI_SD2: kurzer L1-Umweg auf Y 75,149 mm zwischen X 167,3 und 169,2013 mm; alle vorhandenen Endpunkte bleiben erhalten.
- QSPI_CLK: kurzer L4-Umweg nahe seinem ursprünglichen Via (167,175 / 74,457) mm; danach Rückkehr auf die ursprüngliche Trasse. Seine Via-Position bleibt erhalten.

Alle sechs QSPI-Netze bleiben geschlossen, USB ebenfalls. Das EP-AGND-Via bleibt unverändert bei (166,85 / 78,15) mm mit L2-Kontakt. Verworfene Versuche an Pin22 mit Kupfer-/Bohrkollisionen sowie das alternative QSPI-Clock-Via wurden nicht übernommen. Einzelne Abstände liegen nur wenige Mikrometer über der Regelgrenze; Robustheit, Paarführung, Timing und Entkopplungsschleifen bleiben Engineering-Review-Punkte vor einer Fertigungsübernahme.

## TDM_ANALOG: getrennte Kanalgruppen und Zusammenführung

Nach POWER=0 wurden vier begrenzte Routing-Prozesse ausgeführt, mit 0,10- beziehungsweise 0,05-mm-Suchraster, L1/L4, bestehenden Kupfer-Ankern und unveränderten Neighbor-Clearances. Die ersten beiden Kanalgruppen brachten keinen Connectivity-Gewinn. Die weiteren Gruppen schlossen BANK6_N_BUFFER und CH049_P_MUX. Ein CH081_N_ELECTRODE-Kandidat mit drei Clearance-Verletzungen wurde verworfen.

Die beiden angenommenen Analogzweige wurden relativ zum gemeinsamen 182er-POWER-Stand über `merge_native_closure.py` zusammengeführt. Frischer nativer DRC und ein Vergleich der Luftlinien pro Netz bestätigen den Gewinn; kein geschlossenes Power-, AGND-, MUX-, USB- oder QSPI-Netz wurde wieder geöffnet. Der Supervisor und die Kandidaten-Pipeline besitzen zusätzlich einen Netz-Regressionsguard: Eine kleinere Gesamtsumme darf keine neue Luftlinie eines anderen Netzes verbergen.

`supervisor-validation.json` enthält alle vier Worker-Endstände, die Zusammenführung und den separaten Rezept-Replay. Die restlichen 180 Analog-Luftlinien bleiben reale Abschlussblocker; die Versorgungsschließung erzeugt keine automatische Analog-Schließung.

## Reproduzierbarer U23-Replay

`power-baseline-188.zip` enthält den geprüften Eingang dieses Passes. `rp2040-power-recipes.json` bindet sämtliche Kupfer-Mutationen an die SHA-256 von PCB, Projekt und Custom-Rules des 188er-Standes. Es umfasst 77 Änderungen, darunter fünf explizit ersetzte VREG-Segmente. Regeln, Footprints und Pads werden nicht verändert. Das Rezept darf nicht erneut auf das aktuelle ZIP angewendet werden.

```bash
mkdir -p /tmp/eeg128-power188
unzip hardware/eeg128-tdm/engineering/power-baseline-188.zip -d /tmp/eeg128-power188
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-power188/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/rp2040-power-recipes.json \
  --output-dir /tmp/eeg128-power-replay
```

Der Replay ist separat mit KiCad 8.0.9 nachgewiesen: 188→182, 0 Violations, 0 Warnings, keine Netz-Regressionsluftlinien. Mutationen laufen in einem eigenen Prozess; Refill/DRC danach in einem frischen Prozess. `replay-result.json` liefert den Nachweis.

## Zonen und Hardware-Identität

| Netz | Layer | Gleichnamige Via-Kontakte |
|---|---|---:|
| AGND | In1.Cu | 149 |
| 3V3A | In2.Cu | 39 |
| 5V_ISO | In2.Cu | 8 |
| 3V3D | In2.Cu | 23 |

Alle vier Zonen besitzen jeweils eine gefüllte Insel mit Via-Kontakt. Keine Insel ohne Kontakt; keine L1-/L4-Zonen. Alle 642 Bestückpositionen und die kritischen Pinouts/Landpatterns bestehen die Identitätsprüfung. Dies ersetzt nicht den fehlenden 0/0/0-Abschluss.

## Nativer DRC-Kopf und Checkpoint-Verifikation

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T00:32:38-0500",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 180
}
```

Ab Repository-Wurzel, mit KiCad 8 und seinem pcbnew-Modul:

```bash
mkdir -p /tmp/eeg128-current
unzip hardware/eeg128-tdm/engineering/latest-pcb.zip -d /tmp/eeg128-current
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-current/eeg128-tdm.kicad_pcb
kicad-cli pcb drc --format json --severity-all --all-track-errors \
  --output /tmp/eeg128-current/drc.json /tmp/eeg128-current/eeg128-tdm.kicad_pcb
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der KiCad 8.0.9-CLI besitzt keinen `pcb fill-zones`-Unterbefehl. `fill_zones.py` verwendet `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` und bewahrt die Projektdatei. Exitcode 5 bei verbleibenden Luftlinien ist kein 0/0/0-PASS.

## Release-Gate

`routing_completed=false`, `fabrication_release=false`. Die primäre PCB im Fertigungspfad bleibt unverändert. `PUBLICATION_SHA256SUMS`, Gerber, NC Drill, Pick&Place und BOM wurden nicht erzeugt oder überschrieben. Ausschließlich das Engineering-Checkpoint-Manifest wird aktualisiert.

Erst nach 0/0/0 und Promotion der validierten PCB in den Fertigungspfad folgen `generate_manufacturing.py`, die Release-Manifest-Generierung und dessen Verifikation. Dieser Stand wird nicht als Fertigungsfreigabe veröffentlicht.

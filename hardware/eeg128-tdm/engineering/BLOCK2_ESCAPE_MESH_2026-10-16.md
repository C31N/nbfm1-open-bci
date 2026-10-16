<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: weitere Escape-Suche auf dem 139er-Stand

**Keine weitere Luftlinie geschlossen. Der bestätigte Routing-Checkpoint bleibt bei 139.**
CH018_P_MUX und CH021_N_ELECTRODE bleiben offen. Eine zusätzliche vollständige
MUX_S1-Nachbarumlegung ist nativ geprüft und unabhängig byteidentisch replayt;
sie bleibt ausdrücklich `accepted=false`. Es wurden keine Fertigungsdaten erzeugt.

Die Eingangsdateien entsprechen exakt Commit `437b37f`:

- Basis-ZIP: `f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b`.
- Basis-PCB: `f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea`.

Der bestehende Diagnose-Branch bis `32496d2` mit den c22-/c26-Prüflingen wurde
als Codebasis übernommen. Die neuen Untersuchungen verwenden weiterhin das
unveränderte 139er-Archiv; frühere Replays und CI-Prüfungen bleiben erhalten.
`current-routing-status.json` und die Release-Dateien werden nicht umgestellt.

## U3: vollständige MUX_S1-Umlegung ohne neue Vias

Der P-Zielpad ist **U3.7, (41,135 / 45,150) mm**. CH018_N_MUX endet dagegen
an U4.7. Die Endpunkte werden nicht vertauscht.

Fünf F.Cu-Segmente der horizontalen MUX_S1-Brücke zwischen den U1-/U3-Zweigen
werden durch vier F.Cu-Segmente ersetzt. Der Ersatz nutzt die bestehenden
S1-Übergänge bei (22,515 / 43,550) und (46,115 / 43,550) mm. Im verwendeten
F.Cu/B.Cu-Suchmodell war kein durchgehender reiner B.Cu-Ersatz gefunden worden;
der vollständige geometrische Ersatz verläuft über F.Cu. Neue oder entfernte
Vias: **0**.

| Prüfung der Diagnosevariante | Ergebnis |
| --- | --- |
| Native KiCad-Version | 8.0.9 |
| DRC-Fehler / Warnungen / offene Verbindungen | 0 / 0 / 139 |
| Paritätsbefunde / Netzregressionen | 0 / keine |
| L3-Power-Verlust / -Zugewinn | exakt 0,0 / 0,0 mm² |
| Footprints, Zonenaußenkonturen, Projekt-/DRC-Regeln | unverändert |
| PCB- und ZIP-Replay | byteidentisch |
| Als neuer Routingstand übernommen | nein |

Der im Suchfenster modellierte erreichbare F.Cu-Bereich des P-Ziels vergrößert
sich von rund 10,099 auf 68,233 mm². Die Fläche für neue Vias außerhalb der
vollständigen Power-Zonenkonturen bleibt jedoch **0,0 mm²**. Die Umlegung
allein löst den Ziel-Escape nicht und ersetzt deshalb keinen Checkpoint.

Diagnose-PCB SHA-256:
`56b616fbca7bf5d9f14c75146a569fe23af904e7876800361a1e529f324c96de`.
Diagnose-ZIP SHA-256:
`82da4d4838f9128a97f27860c91a1d6b81bbbbf4c3610ed7554afdde7183f33e`.
Das ZIP liegt gesondert als `followup-2026-10-16-escape139/mux-s1-unadopted139.zip`.

Die gemeinsame lokale Entfernung der S0-/S1-Brücken wurde zusätzlich mit
vollständigen Ersatzanforderungen modelliert. Dieser begrenzte Versuch lieferte
keinen vollständigen P-Pfad. Weitergehende Zwei-Netz-Entfernungsmodelle zeigen
zwar Fenster, unter anderem bei S1 zusammen mit S2/S3. Sie enthalten entfernte
Nachbarverbindungen und sind keine übernehmbaren Korridore.

## CH021-N: vollständige Nachbar-Restitution weiterhin offen

Quelle: R300.1, (36,150 / 18,200) mm. Ziel: J2.22, (43,250 / 7,600) mm.
Die native `pad_copper_shape()`-Modellierung bleibt aktiv. Untersucht wurden:

- 22 gemeinsame Ersatzmodelle mit CH026-P oder CH027-P an der Quelle und
  CH019-N, CH022-N oder CH023-N am Header, unterschiedlichen Routingreihenfolgen
  und F.Cu/B.Cu- beziehungsweise F.Cu/In2.Cu-Nachbarführungen.
- Drei lokale Varianten mit erhaltenen Pad-Escapes und Ersatz der sperrenden
  Mittelstücke von CH027-P und CH023-N.
- Drei Varianten mit vorab reserviertem CH023-N-Header-Escape zum Via-Vorschlag
  (50,4762 / 8,808369) mm; die letzte prüft B.Cu/In2.Cu für die Nachbartrunks.

CH021 selbst besitzt in mehreren Modellen einen vollständigen F.Cu/In2.Cu-Pfad.
Es gelang jedoch keine gleichzeitige Wiederherstellung aller betroffenen Netze.
Beim reservierten rechten CH023-Header gelingt dessen F.Cu-Anbindung und der
CH021-Pfad; die CH023-Verbindung vom vorhandenen Quell-Via zum rechten Übergang
bleibt unvollständig. Die Varianten bleiben `accepted=false`; aus ihnen wurde
kein neuer PCB-Checkpoint gespeichert oder freigegeben.

Die 29 dokumentierten gemeinsamen Modellfälle einschließlich des MUX-Versuchs
enthalten **keinen vollständigen gemeinsamen Abschluss**. Endliche Via-Samples,
Suchfenster und konservative Geometriemargen begrenzen diese Aussage; eine
globale Unroutbarkeit ist daraus nicht ableitbar.

## Modell, Replay und Prüfung

`escape_mesh.py` ergänzt optionale Vorschläge über eine beschränkte
Triangulierung mit Shapely 2.1.2. Das Modell verwendet unveränderte 0,15-mm-Tracks,
die bestehende Clearance-/Pad-/Randmodellierung und ausschließlich F.Cu, In2.Cu
oder B.Cu. Neue Via-Mittelpunkte halten 0,505 mm Abstand zu den vollständigen
L3-Power-Außenkonturen; neue In2.Cu-Tracks werden zusätzlich von diesen Konturen
ferngehalten. Vorhandene Durchkontaktierungen dürfen exakt wiederverwendet werden.
Das Modell ersetzt keinen nativen DRC.

`replay_139_escape_diagnostic.py` prüft ein SHA-gebundenes Rezept, erlaubt
nur die bezeichneten F.Cu-S1-Tracks und verbietet neue Vias. Frische native
Zonenfüllung, DRC, Parität, exakte Kupfer-/Footprint-/Regelvergleiche, beide
Power-Differenzen und erwartete PCB-/ZIP-Hashes sind Pflicht. Das Ergebnis
bleibt auch bei bestandenen Prüfungen `accepted=false`.

```sh
/usr/bin/python3 hardware/eeg128-tdm/replay_ch019_electrode.py \
  --output-dir /tmp/verified139
/usr/bin/python3 hardware/eeg128-tdm/replay_139_escape_diagnostic.py \
  --output-dir /tmp/s1-diagnostic139
```

Beide nativen Replays sind in dieser Untersuchung erfolgreich ausgeführt worden.
Die Standardumgebung besteht 45 Tests und überspringt fünf optionale Mesh-Tests;
mit dem optionalen Mesh-Runtime bestehen **alle 50 Tests**. Die CI ergänzt fünf
Diagnose-Schutztests und den neuen nativen Replay samt Exportkontrolle.
Ein neuer Online-CI-Erfolg wird hier nicht vorweggenommen.

Rohberichte, Modellzusammenfassung, Rezept und Planungsarchiv liegen in
`followup-2026-10-16-escape139/`. `ESCAPE_MESH139_2026-10-16_SHA256SUMS` bindet
alle neuen Nachweise und die unveränderte Basis. `routing_completed=false` und
`fabrication_release=false` bleiben durchgesetzt. Es wurden keine Gerber-,
Drill-, CPL- oder BOM-Dateien erzeugt.

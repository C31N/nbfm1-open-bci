<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: sieben MUX-Escapes und konservative Drei-Lagen-Suche

**Keine weitere Luftlinie ist geschlossen.** Zwei vollständige Nachbar-Umlegungen
und ihre gemeinsame Variante sind nativ sauber und byteidentisch replayt.
Der diagnostische Stand bleibt bei 137 Luftlinien, davon sieben MUX-Netze in
Block 2 und keine offene Block-2-Elektrodenverbindung. Alle neuen Prüflinge
bleiben `accepted=false`, `routing_completed=false`, `fabrication_release=false`.
Der bestätigte 139er-Checkpoint und die primäre Platine werden nicht ersetzt.

Die Basis ist der gemeinsame 137er-Prüfling aus `f04ec78`:
ZIP SHA-256 `50e62977c202838640dfb00a6580f1e010c71503711e8a8fb85c7244a9d4a6f3`,
PCB SHA-256 `8d25968ffff8564334a4ba21c45c25b58dece7b27e2ca77be6118eb28817b187`.
Die vollständigen Replays der 139er-Basis und der daraus erzeugten
137er-Diagnose wurden erneut erfolgreich ausgeführt; beide PCB-/ZIP-Paare
bleiben byteidentisch zu den zuvor bestätigten Hashes.

## Vollständige native Präparationen

| Prüfling | Geändertes Netz | Fehler / Warnungen / Luftlinien | Parität | Power-Verlust / -Zugewinn |
| --- | --- | --- | --- | --- |
| S0-Dogleg | MUX_S0 | 0 / 0 / 137 | 0 | exakt 0,0 / 0,0 mm² |
| CH024-P-Zielfenster | CH025_P_MUX | 0 / 0 / 137 | 0 | exakt 0,0 / 0,0 mm² |
| Gemeinsame Präparation | beide | **0 / 0 / 137** | **0** | **exakt 0,0 / 0,0 mm²** |

KiCad 8.0.9 bestätigt alle drei Varianten. Die Netzprüfung findet keine
Regression. Footprints, Zonenaußenkonturen, Projekt- und DRC-Regeln bleiben
unverändert. Sämtliche tatsächlichen Änderungen liegen auf F.Cu;
**kein Via und kein In2.Cu-Segment wird hinzugefügt, verschoben oder entfernt**.
Die unabhängige Randprüfung bestätigt die 0,25-mm-Kupferfreihaltung.

MUX_S0 erhält zwischen den U2-/U4-Padanbindungen einen unteren F.Cu-Dogleg
über (33,0 / 61,0) mm. 27 alte Segmente werden durch sieben ersetzt.
Der von CH020_N am Ziel erreichbare F.Cu-Bereich wächst nach vollständiger
Restitution von **36,1980 auf 73,4818 mm²**. Die freie Via-Fläche bleibt
**0,0 mm²**: Die Korridorvergrößerung allein schließt den Ziel-Escape noch nicht.
Die gesamte S0-Länge steigt um 12,6418 mm; seine 13 Vias bleiben erhalten.

CH025_P erhält einen vollständigen neuen F.Cu-Escape zwischen dem vorhandenen
Via (34,055 / 33,299999) mm und seinem U3-Pad (36,055 / 35,85) mm.
Zehn alte Segmente werden durch drei ersetzt. Eine virtuelle Reservierung für
den späteren CH024-P-Zielpfad wurde bei der Suche berücksichtigt, aber
**kein CH024-P-Kupfer und kein reservierter Via werden im Prüfling angelegt**.
Nach der tatsächlichen Restitution steigt der CH024-P-Zielbereich von
3,1497 auf **27,0692 mm²**. Die freie Via-Fläche beträgt **1,057013144063 mm²**:

| Fenster-Mittelpunkt | Fläche |
| --- | --- |
| (28,487500 / 34,700000) mm | 0,591249995150 mm² |
| (32,825000 / 33,635907) mm | 0,459813114323 mm² |
| (29,692500 / 32,290000) mm | 0,005950034590 mm² |

CH025-P wird lediglich um 0,4068 mm länger; seine sieben Vias bleiben erhalten.
Die gemeinsame Variante enthält die Vereinigung dieser disjunkten Änderungen:
37 alte Segmente entfallen, zehn neue F.Cu-Segmente kommen hinzu.
Laufzeit, Impedanz, Übersprechen und analoges Settling sind nicht qualifiziert.

## Vollständige Quell-/Ziel-Kartierung der sieben offenen Netze

Die Tabelle beschreibt die unveränderte 137er-Basis mit echten nativen
Padkonturen. Alle Ziel-Fenster sind zunächst leer. Region:
X=12…59 / Y=0,5…69 mm; Via-Mindestmaß 0,60/0,30 mm.

| Netz | RC-Quelle | MUX-Ziel | Quell-Via-Fläche | Ziel-Via-Fläche |
| --- | --- | --- | --- | --- |
| CH020_N_MUX | R42.1 (38,25 / 20,80) | U4.5 (38,595 / 58,15) | 0,0 mm² | 0,0 mm² |
| CH020_P_MUX | R41.1 (32,75 / 20,80) | U3.5 (38,595 / 45,15) | 2,6076 mm² | 0,0 mm² |
| CH024_N_MUX | R50.1 (48,75 / 13,00) | U4.23 (34,785 / 48,85) | 0,0 mm² | 0,0 mm² |
| CH024_P_MUX | R49.1 (43,25 / 13,00) | U3.23 (34,785 / 35,85) | 0,0 mm² | 0,0 mm² |
| CH028_N_MUX | R58.1 (48,75 / 23,40) | U4.19 (39,865 / 48,85) | 1,1936 mm² | 0,0 mm² |
| CH029_N_MUX | R60.1 (48,75 / 26,00) | U4.18 (41,135 / 48,85) | 1,2833 mm² | 0,0 mm² |
| CH030_N_MUX | R62.1 (48,75 / 28,60) | U4.17 (42,405 / 48,85) | 0,0897 mm² | 0,0 mm² |

CH020-P und CH028-/CH029-/CH030-N teilen denselben durch Nachbar-Kupfer
begrenzten F.Cu-Zielbereich. Das frühere CH018-P-Fenster ist durch dessen
vollständige 137er-Führung belegt; seine bloße Existenz in der vorherigen
Kontroll-Diagnose erlaubt keinen weiteren unabhängigen Via-Drop.

## Nachbar-Modelle und sequenzielle Pfadversuche

Alle folgenden Entfernungsmodelle sind hypothetisch. Sie besitzen keine
vollständig restituierten Nachbarn und werden ausdrücklich nicht als native
Routing-Kandidaten oder Fortschritt im Luftlinien-Zähler ausgegeben.
Die maßgeblichen Modelle wurden erneut jeweils auf einer frischen,
SHA-gepinnten PCB-Instanz ausgeführt.

- Das Entfernen von CH031_N_MUX öffnet im gemeinsamen Zielbereich
  2,405531503696 mm²; das Entfernen von CH000_N_MUX öffnet
  0,574718572878 mm². Nach dieser Freilegung werden vollständige Pfade
  für einzelne neue Netze gefunden, aber die anschließende Wiederherstellung
  von CH031-N beziehungsweise CH000-N scheitert in den untersuchten Varianten.
- CH028-/CH029-/CH030-N werden mit F.Cu/B.Cu, F.Cu/In2.Cu sowie allen drei
  Signallagen geprüft. Separat reservierte Quell-/Ziel-Enden und verschiedene
  Reihenfolgen verhindern bislang keine Blockade bei der Nachbar-Restitution.
- Bei CH020-N öffnet weder einer der neun einzeln entfernten Ziel-Nachbarn
  noch die Mehrzahl der geprüften Paare ein Via-Fenster. Von den 18 gezielten
  Zweiermodellen sind nur CH000-N + MUX_S0 beziehungsweise CH031-N + MUX_S0
  positiv. Die Ergebnisse betragen 0,5747 beziehungsweise 2,4055 mm².
  Die Quelle bleibt dabei weiterhin blockiert. Hypothetische Eingriffe an
  CH025-P beziehungsweise CH026-P öffnen dort 2,0204 beziehungsweise
  5,8477 mm². Eine vollständige CH020-N-Lösung benötigt damit mehrere
  koordinierte Änderungen, nicht nur den qualifizierten unteren S0-Dogleg.
- CH024-P wird an der Quelle durch Elektrodenführungen begrenzt.
  Das Entfernen von CH022_N_ELECTRODE öffnet dort 1,8174 mm²,
  alternativ CH019_N_ELECTRODE 0,5263 mm². Nach dem qualifizierten
  CH025-P-Ziel-Escape werden sowohl Quell- als auch Ziel-Endpfade zu
  getrennten Vias gefunden. In vier Varianten fehlt jedoch der vollständige
  zusätzliche Trunk oder die CH022-N-Restitution. Keine Variante wird übernommen.
- Das konservative kontinuierliche Drei-Lagen-Komponentenmodell bestätigt
  für diesen vorbereiteten CH024-P-Versuch die Trennung der Enden.
  Von zwölf einzelnen MUX-Lagen-Entfernungen verbinden nur die
  In2.Cu-Entfernungen von CH018_N_MUX oder CH019_P_MUX die Komponenten.
  Das sind Ansatzpunkte für eine spätere lokale Trunk-Umlegung; die
  vollständige Wiederherstellung dieser Nachbarn ist noch nicht nachgewiesen.
- CH024-N besitzt an beiden Enden kein Via-Fenster. Seine Quelle wird durch
  Elektroden-Escapes begrenzt: hypothetische Entfernungen von CH026-N,
  CH030-N oder CH031-N_ELECTRODE öffnen 9,0370 / 0,6014 / 1,4083 mm².
  Am Ziel helfen die separat entfernten CH025_N_MUX, CH027_N_MUX und MUX_S3
  nicht. Eine reine MUX-Umlegung löst die Quellblockade nicht.

Dies sind begrenzte konservative Suchergebnisse, kein Nachweis globaler
Unroutbarkeit. Ein unvollständiges Modell wird nicht als PCB gespeichert,
als nativ bestanden gezählt oder zum bestätigten Checkpoint erklärt.

## Verschärfte Such- und Replay-Gates

`escape_mesh_505.py` erlaubt zwei oder drei verschiedene Signallagen aus
F.Cu/B.Cu/In2.Cu. **Neue In2.Cu-Mittellinien und neue Via-Mittelpunkte bleiben
außerhalb der vollständigen 0,505-mm-Power-Sperre.** Bestehende Zone-Voids
werden nicht ausgenutzt. Ein zusätzlicher 5-nm-Suchabstand schützt gegen
Koordinatenrundung. Die bestehenden Suchmodelle der früheren Checkpoints
werden nicht nachträglich gelockert oder umdefiniert. Board-Outline und
0,25-mm-Randfreihaltung bleiben in den Hindernissen aktiv.

Sieben neue Mesh-Tests prüfen unter anderem den strengeren In2-Abstand und
synthetische Fälle, die tatsächlich alle drei Signallagen benötigen.
Für jeden Einzelprüfling wurden alle bisherigen 70 Hardware-Schutztests
und weitere neue Tests ausgeführt: je 87 PASS. Der gemeinsame Prüfling
besteht abschließend **92 isolierte Hardware-Tests**: dieselben 70 plus
sieben Mesh- und 15 Replay-Guards. Root-pytest: 21 PASS / 3 SKIP.
Ruff, Zero-Debt, Hardware-Identität, EDA-Integrität und der gesperrte
Fertigungsexport werden geprüft. Keine Gerber-, Drill-, CPL- oder BOM-Datei
wurde erzeugt.

`replay_mux137_followup.py --case s0|p25|joint --output-dir NEUES_VERZEICHNIS`
prüft die gepinnte 137er-Basis nativ, wendet die überprüften Kupferblöcke
in einem eigenen Prozess an und prüft anschließend separat Zonenfill/DRC,
Parität, exakte geschützte Geometrie sowie byteidentische PCB-/ZIP-Hashes.
Die Guard-Tests lehnen neue Vias, andere Netze/Lagen und geänderte
Release-Flags vor dem Schreiben ab. Alle drei Replays sind in der nativen
CI verdrahtet.

Gemeinsames PCB SHA-256:
`cac02064d9926676f6368536c4c104cb36295961333de6074e65fa1fa60a814c`.
Gemeinsames ZIP SHA-256:
`a3e476707113761a4f042793f1711884635d740ee4871729f0afe2e4e37bf041`.

Alle qualifizierten Replays, Rezepte, Einzel-Hashes, Testübersichten,
Fensterdaten und archivierten Suchquellen liegen unter
`followup-2026-10-16-mux137/`. Die neue SHA-256-Manifestierung bindet sie
an die Prüfprogramme, den nativen Workflow und beide unveränderten Basen.

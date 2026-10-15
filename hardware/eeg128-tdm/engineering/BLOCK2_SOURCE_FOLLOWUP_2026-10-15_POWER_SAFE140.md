<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: Power-sicherer 140er-Checkpoint, 2026-10-15

**Korrektur der späteren Korridoranalyse:** Die drei aus der analytischen
CH030-Entfernung abgeleiteten Via-Fenster sind kein belegter Korridor.
Die Randmaske fehlte im direkten geometrischen Modell. Der akzeptierte
140er-Checkpoint ist unverändert nativ gültig. Details und korrigierte Evidenz:
[EDGE_SAFE140](BLOCK2_SOURCE_FOLLOWUP_2026-10-15_EDGE_SAFE140.md).


CH025_P_ELECTRODE ist geschlossen. Der unabhängig wiederholte Replay von 141 auf
140 offene Verbindungen liefert unter nativem KiCad 8.0.9 exakt 0 DRC-Fehler,
0 Warnungen, 0 diagnostische Paritätsbefunde sowie 0.0 mm² L3-Power-Verlust und
0.0 mm² L3-Power-Zugewinn. Es wird keine numerische Toleranz verwendet.

## Übernommene Mutation

Die F.Cu-Diagonale von CH026_P_ELECTRODE, UUID
`52f206ab-0d20-407f-971a-f947abc4828a`, von (34.4548,11.5894) nach
(37.7500,8.2942) wurde durch einen vollständigen F.Cu-Pfad ersetzt.
Damit erhält CH025_P_ELECTRODE von (41.1500,15.6000) nach J2.10
(37.2500,7.6000) einen durchgängigen F.Cu/In2.Cu/F.Cu-Pfad.
Die beiden neuen Durchkontaktierungen liegen bei (43.599999,14.230000) und
(36.000000,9.400000), Durchmesser 0.6 mm, Bohrung 0.3 mm.
Die signalseitige Leiterbahnbreite beträgt 0.15 mm. Alle neuen Via-Positionen
liegen oberhalb der L3-Power-Region. Die exakten Segmente, UUIDs und Netzcodes
sind im SHA-256-gebundenen `ch025e140-recipe.json` festgeschrieben.

Ein vorhandenes Kupferobjekt wird ersetzt; 214 Kupferobjekte werden hinzugefügt.
Der neue Pfad von CH026 bleibt vollständig verbunden. Keine zuvor geschlossene
Verbindung wird geöffnet. Footprints, Zonenaußenkonturen, Projektregeln und
DRC-Regeln sind unverändert. Neue Vias werden vor dem Speichern auf elektrische
Anbindung an mindestens zwei Kupferlagen geprüft.

## Reproduzierbarkeit und Prüfung

`replay_ch025_electrode.py` prüft zunächst das unveränderte 141er-Archiv,
startet die Mutation als separaten `--apply-only`-Prozess und wartet auf dessen
Ende. Anschließend folgen unabhängige Prozesse für Zonenfüllung/DRC und
schematische Parität. Das gefüllte L3-Power-Kupfer wird geometrisch mit dem frisch
gefüllten Ausgangsstand verglichen. Der unabhängige Replay erzeugt byteidentisch
das geprüfte PCB und das reproduzierbare Engineering-Archiv.

- Ausgang: `block2-ch029-electrode-closed141.zip`, SHA-256
  `a69aadf1bdd2436aadd7b9ae80e2796f1b5937b816389b44a11582685b2699a1`.
- Ergebnis: `block2-ch025-electrode-closed140.zip`, SHA-256
  `06817fef09feb864a8ef96a93e60034bb5aec7b8baecfe350ae0277a25a424b4`.
- PCB SHA-256:
  `d95f88c9e58766600eb536a38fb3d7e72241d370d998b16c18a703bc9da4f25f`.

Die CI führt zusätzlich zu den beiden bisherigen Replays den neuen 141→140-Replay
und seine fünf Negativ-/Integritätsprüfungen aus. Alle drei Replay-Verzeichnisse
unterliegen der Sperre gegen Fertigungsexporte. Native Rohberichte, Geometrie,
Inventar, vollständiger Routingplan und Replay-Ergebnis liegen unter
`followup-2026-10-15-power-safe140/`.

## CH018_P und verbleibende Elektroden

CH018_P_MUX bleibt offen. Die vorhandene F.Cu-Endpunkttasche besitzt nach der
untersuchten MUX_S1-/VCM-Umlegung kein neues Via-Fenster außerhalb der
L3-Power-Zonenkontur. Frühere mikroskopische Antipad-Verluste bleiben verworfen.
Weitere kombinierte Modelle untersuchten CH019_P_MUX-Trunktausch und VCM-
Busbrücken. Kein vollständiger kurzer CH018-P-Kandidat ist nativ qualifiziert.
Eine geometrische Referenz für den umgelegten CH019-P-Rückweg erreicht rund
166.24 mm, davon 127.79 mm auf L3. Diese Referenz wird wegen der erheblichen
Umweglänge und fehlender vollständiger Qualifikation nicht übernommen.
Isolierte Vias und unvollständige Nachbarnetz-Umlegungen sind nicht Bestandteil
des Checkpoints.

Für CH021_N_ELECTRODE liegt ein potenzielles Quell-Via-Fenster bei
(35.600,17.275), dessen L3-Korridor durch CH022_N_MUX blockiert ist. Die
untersuchten F.Cu/B.Cu-Ersatzrouten für diese Begrenzung blieben unvollständig.
CH019_N_ELECTRODE benötigt zusätzlich eine vollständige Umlegung des begrenzenden
CH018-N-Elektrodenpfads und einen nachgewiesenen Header-Korridor. Die modellierten
Via-Positionen nahe J2 wurden wegen Nachbarkupfer verworfen. Diese Koordinaten
sind Analysebefunde, keine freigegebenen Mutationen.

Es verbleiben 75 MUX- und 65 Elektroden/RC-Verbindungen. In Block 2 sind acht
MUX-Verbindungen sowie CH019_N_ELECTRODE und CH021_N_ELECTRODE offen.
`routing_completed=false`, `fabrication_release=false`. Der primäre historische
Pre-Route-Stand wird nicht ersetzt. Keine Gerber-, Drill-, CPL- oder BOM-Dateien
wurden erzeugt. Dieser Stand ist ein Engineering-Checkpoint, keine Fertigungsfreigabe.

## Zusätzliche CH018-P-Korridoranalyse nach Veröffentlichung des Checkpoints

Der 140er-Checkpoint wurde als `a9dcedcdefb47a136862894a81ec46fe8a7c64d6`
veröffentlicht. Alle drei Workflows sind erfolgreich: CI (38793755550),
Native KiCad 8 Validation (38793755531), Materialize EDA Connectivity Schematic
(38793755575). Die native CI bestätigt alle drei Replays bis 140 byteidentisch,
15 Replay-Integritätsprüfungen und die Fertigungssperre. Der Neuro-Job bestätigt
27 Python-Tests und zwei Rust-Tests.

Ein zusätzlicher vollständiger Ersatz der beiden langen CH017-N-Elektroden-
B.Cu-Segmente zwischen den vorhandenen Vias (37.583,27.349) und
(38.5302,11.5885) wurde getrennt angewendet und nativ geprüft. Der gefundene
16.150081-mm-Pfad bleibt vollständig auf B.Cu und benötigt keine neuen Vias.
Das Prüf-PCB hat SHA-256
`3db9417fe047a2eca5df3c960992f923b3ef0b6e51bbfab78f45e10fec78f5cf`.
Es erreicht 0 Fehler / 0 Warnungen / 140 Luftlinien / 0 Paritätsbefunde und
exakt 0.0 mm² Power-Verlust/-Zugewinn. Footprints, Regeln und Zonenaußenkonturen
sind unverändert, kein Netz regressiert. Der Kandidat wird nicht übernommen:
Er reduziert die Luftlinien nicht und weist noch keine vollständige CH018-
Korridoröffnung nach. Der akzeptierte Stand bleibt das CH025-140er-Archiv.

Die geometrische Vergleichsanalyse für die CH022-N-Quell-Anbindung verwendet
das ausdrücklich unvollständige CH019-P-Trunktausch-Modell; insbesondere die
CH027-N-Rückführung ist darin noch nicht wiederhergestellt. Sie ist daher keine
elektrische oder native Freigabe. Mit erhaltenen Begrenzungen gibt es weder
einen direkten Via-Tap auf dem erhaltenen CH022-L3-Trunk noch ein zulässiges
Via-Fenster für einen L3-Stich aus der B.Cu-Quelltasche.

Sieben kontrollierte Vergleichsmodelle entfernen ausschließlich zur Analyse
die B.Cu-Segmente von CH017_N_ELECTRODE, CH018_N_ELECTRODE und/oder
CH030_P_ELECTRODE. Die vorhandenen Vias bleiben erhalten. Die jeweils nicht
wiederhergestellten Nachbarnetze machen diese Modelle unvollständig:

| Analytisch entfernte B.Cu-Strecken | Gemeinsame zulässige Via-Fläche mm² | Fenster |
| --- | ---: | ---: |
| CH017 N | 0.0 | 0 |
| CH018 N | 0.0 | 0 |
| CH030 P | 0.2252110033471615 | 3 |
| CH017 N + CH018 N | 0.00025968284927918887 | 1 |
| CH017 N + CH030 P | 0.22521100334716115 | 3 |
| CH018 N + CH030 P | 0.22521100334716043 | 3 |
| Alle drei | 0.22547068619643962 | 4 |

Damit ist CH030-P für die nächste vollständige Kupferumlegung ein konkreter
Ansatzpunkt. Ein mögliches Fenster liegt um (40.294118,27.044748); es ist erst
nach vollständiger Wiederherstellung von CH030-P und allen übrigen Nachbarnetzen
als echter Korridor zu bewerten. Die exakten Analysewerte und der native
CH017-N-Prüfplan sind als getrennte JSON-Evidenz manifestiert. Kein aus einem
unvollständigen Modell abgeleiteter Via-Kandidat wird in den Checkpoint eingebracht.

Der anschließende F.Cu/B.Cu-Suchlauf für einen vollständigen CH030-P-Ersatz
zwischen den bestehenden Vias (39.3158,11.5863) und (40.8474,27.6679)
reservierte das genannte CH022-Via-Fenster als Hindernis auf allen Lagen.
Innerhalb des Suchbudgets (0.01-mm-Raster, maximal 1.8 Millionen Knoten,
40 Sekunden Suchfrist) wurde kein vollständiger Ersatz gefunden. Das ist
kein Unmöglichkeitsbeweis. Es wurde kein CH030-Mutations-PCB erzeugt; der
fehlgeschlagene Plan ist ausdrücklich als unvollständiges Modell dokumentiert.

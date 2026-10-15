<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: Power-sicherer 140er-Checkpoint, 2026-10-15

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

<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: gemeinsame Elektrodenumlegung, 140 → 139

## Übernommener Engineering-Checkpoint

CH019_N_ELECTRODE ist geschlossen. CH017_N_ELECTRODE und CH018_N_ELECTRODE
wurden gemeinsam vollständig neu geführt und bleiben geschlossen. Ein
unabhängiger Replay unter nativem KiCad 8.0.9 bestätigt:

| Prüfung | Ergebnis |
| --- | --- |
| Geometrische DRC-Fehler / Warnungen | 0 / 0 |
| Offene Verbindungen | 139 |
| Diagnostische Paritätsbefunde | 0 |
| L3-Power-Verlust / -Zugewinn | exakt 0.0 / 0.0 mm² |
| Netzregressionen | keine |
| Footprints, Zonenaußenkonturen, Projekt-/DRC-Regeln | unverändert |
| Unabhängiger PCB- und ZIP-Replay | byteidentisch |

Ausgang: `block2-ch025-electrode-closed140.zip`, SHA-256
`06817fef09feb864a8ef96a93e60034bb5aec7b8baecfe350ae0277a25a424b4`.

Neues Archiv: `block2-ch019-electrode-closed139.zip`, SHA-256
`f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b`.

PCB SHA-256:
`f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea`.

Es verbleiben 75 MUX- und 64 Elektroden/RC-Verbindungen. In Block 2 sind acht
MUX-Verbindungen und ausschließlich CH021_N_ELECTRODE als Elektrodennetz offen.
CH018_N_MUX bleibt geschlossen, CH018_P_MUX offen. Die verschobene VCM-Via-
Position an R38 und sämtliches nicht zur Mutation gehörende Kupfer bleiben
unverändert. Der primäre historische Pre-Route-PCB wird nicht durch den
Engineering-Checkpoint ersetzt.

## Gemeinsame Routingstrategie

Die bestehenden CH017-N- und CH018-N-Elektrodenrouten wurden auf einer
Arbeitskopie vollständig entfernt. Die Header-Anbindungen und Quell-Escapes
wurden für alle drei Netze gemeinsam reserviert; anschließend wurden mehrere
Lagen- und Routingreihenfolgen untersucht. Der erfolgreiche Entwurf reserviert
für CH017-N den nördlichen Header-Zugang, für CH018-N das kleine Fenster bei
(40.708500,8.775938) und für CH019-N den weiter unten liegenden Zugang bei
(38.407134,14.181268). Die Quell-Vias liegen bei:

| Netz | Quell-Via mm | Header-Via mm | Weiteres Via mm |
| --- | --- | --- | --- |
| CH017_N_ELECTRODE | 37.344255 / 27.176452 | 43.800000 / 5.800000 | 38.843033 / 19.120389 |
| CH018_N_ELECTRODE | 37.308680 / 24.447820 | 40.708500 / 8.775938 | 38.502450 / 11.592900 |
| CH019_N_ELECTRODE | 36.975000 / 22.100000 | 38.407134 / 14.181268 | keines |

Alle acht neuen Durchkontaktierungen haben 0.60 mm Durchmesser und 0.30 mm
Bohrung. Sie liegen außerhalb der L3-Power-Konturen einschließlich der
0.505-mm-Sperre für Via-Mittelpunkte. Alle neuen Vias besitzen tatsächlich
angeschlossenes Kupfer auf mindestens zwei Lagen. Die Leiterbahnbreite beträgt
0.15 mm; es wird auf F.Cu, B.Cu und In2.Cu geführt. Keine L2-Leiterbahn wird
hinzugefügt. Von den beiden alten Nachbarnetzen werden 31 Kupferobjekte entfernt;
46 Leiterbahnsegmente und acht Vias bilden den vollständigen Ersatz einschließlich
CH019-N. Änderungen an anderen Netzen sind im Replay verboten.

Die Auswahl entstand aus einer geometrischen Komponenten-/Mesh-Suche mit
reservierten vollständigen Endpunkten. Unterbrochene Nachbarnetz-Varianten und
reine Via-Fenster ohne vollständigen Trunk blieben `accepted=false`.
Die Suchprotokolle und Zwischenpläne sind im separaten Diagnosearchiv
`joint-electrode139-model-diagnostics.zip` erhalten. Nur der vollständig nativ
qualifizierte Entwurf `joint1718-precise-spread140/case2-plan.json` wird übernommen.

## Modellverfeinerung bei unveränderten Designregeln

Das konservative Pad-Rechteckmodell sperrte Teilstücke eines bereits nativ
DRC-sauberen CH018-N-Bestandswegs: circa 0.271 mm am Diagonalstück bei
(41.63…41.82,13.51…13.70) sowie circa 0.133 mm nahe dem gerundeten Header-Pad.
Für Leiterbahnen verwendet `pad_copper_shape()` jetzt KiCads tatsächliche
Pad-Polygone. Die native Polygonisierung wird mit maximal 0.0001 mm Fehler
angefordert und um 0.001 mm konservativ nach außen erweitert. Ungültige oder
nicht unterstützte Konturen fallen auf das sichere Pad-Rechteck zurück.
Die Via-in-Pad-Sperre umfasst weiterhin das gesamte Pad-Rechteck auf allen Lagen.
Clearance-, Trackbreiten- und Via-Regeln wurden nicht geändert.

`routing_domain()` bleibt in sämtlichen Lagen- und Via-Hindernismengen aktiv:
0.25 mm A2-Randabstand zu tatsächlichen geschlossenen Konturen einschließlich
Ausschnitten plus jeweiliger Kupferradius. Die positive Modellverfeinerung ersetzt
keinen nativen DRC. Für den akzeptierten Entwurf sind die nativen Rohberichte
und der byteidentische Replay maßgebend.

Die acht nativen Geometrieprüfungen umfassen Außenraum-/Ausschnitt-Sperren,
getrennte Via-/Leiterbahnränder, fehlende Konturen, gerundete Pad-Ecken und die
konservative Einhüllung analytischer Roundrect-Umfänge für drei Padgrößen in
0°/90°-Orientierung. Das L3-Power-Gate verwendet weiterhin keine Toleranz:
Verlust und Zugewinn müssen beide exakt 0.0 mm² sein.

## Leitungslängen und noch offene elektrische Validierung

| Netz | Vorher mm / Vias | Jetzt mm / Vias |
| --- | ---: | ---: |
| CH017_N_ELECTRODE | 23.268367 / 4 | 57.022776 / 3 |
| CH018_N_ELECTRODE | 34.883490 / 2 | 24.465250 / 3 |
| CH019_N_ELECTRODE | offen | 21.095433 / 2 |

CH017-N wurde um rund 33.754409 mm verlängert. Die neue Führung ist ein
geometrisch und elektrisch zusammenhängender Engineering-Stand. Aussagen zu
zusätzlicher Einkopplung, parasitären Effekten oder erreichbarer Rauschleistung
werden daraus nicht abgeleitet. Die elektrische Laborprüfung bleibt vor einer Fertigungs-/Hardwarefreigabe
erforderlich. Eine spätere Längenoptimierung ist zu prüfen.

## Folgesuche am 139er-Stand

Die korrigierten Modellgrenzen wurden für CH018_P_MUX (F.Cu/B.Cu) und
CH021_N_ELECTRODE (F.Cu/In2.Cu) beibehalten. Begrenzte Suchläufe mit
0.01-mm-Raster, maximal einer Million Knoten und 30 Sekunden Suchfrist je Netz
fanden keinen vollständigen weiteren Weg. Aus diesen Suchläufen wurde keine
Mutation erzeugt. Die Via-Fensteranalyse der Quell-/Zielkomponenten für 140 und
139 ist zusätzlich als `next-window-analysis.json` gespeichert. Die Ergebnisse
sind Modelle und begründen keine weiteren Freigaben oder Unmöglichkeitsbehauptungen.

Am 139er-Stand sind die modellierten Via-Fenster bei CH021-N sowohl in der
F.Cu-Quellkomponente als auch in der F.Cu-Zielkomponente leer. Die gemeinsame
Umlegung beseitigt diese beiden Engstellen nicht. Bei CH018-P besitzt die
Quellkomponente weiterhin rund 5.442749 mm² freie Via-Fläche außerhalb der
Power-Sperre; die Zielkomponente besitzt exakt 0.0 mm². Ihr F.Cu-Bereich liegt
zwischen Y=44.140100 und 46.897000 mm. Der nächste vollständige Lösungsversuch
muss deshalb den Ziel-Escape beziehungsweise dessen begrenzende Nachbarstrecken
öffnen oder einen bereits vorhandenen geeigneten Übergang vollständig umlegen.
Ein neuer isolierter Via-Drop am Ziel wird nicht übernommen.

## Replay, Manifeste und CI

`replay_ch019_electrode.py` liest ausschließlich das SHA-256-geprüfte 140er-
Archiv und die unveränderliche `joint139-recipe.json`. Ein separater Apply-
Kindprozess prüft vor jedem Schreiben den Ausgangshash, die erlaubten Netze und
Lagen sowie die Via-Anbindung. Erst nach seinem Ende folgen frische Zonenfüllung
und DRC; Parität wird in einem weiteren Prozess geprüft. Native Version,
140→139-Reduktion, fehlende Netzregression, unveränderte geschützte Geometrie,
exakte Power-Differenzen und erwartete PCB-/ZIP-Hashes sind harte Bedingungen.

Die CI ergänzt fünf Integritäts-/Negativtests und den neuen 140→139-Replay.
Die bisherigen Replays und der ausdrücklich nicht übernommene CH030-Diagnose-
Replay bleiben erhalten. Alle Replay-Verzeichnisse unterliegen der Sperre gegen
Fertigungsexporte. Die native Testsuite enthält damit 33 Tests. Der Legacy-
Experimentrouter bleibt ausschließlich manuell startbar.

`current-routing-status.json` benennt ausschließlich das verifizierte 139er-
Engineering-Archiv. `routing_completed=false`, `fabrication_release=false` und
sämtliche übrigen Freigabesperren bleiben unverändert. Keine Gerber-, NC-Drill-,
CPL- oder BOM-Dateien wurden erzeugt oder freigegeben. Dies ist keine
Fertigungs- oder Anwendungsfreigabe.

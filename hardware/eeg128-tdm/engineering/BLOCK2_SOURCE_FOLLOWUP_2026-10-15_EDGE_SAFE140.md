<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: Korridorprüfung mit vollständigem Platinenrand-Gate

## Ergebnis

Der akzeptierte Hardwarestand bleibt unverändert bei 140 Luftlinien:
`block2-ch025-electrode-closed140.zip`, SHA-256
`06817fef09feb864a8ef96a93e60034bb5aec7b8baecfe350ae0277a25a424b4`;
PCB SHA-256
`d95f88c9e58766600eb536a38fb3d7e72241d370d998b16c18a703bc9da4f25f`.
Kein Routingprüfling dieses Folgeberichts wird übernommen. Die bestehende
native 0-Fehler-/0-Warnungen-/0-Paritäts-Prüfung des 140er-Checkpoints und seine
exakt unveränderte L3-Power-Fläche bleiben gültig. Es verbleiben 75 MUX- und
65 Elektroden/RC-Verbindungen, in Block 2 acht MUX- und zwei Elektrodennetze.

## Korrektur der bisherigen CH030-Fensteranalyse

Die vorangegangene reine Komponenten-/Mesh-Analyse benutzte ein Analysefenster,
das nördlich über die physische Platinenkante bei Y=5 mm hinausragte. Anders als
die gerasterte `search()`-Funktion enthielt die direkt aufgerufene
`obstacles()`-Funktion bisher keine Sperre für diesen Außenraum. Dadurch konnte
die geometrische Zusammenhangsanalyse über den Platinenrand hinweg verbinden.
Die drei vermeintlichen CH030-basierten Via-Fenster mit zusammen rund
0.225211 mm² sind **kein belegter Routingkorridor**. Die entsprechenden Aussagen
im vorherigen POWER_SAFE140-Bericht sind durch diese Korrektur überholt.
Die nativen Nachweise des akzeptierten CH025-140er-Archivs waren davon nicht
betroffen: Es wurde ausschließlich die verworfene Korridoranalyse korrigiert.

`routing_domain()` bildet jetzt die tatsächlich geschlossenen KiCad-Konturen
samt inneren Ausschnitten ab. Kupfermittellinien halten mindestens 0.25 mm
Randabstand plus halbe Leiterbahnbreite ein; Via-Mittelpunkte halten 0.25 mm
plus Via-Radius ein. Zusätzlich wird 0.000001 mm nach innen abgerückt.
Dieser kleine konservative Planungsaufschlag ist keine Toleranz für das
L3-Power-Gate. Fehlende/offene oder ungültige Konturen blockieren die Analyse.
Beide Lagenhindernismengen sowie die lagenübergreifende Via-Sperre enthalten den
unzulässigen Außenraum. Das schützt nun auch direkte geometrische Aufrufer.
Die 0.25-mm-Vorgabe entspricht der unveränderten Regel
`A2 copper edge clearance` in diesem Projekt. Native DRC bleibt maßgebend.

## Vollständig angewendete CH030-Prüflinge

| Prüfling | Länge | Neue Vias | DRC-Fehler / Warnungen | Luftlinien | Parität | L3 Verlust / Zugewinn mm² | Entscheidung |
| --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| L3-Referenz zwischen bestehenden Vias | 79.515331 mm | 0 | 2 / 0 | 140 | 0 | exakt 0.0 / 0.0 | Verworfen: zwei Randverletzungen |
| Kurzer B.Cu-Ersatz | 16.587472 mm | 0 | 0 / 0 | 140 | 0 | exakt 0.0 / 0.0 | Nicht übernommen: kein vollständiger Korridor |

Beide ersetzen vollständig die drei bisherigen CH030_P_ELECTRODE-B.Cu-Segmente
zwischen (39.3158,11.5863) und (40.8474,27.6679). Vorhandene Vias und
F.Cu-Anbindungen bleiben erhalten. Footprints, Regeln und Zonenaußenkonturen
bleiben unverändert. Kein zuvor geschlossenes Netz regressiert.
Die 79.5-mm-Referenz verlässt bei Y≈3.65–3.87 mm die Platine; die beiden nativen
`copper_edge_clearance`-Fehler verwerfen sie unabhängig von der Power-Metrik.
Der kurze B.Cu-Ersatz ist elektrisch und geometrisch sauber, trennt aber die
für CH022 benötigte B.Cu-Quelltasche weiterhin vom Via-Ziel. Ein freier Via-Kreis
allein wird nicht als Korridoröffnung gewertet.

Der kurze B.Cu-Prüfling wurde mit `replay_ch030_probe.py` unabhängig wiederholt.
Der SHA-256-gebundene reine Apply-Kindprozess beendet sich vor Zonenfüllung/DRC;
Parität folgt in einem weiteren Prozess. Die Wiederholung ist PCB-byteidentisch:
`80003bdb106684903928fc27ab46440a2bbce90f5bcfc09bc1b1677ebd4cb23a`.
Der Replay prüft exakt 0/0/140, Parität 0, keine Netzregression und exakt
0.0 mm² Power-Verlust **und** -Zugewinn. Sein Ergebnis enthält trotzdem
`accepted=false`: Es ist ein reproduzierbares Diagnoseobjekt, kein neuer
Checkpoint. Der Replay erzeugt kein Engineering-Release-Archiv und keine
Fertigungsdateien. Der L3-Fehlprüfling bleibt ausschließlich negative Evidenz.

## Korrigierte Korridorbefunde

Die sieben früheren Vergleichsmodelle wurden mit der neuen Randmaske erneut
berechnet. CH030-P allein liefert jetzt 0.0 mm² gemeinsame zulässige Via-Fläche;
dasselbe gilt für CH017-N allein und CH018-N allein. Lediglich die kombinierte
analytische Entfernung der CH017-N- und CH018-N-B.Cu-Strecken lässt ein sehr
kleines Fenster von 0.00025968284927918887 mm² um (36.95,16.367738) übrig.
Das Modell ist unvollständig und ausdrücklich nicht übernommen: Beide
Elektrodennetze müssten vollständig und ohne erneutes Schließen des Fensters
wiederhergestellt werden. Es gibt dafür keinen nativ qualifizierten Kandidaten.
Diese Vergleichsmodelle enthalten weiterhin den unvollständigen CH019-P-
Trunktausch, einschließlich noch nicht wiederhergestellter CH027-N-Rückführung.
Ihre Ergebnisse begründen weder eine elektrische Freigabe noch ein neues Via.

Zusätzlich wurde die vollständige Entfernung des oberen CH022-N-L3-Escapes
bis zum erhaltenen Trunk bei (30.955,24.579999) geometrisch untersucht.
Mit unverändertem CH030-P, mit dessen analytisch entfernter B.Cu-Begrenzung
und mit dem vollständigen kurzen B.Cu-Ersatz bleibt die gemeinsame zulässige
Via-Fläche zwischen B.Cu-Quelltasche und L3-Trunkkomponente jeweils exakt 0.0 mm².
Die reine CH030-Umlegung ist damit im untersuchten Bereich kein belegter
Lösungsweg für den vollständigen CH022-Quell-Escape.

## CH018-P und verbleibende Elektroden

Auf dem unveränderten 140er-Checkpoint wurden erneut begrenzte Suchläufe mit
0.01-mm-Raster, maximal einer Million Knoten und 30 Sekunden Suchfrist je Netz
angesetzt. Alle neuen Via-Positionen bleiben außerhalb der L3-Power-Kontur
inklusive 0.505-mm-Sperrbereich; auf L3 wird die Power-Kontur zusätzlich als
Leiterbahnhindernis reserviert.

| Netz | Quelle mm | Ziel mm | Lagen | Vollständiger Weg gefunden |
| --- | --- | --- | --- | --- |
| CH018_P_MUX | 32.750 / 26.000 | 41.135 / 45.150 | F.Cu / B.Cu | Nein |
| CH019_N_ELECTRODE | 36.150 / 23.400 | 42.250 / 7.600 | F.Cu / In2.Cu | Nein |
| CH021_N_ELECTRODE | 36.150 / 18.200 | 43.250 / 7.600 | F.Cu / In2.Cu | Nein |

Das sind begrenzte Suchergebnisse, keine Unmöglichkeitsbeweise. Aus diesen
Suchläufen wurden keine Mutations-PCBs oder isolierten Vias erzeugt.
Weitere Arbeit muss eine vollständige gemeinsame Umlegung der Begrenzungen
oder die Wiederverwendung vorhandener Übergänge nachweisen; die widerlegten
CH030-Fenster werden nicht weiter als offene Korridore geführt.

## Prozess, CI und Release

Die CI ergänzt sechs native Prüfungen der Routingdomäne (darunter ein außen
vorbeiführender falscher Korridor, Ausschnitte, getrennte Via-/Leiterbahnränder
und fehlende Konturen), fünf Replay-Integritätsprüfungen des unübernommenen
CH030-Prüflings und dessen getrennten nativen Replay. Die drei bestehenden
Replays bis 140 bleiben unverändert vorgeschrieben. Das zusätzliche
Diagnoseverzeichnis ist ebenfalls in der Fertigungsexport-Sperre enthalten.

Alle Rohberichte, Pläne, korrigierten Modelle und das unabhängige Replay-
Ergebnis liegen unter `followup-2026-10-15-edge-safe140/` und sind SHA-256-
manifestiert. Der aktuelle Routingstatus und das akzeptierte 140er-Archiv
bleiben unverändert. `routing_completed=false`, `fabrication_release=false`.
Keine Gerber-, NC-Drill-, CPL- oder BOM-Dateien wurden erzeugt oder freigegeben.

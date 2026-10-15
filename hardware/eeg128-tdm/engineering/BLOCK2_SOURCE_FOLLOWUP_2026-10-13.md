# Block-2-Freigabe und systematische MUX-Paarsuche – 2026-10-13

## Übernahme und Ergebnis

Der nun veröffentlichte Bericht vom 12.10. liegt auf
`hardware/block2-source-window-2026-10-12`, Commit `7e5129f`.
Alle Einträge von `BLOCK2_SOURCE_FOLLOWUP_SHA256SUMS` und
`CHECKPOINT_SHA256SUMS` bestehen. Die freigegebene VCM-Mutation wurde mit
KiCad 8.0.9 bytegleich reproduziert: Via an R38 auf **39,65 / 26,00 mm**,
verkürztes F.Cu-Endstück und zusätzlicher 0,20-mm-B.Cu-Link. Der VCM-Stand
bestätigt 0 DRC-Verletzungen, 0 Warnungen, 149 Luftlinien, 0 diagnostische
Paritätsbefunde und geometrisch **0 mm² L3-Power-Verlust und -Zugewinn**.

Die systematische Suche schließt anschließend **CH099_N_MUX und CH099_P_MUX**.
Dieses Paar liegt außerhalb des lokalen Block-2-Engpasses, wurde jedoch in
der Suche nach anderen geeigneten MUX-Paaren gefunden. Der neue
Engineering-Arbeitsstand enthält die freigegebene VCM-Verschiebung und hat
**147 Luftlinien, 0 DRC-Verletzungen, 0 Warnungen, 0 diagnostische
Paritätsbefunde und exakt 0 mm² L3-Power-Verlust sowie -Zugewinn**.
Es wurden keine zuvor geschlossenen Netze wieder geöffnet.

`BLOCK2_WORKING_BASELINE.json` bindet das neue Arbeitsarchiv
`block2-ch099-closed147.zip`. Der bisherige Recovery-Checkpoint
`latest-pcb.zip` und seine Status-/Release-Dateien bleiben unverändert;
der neue 147er-Stand ist ausdrücklich eine separate Engineering-Arbeitsbasis.
Routing- und Fertigungsfreigabe bleiben false.

## Suche und verworfene Kandidaten

Die acht normalen und vier Wegpunkt-Probes vom 12.10. wurden gelesen.
Der neue Lauf umfasst 60 Paar-Probes für CH018, CH020, CH024, CH033,
CH042, CH051, CH060, CH072, CH073, CH088, CH099, CH102, CH104, CH114
und CH120: F.Cu/L3 und F.Cu/L4, jeweils N-vor-P und P-vor-N;
Raster 0,05 mm, Rand 12 mm, A*-Budget 6 Sekunden und 250000 Knoten.
Diese Budgets betreffen die Suche, nicht den geometrischen Modellaufbau.
Nicht gefundene Pfade sind keine Unmöglichkeitsnachweise.
Unvollständige Paarpfade blieben ausschließlich im Speicher; keine
isolierten Probe-Vias wurden als PCB-Kandidat gespeichert.

CH099 und CH102 erreichten probeweise 147 Luftlinien bei DRC 0/0 und
Parität 0, wurden zunächst aber wegen L3-Flächenverlust verworfen:
CH099 rund 0,000077235 mm², CH102 rund 0,007589238 mm².
Das Suchmodell reservierte die Power-Fläche zunächst mit dem normalen
Signalabstand. Ein zusätzlicher 0,05-mm-Puffer berücksichtigt nun den
höheren Power-Abstand von 0,20 mm. Ein gezielter Lauf für CH099/CH102
mit 12 Sekunden Suchbudget fand bereits im ersten Versuch ein akzeptiertes
CH099-Paar; er stoppte dort und testete CH102 nicht erneut.

Bei der abschließenden Regelprüfung wurde außerdem KiCads automatische
Erzeugung einer Default-PRO-Datei nach SaveBoard für einen neuen Pfad
abgefangen. Die Such- und Probe-Skripte stellen vor der nativen Prüfung
PRO/DRU aus der freigegebenen Basis wieder her. Der akzeptierte Stand
wurde danach erneut mit den unveränderten Originalregeln geprüft.
Die ersten Suchprotokolle dienen der Diagnose; maßgeblich sind die
abschließenden DRC-, Paritäts- und Geometrienachweise.

## Konkreter CH018-Engpass

Ein neuer B.Cu/L3-Modellpfad führt von (43,60;25,00) zum bisherigen
N-Ziel-Via-Fenster (41,135;59,65). Nach Entfernung eines redundanten
anfänglichen Layerwechsels ergibt die vollständig angeschlossene N-Probe
0 DRC-Verletzungen, 0 Warnungen, 148 Luftlinien und 0 Paritätsbefunde.
**Sie wurde verworfen:** Die gefüllte L3-Power-Fläche verliert dabei rund
0,792364302 mm². Der bisherige Ziel-Via-Ort liegt in der gefüllten
Power-Fläche; der Quellpfad in der RC-Tasche hat im geometrischen Modell
keine Power-Überlappung. DRC 0/0 allein reicht daher nicht zur Übernahme.

Ein weiterer lokaler Ziel-Escape-Probe von U4-Pad 7 mit Power-Sperre
(Raster 0,025 mm, Rand 8 mm, Budget 15 Sekunden/250000 Knoten)
fand keinen alternativen Via-Ort. Das begrenzte Suchergebnis belegt keine
Unmöglichkeit. Der nächste lokale CH018-Schritt ist ein Ziel-Escape außerhalb
der vorhandenen L3-Power-Fläche; das Fenster 41,135/59,65 darf unter der
Null-Verdrängungs-Vorgabe nicht übernommen werden. Die verworfene N-Probe
wird nur durch Pfade und Berichte dokumentiert, nicht als Arbeits-PCB.

## Abschlussnachweise und Grenzen

Die separate Abschlussprüfung des CH099-Archivs bestätigt KiCad 8.0.9,
0/0/147 sowie Parität 0. Der neue Geometrie-Audit erlaubt exakt die beiden
CH099-Netze und prüft das gesamte Board: 109 neue Kupferobjekte,
bestehendes Kupfer einschließlich ADC6/ADC7 unverändert, Footprints,
Zonen-Umrisse und PRO/DRU unverändert. Mindestabstand neuer L3-Segmente
zur bisherigen Power-Fläche: N 0,475 mm, P 2,325 mm.

Neue Leiterbahnlängen: N 36,107 mm (davon L3 27,569 mm, 4 Vias),
P 26,266 mm (davon L3 23,345 mm, 2 Vias).
Dies ist **keine P/N-Skew-, Rückstrom-, Kopplungs- oder unabhängige
Primärschaltplan-LVS-Freigabe**. Die Parität verwendet weiterhin den aus
PCB-Netzen erzeugten Diagnoseschaltplan. Keine Fertigungsdateien erzeugt.

PCB SHA-256: `52122b691e649d3b7328672e3d6ef303618e1fbc263f3c486821e3a1b95542be`

ZIP SHA-256: `5e579742d45bd449428ec77ea5658f63e79d52f98cae9a1d9c8062ccfc473ae0`

Die neuen Dateien sind in `BLOCK2_FOLLOWUP_2026-10-13_SHA256SUMS` gebunden.
Die reproduzierbaren Suchparameter und Pfade liegen in den JSON-Nachweisen;
`search_block2_followup.py`, `probe_block2_trunk.py` und
`audit_mux_followup.py` enthalten Suche, verworfenen N-Versuch und
abschließenden Schutz-Audit. Für den ersten Suchlauf ist
`--power-margin 0`, für den akzeptierten Lauf `--power-margin 0.05` zu verwenden.

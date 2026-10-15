<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: U3-Ziel-Escape und CH021-N, 139er-Basis

## Ergebnis und unveränderter Checkpoint

**Keine weitere Luftlinie geschlossen; kein neuer PCB-Checkpoint übernommen.**
CH018_P_MUX und CH021_N_ELECTRODE bleiben offen. Sämtliche neuen Varianten
sind `accepted=false`. Zwei vollständige lokale Nachbarnetz-Umlegungen sind
nativ qualifiziert, ohne sie als Routingfortschritt zu übernehmen.

Freigegebene Basis bleibt der Routing-Commit
`437b37f2ed115e293ca30ccfbc873bedcf4d449b`.
Das Basisarchiv `block2-ch019-electrode-closed139.zip` bleibt bytegleich:

- ZIP SHA-256: `f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b`.
- PCB SHA-256: `f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea`.
- 139 Luftlinien, 0 geometrische Fehler, 0 Warnungen, 0 Paritätsbefunde.
- 75 MUX- und 64 Elektroden/RC-Verbindungen; Block 2: acht MUX und CH021_N_ELECTRODE.

`current-routing-status.json`, der historische primäre PCB und das akzeptierte
139er-Archiv werden durch diese Untersuchung nicht ersetzt. Die VCM-Via-
Position an R38 bleibt X=39,65 mm. `routing_completed=false` und
`fabrication_release=false`; keine Gerber-, Drill-, CPL- oder BOM-Erzeugung.

## CH018_P_MUX: U3 und vollständige Steuerleitungs-Restitution

Der P-Zielpad ist **U3.7 bei (41,135 / 45,150) mm**. Der bereits geschlossene
N-Zweig endet an U4.7; dessen Ziel wird nicht mit U3 vertauscht.

Die bereits untersuchte lokale MUX_S1-F.Cu-Umleitung und die vollständige
linke VCM-Brücke wurden als geometrisches Delta auf die 139er-Basis
übertragen. Anschließend wurden die drei begrenzenden internen F.Cu-
Steuerleitungsverbindungen MUX_EN, MUX_S2 und MUX_S3 im Suchmodell geöffnet.
Der P-Zweig besitzt in diesem Modell einen vollständigen F.Cu/B.Cu-Pfad.
Dieser Pfad ist noch keine qualifizierte Gesamtmutation.

Zwei Familien mit je sechs Routingreihenfolgen wurden geprüft:

1. F.Cu-Start der Steuerleitungen, mit B.Cu-Ausweichführung und neuen Vias
   ausschließlich außerhalb der In2.Cu-Power-Konturen.
2. Wiederverwendung der vorhandenen B.Cu-Starts von MUX_S2 bei
   (23,680 / 37,100) mm und MUX_S3 bei (26,4572 / 37,8222) mm.

In keiner der zwölf begrenzten Suchen gelang die gleichzeitige Wiederherstellung
aller drei Steuersignale. Je nach Reihenfolge gelingt die erste Verbindung,
die nächste scheitert. Die entfernten Nachbarnetzstrecken werden daher **nicht**
als freier Korridor übernommen. Alle Gesamtpläne bleiben unvollständig und
`accepted=false`; es wird kein isoliertes Via als Zwischenstand freigegeben.
Die Ergebnisse sind keine Aussage, dass global keine Lösung existiert.

## CH021_N_ELECTRODE: zwei nativ geprüfte Quellöffnungen

Quelle: R300.1 bei (36,150 / 18,200) mm; Ziel: J2.22 bei
(43,250 / 7,600) mm. Padreferenzen, Netzname und Koordinaten sind am nativen PCB verifiziert.

| Unübernommene lokale Umlegung | Lage | Änderungen | Modelliertes legales Quell-Via-Fenster |
| --- | --- | --- | --- |
| CH022_N_MUX | In2.Cu | ein Segment durch 16 Segmente ersetzt | 0,0006270576613892242 mm² um 35,600 / 17,275 mm |
| CH026_P_ELECTRODE | F.Cu | ein Segment durch acht Segmente ersetzt | 0,026628867281972456 mm² um 38,225 / 17,250 mm |

Die jeweilige Ausgangsverbindung ist vollständig wiederhergestellt. Neue Vias
wurden in diesen beiden lokalen Prüflingen **nicht** gesetzt. Die Fenster sind
Suchmodell-Ergebnisse; sie ersetzen keinen nativen DRC einer späteren vollständigen
CH021-Verbindung einschließlich Vias.

Beide Prüflinge wurden unabhängig aus dem SHA-gebundenen Basisarchiv replayt:

| Native KiCad 8.0.9-Prüfung | CH022-L3-Prüfling | CH026-F.Cu-Prüfling |
| --- | --- | --- |
| DRC-Fehler / Warnungen / Luftlinien | 0 / 0 / 139 | 0 / 0 / 139 |
| Paritätsbefunde / Netzregressionen | 0 / keine | 0 / keine |
| L3-Power-Verlust / -Gewinn | exakt 0,0 / 0,0 mm² | exakt 0,0 / 0,0 mm² |
| Footprints, Zonenaußenkonturen, Projekt-/DRC-Regeln | unverändert | unverändert |
| PCB SHA-256 | `072c9dd32afd33523a23a322d51465305adfb9384dacb7314e7984f27c38b573` | `6ac55e3774bd4f595555b12c19845b2706db1b4df6349bfc41624fe9b4ecaadf` |
| Übernahme als neuer Routingstand | nein | nein |

## Header-Engpass und kombinierte Entflechtung

Sieben F.Cu-Entfernungsmodelle untersuchen einzeln und kombiniert die Header-
Führungen von CH020_N_ELECTRODE, CH022_N_ELECTRODE und CH023_N_ELECTRODE.
Die bestehenden Vias bleiben erhalten:

- CH020 allein öffnet kein Ziel-Via-Fenster.
- CH022 öffnet modellseitig rund 0,212934 mm².
- CH023 öffnet modellseitig rund 8,377595 mm² im betrachteten Suchfenster.
- CH022 zusammen mit CH023 öffnet rund 8,590528 mm².

Diese Werte gelten ausdrücklich **nach Entfernen der bezeichneten Nachbarstrecken**.
Sie sind keine unmittelbar nutzbare freie Fläche des akzeptierten PCB.

Mit den beiden lokalen Quellöffnungen gelingt innerhalb der untersuchten
F.Cu/B.Cu/In2.Cu-Komponentengraphen noch keine Gesamtverbindung zum Header.
Eine weitergehende Entfernung der vier CH026-F.Cu-Quellsegmente öffnet dagegen
einen vollständigen modellierten CH021-F.Cu/In2.Cu-Pfad: F.Cu-Quelle bis
(44,463531 / 22,100000) mm, In2.Cu bis (50,976200 / 8,308162) mm, dann F.Cu zum
Header. Dabei fehlt die vollständige Wiederherstellung von CH026_P_ELECTRODE.
Auch alternative Reihenfolgen und vorhandene Via-Starts ergeben keinen
vollständigen Gesamtplan. Die zusätzliche CH020-L3-zu-B.Cu-Umlegung wurde in
begrenzten Suchen ebenfalls nicht vollständig gefunden. Diese Varianten werden
verworfen und nicht nativ als neue Checkpoints qualifiziert.

Die nächste kombinierte Suche muss daher **die Restitutionskorridore zuerst
reservieren**: insbesondere den CH026-Anschluss an R309 bei (41,150 / 18,200) mm
und die Header-Anbindung des jeweils veränderten CH022-/CH023-Netzes. Ein
alleiniger CH021-Pfad durch nachbarseitig entfernte Kupferstrecken genügt nicht.

## Modellgrenzen, Replay und CI

Alle Suchen verwenden `routing_domain()` einschließlich 0,25 mm Randabstand,
native `pad_copper_shape()`-Polygone mit 0,0001 mm Approximationsfehler und
0,001 mm konservativer Aufweitung. Leiterbahnen: 0,15 mm; Signalclearance:
mindestens 0,15 mm; Referenz-/Power-Clearance: mindestens 0,20 mm.
Vorschläge für neue Durchkontaktierungen: mindestens 0,60/0,30 mm und außerhalb
der Power-Zonenaußenkonturen mit 0,505 mm Mittelpunktsperre. In2.Cu-Pfade
meiden die Power-Außenkonturen mit der vorhandenen konservativen Sperre.
Die begrenzten A*-Suchen und komponentenbasierten Suchfenster beweisen keine
globale Unroutbarkeit. Die Wahl repräsentativer Via-Übergänge ist endlich.

`replay_escape139_probes.py` reproduziert ausschließlich die zwei geprüften
lokalen Umlegungen. Das Apply-Unterprogramm endet vor dem getrennten
Zonenfill/DRC-Prozess; Parität läuft anschließend separat. Die Prüfung vergleicht
sämtliches Kupfer mit dem exakten Rezept, Footprints, Regeln, Zonen und beide
Richtungen der Power-Flächendifferenz **ohne numerische Toleranz**. Die Ergebnisse
bleiben selbst bei sauberem DRC explizit `accepted=false`, da keine Luftlinie
reduziert ist. Es entsteht kein neues Routing-ZIP.

```sh
python3 hardware/eeg128-tdm/replay_escape139_probes.py \
  --case c22 --output-dir /tmp/escape139-c22
python3 hardware/eeg128-tdm/replay_escape139_probes.py \
  --case c26 --output-dir /tmp/escape139-c26
```

Voraussetzung: native KiCad-8.0.9-Python-Bindings, passende `kicad-cli`-Version,
NumPy und Shapely 2.0.3, wie in der nativen CI. Beide Ausgabepfade müssen neu sein.
Fünf neue Tests sichern Rezeptbindung, Ausgangs-PCB, exakte Anwendung sowie
Ablehnung fremder Lagen und Via-Drops vor dem Schreiben. Die native CI führt
beide Replays zusätzlich zur bisherigen Replay-Kette aus; Exportkontrollen
erfassen auch diese Verzeichnisse. Alle 38 nativen Guard-Tests haben lokal bestanden.

Rohberichte, Rezepte, Fenster und Suchzusammenfassung liegen in
`followup-2026-10-15-escapes139/`. `escape139-model-diagnostics.zip` enthält nur
Planungs-JSON und zugehörige Suchquellen, keine PCB- oder Fertigungsdateien.
`ESCAPES139_FOLLOWUP_2026-10-15_SHA256SUMS` bindet diese Nachweise und die
unveränderte 139er-Basis. Der Bericht beschreibt eine abgeschlossene Untersuchung,
keinen neuen freigegebenen Routingstand.

# Block-2-Korridorprüfung ab dem bestätigten 143er-Stand – 2026-10-15

## Ergebnis und Arbeitsbasis

Der freigegebene Arbeitsstand bleibt **143 Luftlinien**. In dieser Iteration
wurde keine Verbindung geschlossen und keine Umlegung in die Arbeitsbasis
übernommen. Die neuen Erkenntnisse betreffen die Grenzen der CH018-Quell-Tasche
und einen elektrisch sauberen, aber weiterhin eingeschlossenen Umlegekandidaten.

Arbeitsarchiv: `block2-electrode-closed143.zip`.

ZIP SHA-256: `e8d60a9835aea686af2d34d9e0e31b3a948b8c7dd2caae81c2c24786e4a3a8e1`

PCB SHA-256: `497b588e580caf24766d5d60e9753def8dfe10ad3495b75faf5cd3fdd6276f24`

Eine frische Prüfung mit KiCad 8.0.9 bestätigt 0 DRC-Verletzungen,
0 Warnungen, 0 diagnostische Paritätsbefunde und 143 offene Verbindungen.
R38 bleibt bei 38,250/26,000 mm, das VCM-Via bei **39,650/26,000 mm**.
Das Arbeitsarchiv ist bytegleich zur bestätigten Basis.

## CH018: Begrenzungen einzeln und gemeinsam geprüft

Zunächst wurden ausschließlich im geometrischen Modell die lokalen
B.Cu-Segmente von CH019_N_MUX, CH025_P_MUX und CH028_P_MUX einzeln und in allen
Kombinationen entfernt. Die vorhandenen Vias blieben dabei unverändert.
Keines der sieben Gegenmodelle öffnete die zusammenhängende Tasche bis zum
Rand des Fensters X=35–44/Y=22–30 mm. Diese Modelle sind keine vollständigen
Schaltungen und wurden nicht als Routing-Kandidaten übernommen.

| Modell bzw. vollständiger Versuch | L4-Taschenfläche | DRC | Warnungen | Parität | L3-Power-Verlust | Entscheidung |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Bestätigte Basis | 0,586526 mm² | 0 | 0 | 0 | 0 mm² | Arbeitsbasis |
| Nur CH019-N-L4-Segmente entfernt, Modell | 2,251418 mm² | — | — | — | nicht geprüft | kein Ausgang |
| Alle drei lokalen L4-Sperren entfernt, Modell | 3,178643 mm² | — | — | — | nicht geprüft | kein Ausgang |
| Vollständiger Umlegeversuch 1 | 1,365849 mm² | 4 | 0 | 0 | 0 mm² | verworfen |
| Vollständiger Umlegeversuch 2 | 1,966515 mm² | 0 | 0 | 0 | 0 mm² | weiterhin eingeschlossen; keine Übernahme |

Versuch 1 verschob das CH025-P-Via von 38,755/24,999999 auf
38,400/24,999999 mm und legte den CH019-N-L4-Stamm über X=37,650 mm um.
Er scheiterte an einer Clearance von 0,1016 statt 0,1500 mm zur
CH019-N-Quell-Via sowie drei Kurzschlussbefunden mit CH017_N_ELECTRODE.
Es gab keine Verbesserung der Luftlinienzahl; dieser Versuch ist verworfen.

Ein zusätzlicher reiner F.Cu-Ersatz für die CH025-P-Verbindung zwischen
41,155/24,999999 und 38,155/22,399999 mm fand im geprüften Suchbudget keinen
Pfad (Raster 0,025 mm, Rand 6 mm, 30 Sekunden/600000 Knoten).
Hierzu wurde kein unvollständiges Kupfer gespeichert.

Versuch 2 verschob das CH025-P-Via nur auf **38,500/24,999999 mm**.
Die zugehörige F.Cu-Spur wurde vollständig nachgeführt. Die beiden lokalen
CH025-P-L4-Segmente wurden durch einen durchgehenden L3-Pfad zwischen den
vorhandenen Through-Vias ersetzt. Die Suche verwendete eine harte Sperre
gegen das vorhandene Power-Kupfer (Raster 0,010 mm, Rand 4 mm,
25 Sekunden/600000 Knoten). Der CH019-N-Stamm erhielt einen vollständigen
L4-Dogleg über X=37,950 mm zwischen seinen bisherigen Endpunkten.

Dieser Kandidat besteht die nativen Prüfungen bei weiterhin 143 Luftlinien.
Es wurden keine Vias hinzugefügt; CH028_P_MUX und VCM bleiben unverändert.
Der Geometrieaudit bestätigt ausschließlich die deklarierten Änderungen:
2 geänderte, 3 entfernte und 30 neue Kupferobjekte, davon 27 L3-Segmente
und 3 CH019-N-L4-Segmente. Alle anderen bestehenden Kupferobjekte,
Footprints, Zonen-Umrisse und PRO/DRU sind unverändert. Es gibt keine
Netzregression, keinen Power-Verlust und keinen Power-Zugewinn. Der minimale
Abstand der neuen L3-Kupfergeometrie zum ursprünglichen Power-Kupfer beträgt
12,549166 mm.

Die erweiterte Tasche reicht im Modell von X=38,250 bis 39,075 und
Y=22,223230 bis 26,603481 mm, berührt aber weiterhin keinen Fensterrand.
Weiter nördlich begrenzen das CH025-P-Via bei 38,155/22,399999 mm,
das CH027_P_ELECTRODE-Via bei 38,750/21,779999 mm und der VCM-Stamm den
Ausgang. Eine weitere isolierte CH018-Via wäre damit kein belegter Durchgang.
Auch die bereits dokumentierte N-Ziel-Anbindung an U4.7 muss bei einer
späteren vollständigen Lösung ohne Power-Verdrängung geschlossen werden.
Der saubere Versuch wird deshalb ausdrücklich **nicht** zur Arbeitsbasis.

## Vier Elektrodennetze und neun MUX-Signale

Die vier offenen Elektrodennetze CH019_N_ELECTRODE, CH021_N_ELECTRODE,
CH025_P_ELECTRODE und CH029_P_ELECTRODE wurden auf der unveränderten
143er-Basis sequenziell in beiden Richtungen auf L1/L3 untersucht:
Raster 0,025 mm, Rand 18 mm, je Richtung 20 Sekunden/600000 Knoten,
Ø0,60-mm-Vias und harte Power-Sperre. Kein vollständiger Pfad wurde gefunden.

Die neun offenen MUX-Signale CH018_P/N, CH020_P/N, CH024_P/N,
CH028_N, CH029_N und CH030_N_MUX wurden danach auf derselben Basis
sequenziell in beiden Richtungen auf L1/L4 geprüft: Raster 0,025 mm,
Rand 18 mm, je Richtung 15 Sekunden/600000 Knoten und eine harte Sperre
für neue Via-Antipads im bestehenden L3-Power-Kupfer. Auch hier wurde kein
vollständiger Pfad gefunden. Es wurde kein isoliertes Probe-Via gespeichert.

Diese begrenzten, konservativen Suchen beweisen keine allgemeine
Unmöglichkeit. Pad-Bounding-Boxen und der Ausschluss neuer Vias im Pad-Bereich
begrenzen das Modell. Die Restliste bleibt bei insgesamt 76 MUX- und
67 Elektroden-Verbindungen, davon Block 2 mit 9 MUX- und 4 Elektroden-Netzen.

## Prozess, Nachweise und Release-Sperre

Die Apply-Prozesse der beiden vollständigen Versuche endeten jeweils vor
Zonenfill, nativer DRC und Parität in separaten Prozessen. Die verworfenen
Gegenmodelle und Suchläufe sind ausdrücklich von vollständig geprüften
Schaltungen getrennt. `replay_mux147_routes.py` und die freigegebene
147→143-Rezeptkette bleiben unverändert; deren Kupfer-Schutzregeln wurden
für die Nachbar-Umlegungen nicht gelockert.

Die Daten unter `followup-2026-10-15-corridor143/` enthalten Basis-DRC/Parität,
alle Suchergebnisse, beide vollständigen Versuche mit ihren DRC-/Paritäts-
und Geometrienachweisen sowie exakte Kupferdeltas gegen den gebundenen
143er-PCB-Hash. Die Deltas beschreiben ausschließlich diagnostische Versuche;
sie sind keine freigegebenen Schließungsrezepte oder Arbeitsarchive.
Die fünf vorhandenen Prozess-/Replay-Schutztests bestehen, darunter die
Abweisung unvollständiger Vias und unzulässiger L2-Routen.

Der saubere diagnostische Versuch 2 wurde außerdem aus seinem exakten
Kupferdelta auf einer neuen Kopie des gebundenen 143er-Archivs rekonstruiert.
Nach beendetem Apply-Prozess folgten frischer nativer Fill/DRC und Parität.
Der Replay liefert erneut 0/0/143 und 0 Paritätsbefunde sowie einen
bytegleichen PCB-Hash:
`14b05365a49bcb03b20afbcf704dc0f2b93d16365d241d4577d07573d09b0ddb`.
Auch dieser Replay wird nicht zur Arbeitsbasis und erzeugt kein neues
Arbeitsarchiv.

Auf Commit `ffd51da9b4d29ce9536bd582a5c7a1210fa4f371` sind sowohl
CI/validate (Run 38705379916) als auch der native KiCad-Audit
(Run 38705379965) erfolgreich. Letzterer bestätigt ausdrücklich das Fehlen
von Fertigungsexporten im Diagnosepaket. Die beiden älteren A1-Routing-Jobs
laufen beim Statusabruf noch; ihr späterer Export bleibt an das bestehende
Manufacturing-Gate gebunden. Sie arbeiten nicht am hier bestätigten
Engineering-Archiv.

`routing_completed=false` und `fabrication_release=false` bleiben gesetzt.
143 offene Verbindungen schließen eine Fertigungsfreigabe weiterhin aus.
In dieser Iteration wurden keine Gerber-, NC-Drill-, Pick&Place- oder
BOM-Dateien erzeugt. Der bestehende Schutz verlangt weiterhin vollständiges
Routing, saubere Prüfungen und explizite Release-Flags vor jedem Export.

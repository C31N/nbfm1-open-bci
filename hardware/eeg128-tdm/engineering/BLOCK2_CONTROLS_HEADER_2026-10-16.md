<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: U3-Steuerleitungen und J2-Header-Doglegs, 139er-Basis

**Zwei weitere vollständige Nachbar-Prüflinge sind nativ sauber und byteidentisch
replayt. Keine zusätzliche Luftlinie ist geschlossen.** CH018_P_MUX und
CH021_N_ELECTRODE bleiben offen. Beide Diagnosen bleiben `accepted=false`;
der bestätigte Routing-Checkpoint wird nicht ersetzt.

Die ausdrücklich genehmigten Inhalte von `fac9493` wurden auf
`codex/block2-escape-mesh-139-2026-10-16` als `6e5c78f` veröffentlicht.
Der vollständige Git-Dateibaum ist identisch:
`611619c33dbaadac1f20d5ddea6c7b37a8fb2570`.
Der normale Git-Zugang hatte keine Anmeldedaten; die verbundene GitHub-Verbindung
hat deshalb einen neuen Commit mit demselben Dateibaum erzeugt.

Alle PCB-Prüfungen verwenden weiterhin das bestätigte 139er-Archiv:

- ZIP SHA-256: `f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b`.
- PCB SHA-256: `f2780989e2dee6233f207df1f420f7e89d8e855493eb6b1e7fb731d4a4dda1ea`.

## Gemeinsame native Nachweise

| Prüfung | Steuerleitungs-Prüfling | Header-Prüfling |
| --- | --- | --- |
| KiCad | 8.0.9 | 8.0.9 |
| Fehler / Warnungen / Luftlinien | 0 / 0 / 139 | 0 / 0 / 139 |
| Paritätsbefunde / Netzregressionen | 0 / keine | 0 / keine |
| L3-Power-Verlust / -Zugewinn | exakt 0,0 / 0,0 mm² | exakt 0,0 / 0,0 mm² |
| Footprints, Zonenaußenkonturen, Projekt-/DRC-Regeln | unverändert | unverändert |
| Unabhängiger PCB- und ZIP-Replay | byteidentisch | byteidentisch |
| Neuer Routing-Checkpoint | nein | nein |

## U3.7: erstes Via-Fenster bei vollständig restituierten Steuerleitungen

Die S1-Diagnose mit rund 68,2 mm² erreichbarem F.Cu-Bereich wurde auf die
benachbarten S2-/S3-/EN-Brücken erweitert. Nach gemeinsamem Entfernen der
bezeichneten Brücken zeigt das Modell zunächst rund 8,7798 mm² Via-Fläche.
Diese hypothetische Fläche wird nicht als Routingfortschritt gewertet.

Der qualifizierte Gesamtprüfling stellt alle vier Steuernetze vollständig wieder her:

- MUX_S1 erhält einen vollständigen B.Cu-Ersatz zwischen seinen vorhandenen
  Übergängen. Der gefundene Weg benötigt keinen zusätzlichen Via und keine
  neue In2.Cu-Strecke.
- MUX_S2 verbindet den U3-Pad lokal auf F.Cu mit dem vorhandenen Übergang
  bei (45,0207 / 39,3061) mm. Die übrigen S2-Verbindungen bleiben erhalten.
- MUX_S3 und MUX_EN erhalten vollständige F.Cu-Ersatzführungen.

Gegenüber der 139er-Basis werden 19 Leiterbahnsegmente durch 20 Segmente
ersetzt. Es werden **keine Vias hinzugefügt oder entfernt**.

| Modell am P-Ziel U3.7 | Ergebnis nach vollständiger Restitution |
| --- | --- |
| Erreichbarer F.Cu-Bereich | rund 147,6642 mm² |
| Legale neue Via-Fläche außerhalb des Power-Keepouts | **0,010875699771 mm²** |
| Repräsentativer Via-Mittelpunkt | **46,841954 / 34,399999 mm** |

Die Fensterfläche ist ein konservatives Suchmodell mit tatsächlichen Padkonturen,
0,60/0,30-mm-Via-Vorgabe und 0,505-mm-Sperre um vollständige L3-Power-Konturen.
Im qualifizierten Diagnose-ZIP wird dort **kein P-Via gesetzt**. Die vollständige
Anbindung eines solchen Übergangs bleibt offen.

Die F.Cu-Endstücke vom RC-Quellpad und von U3.7 zu getrennt reservierten Vias
wurden im Modell vollständig gefunden. Der anschließende B.Cu/In2.Cu-Trunk
wurde weder im lokalen Fenster noch im erweiterten Fenster
X=0,5…95 / Y=0,5…130 mm vollständig gefunden. Reine F.Cu/B.Cu- und
F.Cu/In2.Cu-Gesamtversuche liefern ebenfalls keinen vollständigen P-Pfad.
Weitere Varianten mit separat reservierten S3-/EN-Endstücken und langen
B.Cu/In2.Cu-Steuertrunks scheitern an der gleichzeitigen Restitution.
Das sind begrenzte Suchergebnisse, kein Nachweis globaler Unroutbarkeit.

## CH021-N: vollständiger CH023-Header-Dogleg und CH027-Restitution

Der zweite qualifizierte Prüfling ändert ausschließlich CH027_P_ELECTRODE
und CH023_N_ELECTRODE. Die Pad-Escapes an den Widerständen bleiben erhalten.

CH023-N verlässt J2.24 auf F.Cu in einen rechten Header-Dogleg zum Übergang
bei etwa (50,4762 / 8,808369) mm. B.Cu/In2.Cu führt ihn vollständig zum
vorhandenen Quell-Escape zurück. CH027-P erhält eine vollständige lokale
F.Cu-Umleitung seiner sperrenden Mittelstücke. Gegenüber der Basis besitzt
CH023-N anschließend drei statt zwei Vias; CH027-P behält seine vier Vias.

Der erste Prüfling enthielt einen nur einlagig genutzten neuen CH027-Via.
Die native Warnung führte zur Ablehnung. Dieser für die Verbindung unnötige
Via wurde entfernt; erst der bereinigte Gesamtprüfling besteht 0/0/139 und
alle Replay-Gates. In der qualifizierten Variante bleibt kein isolierter neuer
Via-Drop zurück.

| CH021-Modell nach vollständiger Nachbar-Restitution | Ergebnis |
| --- | --- |
| Erreichbarer F.Cu-Headerbereich von J2.22 | rund 20,0193 mm² |
| Legale neue Header-Via-Fläche | **9,236889302641 mm²** |
| Freie Via-Fläche der bisherigen F.Cu-Quellkomponente | **0,0 mm²** |

Mit vorab reserviertem CH021-Quell-Escape und separaten Header-Doglegs gelingt
modellseitig die vollständige Wiederherstellung von CH027-P und CH023-N;
der gemeinsame CH021-B.Cu/In2.Cu-Trunk bleibt jedoch unvollständig. Die
bereits geprüfte c22-Quellöffnung wurde alternativ mit den neuen Header-Doglegs
kombiniert. Auch hier schließen die beiden End-Escapes und die Nachbarn,
aber nicht der gesamte zusätzliche Trunk. Diese Varianten bleiben ausschließlich
Planungsdaten mit `accepted=false`.

## Leitungslängen und verbleibende Arbeit

| Netz | Längenänderung gegenüber Basis |
| --- | ---: |
| MUX_S1 | +49,7111 mm |
| MUX_S2 | −22,1607 mm |
| MUX_S3 | +4,5787 mm |
| MUX_EN | +0,0798 mm |
| CH027_P_ELECTRODE | +7,9559 mm |
| CH023_N_ELECTRODE | +18,3126 mm |

Die längeren Wege sind Engineering-Diagnosen. Die native geometrische Prüfung
belegt keine Signalintegrität oder Rauschleistung. Eine spätere Übernahme würde
zusätzlich eine Bewertung und Optimierung der betroffenen Leitungswege erfordern.

Der nächste gezielte Schritt ist der Trunk-Zugang der nun nachgewiesenen
U3-Via-Komponente auf B.Cu/In2.Cu sowie eine CH027-Restitution, die zugleich
einen nutzbaren CH021-Quell- und Trunk-Korridor freihält. Bereits restituierte
Nachbarn werden dabei als reservierte vollständige Verbindungen behandelt.

## Replay, Tests und Freigabesperren

`replay_controls_header139.py` bindet beide Rezepte und das Ausgangsarchiv
an SHA-256. Die Anwendung endet vor separatem nativen Zonenfill/DRC;
Parität wird anschließend unabhängig geprüft. Nur bezeichnete Netze und Lagen
sind erlaubt. Neue/geänderte Vias müssen vor dem Schreiben an mindestens zwei
Lagen angebunden sein. Kupferdelta, Footprints, Regeln, Zonenkonturen, beide
exakten Power-Differenzen und PCB-/ZIP-Hashes werden vollständig geprüft.

```sh
/usr/bin/python3 hardware/eeg128-tdm/replay_controls_header139.py \
  --case controls --output-dir /tmp/controls139
/usr/bin/python3 hardware/eeg128-tdm/replay_controls_header139.py \
  --case header --output-dir /tmp/header139
```

Beide Replays sind erfolgreich ausgeführt. **55 Hardware-Tests bestehen** in
getrennten Prozessen entsprechend der nativen CI-Struktur; hinzu kommen
21 bestandene allgemeine Projekttests mit drei umgebungsbedingten Auslassungen.
Ruff, Zero-Debt, Python-Syntax, Hardware-Identität, EDA-Integrität und die
Fertigungssperre wurden lokal geprüft. Die Online-CI-Import- und
Typannotationsbefunde sind korrigiert; fünf weitere Schutztests und beide
neuen Replays sind in der nativen CI ergänzt.

Die beiden Diagnose-ZIPs, Rohberichte, Rezepte, Längen und 14 weitere
Planungsfälle liegen in `followup-2026-10-16-controls-header139/`.
`CONTROLS_HEADER139_2026-10-16_SHA256SUMS` bindet die neuen Nachweise und
sämtliche betroffenen Quellen an SHA-256. Der bestehende 139er-Checkpoint,
`routing_completed=false` und `fabrication_release=false` bleiben bestehen.
Keine Gerber-, NC-Drill-, CPL- oder BOM-Dateien wurden erzeugt.

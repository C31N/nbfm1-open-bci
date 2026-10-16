<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: vollständige CH018-P-/CH021-N-Trunks auf 139er-Basis

**Beide geforderten Verbindungen schließen gemeinsam in einem unabhängig
byteidentisch replayten 137er-Prüfling.** Der Gesamtprüfling besteht native
DRC, Parität, Nachbar-Restitution und das exakte Power-Gate. Alle neuen
Diagnosen bleiben `accepted=false`, `routing_completed=false` und
`fabrication_release=false`. Der bestätigte 139er-Checkpoint und
`current-routing-status.json` bleiben unverändert; die primäre Platine wird
nicht ersetzt. Die Untersuchung liefert noch keine Fertigungsfreigabe.

Basis ist das bestätigte Archiv `block2-ch019-electrode-closed139.zip`
(SHA-256 `f022d711bf860c6ec9383dae6f511c41189bf7348035d8d1e5e0e0ca6bcd6d1b`).
Sein ursprünglicher `replay_ch019_electrode.py` wurde erneut erfolgreich
mit byteidentischem PCB und ZIP ausgeführt. Die neuen Untersuchungen setzen
auf dem Branchstand `ee2ba6b` nach dem bestätigten Commit `9c096a1` auf.

| Unabhängiger Prüfling | Fehler / Warnungen / Luftlinien | Parität | Power-Verlust / -Zugewinn | PCB-/ZIP-Replay |
| --- | --- | --- | --- | --- |
| CH018-P mit vollständigen Nachbarn | 0 / 0 / 138 | 0 | exakt 0,0 / 0,0 mm² | byteidentisch |
| CH021-N mit vollständigen Nachbarn | 0 / 0 / 138 | 0 | exakt 0,0 / 0,0 mm² | byteidentisch |
| Gemeinsame Schließung | **0 / 0 / 137** | **0** | **exakt 0,0 / 0,0 mm²** | **byteidentisch** |

Alle Prüfungen verwenden KiCad 8.0.9. Footprints, Zonenaußenkonturen,
Projekt- und DRC-Regeln bleiben unverändert. Die native Netzprüfung findet
keine Regression. CH018_P_MUX, CH018_N_MUX, CH017_N_MUX, CH021_N_ELECTRODE,
CH023_N_ELECTRODE, CH027_P_ELECTRODE und die vier verlegten Steuernetze
sind im Gesamtprüfling vollständig verbunden.

## Trennung der B.Cu-/In2.Cu-Komponenten und CH018-P

Die neue Komponentenprüfung ergänzt die endliche Mesh-Suche. Sie verbindet
zusammenhängende freie Polygone auf B.Cu und In2.Cu nur über legale
Via-Flächen außerhalb der vollständigen Power-Zonenaußenkonturen. Im
begrenzten Fenster X=0,5…95 / Y=0,5…130 mm erreicht das U3-Ziel-Via den
rechten Bereich, aber keines der sechs untersuchten linken B.Cu-Quellfenster.
Die Diagnose ist ein konservatives Modell, kein globaler Unroutbarkeitsbeweis.

Die gezielte Entfernung einzelner In2.Cu-Trunks von CH017_N_MUX,
CH018_N_MUX, CH019_P_MUX oder CH020_N_ELECTRODE verbindet diese Bereiche
modellseitig. Reines Entfernen des CH017-N-Elektroden-B.Cu-Abschnitts genügt
nicht. Daraus folgt die erfolgreiche begrenzte CH017-N-MUX-Umlegung:

- Die bisherigen In2.Cu-Abschnitte vor dem Schnittpunkt (39,40 / 36,40) mm
  werden ersetzt; der anschließende Verlauf bleibt erhalten.
- Der Gesamtprüfling führt CH017-N vom vorhandenen Quell-Via
  (38,30 / 28,60) mm auf In2.Cu zum erhaltenen Trunk zurück.
- Der dadurch überflüssige alte B.Cu-Quell-Dogleg und sein Via bei
  (37,50 / 29,549999) mm werden entfernt. Es bleibt keine redundante
  Quellschleife und kein nur einlagig genutzter Via zurück.
- CH018-P nutzt das vorgegebene U3-Ziel-Via bei
  (46,841954 / 34,399999) mm und das Quell-Via bei
  (32,262500 / 35,646231) mm. F.Cu-End-Escapes und der durchgängige
  B.Cu-/In2.Cu-Trunk schließen das Netz vollständig.

Die bereits qualifizierte S1-/S2-/S3-/EN-Restitution wird vollständig
übernommen. CH018_N_MUX bleibt im Gesamtprüfling geometrisch unverändert.

Ein vorheriger vollständiger CH018-N-Trunk-Tausch erreicht ebenfalls
0/0/138, scheitert aber am exakten Power-Gate: Verlust
`1.9414969591480144e-07 mm²`, Zugewinn `4.2793195447059997e-08 mm²`.
Der unabhängige Replay reproduziert PCB und ZIP byteidentisch und bestätigt
die Ablehnung. Diese Werte werden weder gerundet noch als Toleranz akzeptiert.

## CH021-N: reservierter Quell-Escape und vollständige Restitution

Der Quell-Escape von R300.1 (36,15 / 18,20) mm wird vor der CH027-P-Restitution
zum Via bei (33,637364 / 19,491039) mm reserviert. J2.22 wird auf F.Cu zum
Header-Via bei (52,707002 / 7,486252) mm geführt. Der anschließende
B.Cu-/In2.Cu-Trunk ist vollständig, auch bei gleichzeitig geschlossenem CH018-P.

CH027-P erhält seine vollständige lokale F.Cu-Restitution bei unveränderter
Anzahl von vier Vias. CH023-N wird mit einem F.Cu-Header-Dogleg und einem
vollständigen B.Cu-/In2.Cu-Trunk zum bestehenden Quell-Escape restituiert;
die Via-Anzahl steigt von zwei auf drei. Ein im Suchaufbau entstandener,
nur auf F.Cu angeschlossener CH027-Via wird vor der Qualifikation entfernt.
Die native Warnung wird nicht übergangen.

Die getrennten Versuche mit entfernter CH020-N-In2.Cu-Führung finden
Quell-/Header-Escapes und CH021-Trunk, aber keine vollständige
CH020-N-Restitution. Sie bleiben unvollständige Suchmodelle. Erst die lokale
CH017-N-MUX-Umlegung ermöglicht die vollständige gemeinsame Restitution.

## Geometrie, Umfang und Grenzen des 137er-Prüflings

Gegenüber der unveränderten 139er-Basis werden 75 bestehende Kupferobjekte
ersetzt oder entfernt und 105 neue hinzugefügt. Das Replay prüft jede UUID,
jeden alten Kupferblock, erlaubte Netze/Lagen und mehrlagige Via-Anbindung
vor dem Schreiben. Neue Vias an Nachbarn sind ausschließlich für CH023-N
erlaubt; der alte CH017-Via darf nur mit seiner fest bezeichneten UUID entfallen.

Die unabhängige Prüfung aller 16 neuen Vias ergibt mindestens
1,353769 mm Abstand zur vollständigen L3-Power-Außenkontur, gegenüber der
geforderten 0,505-mm-Sperre. Die 27 neuen In2.Cu-Segmente bleiben mindestens
0,550001 mm entfernt, gegenüber 0,280 mm im Suchmodell. Bestehende Power-Voids
werden nicht als neue Via-Fenster benutzt.

| Netz | Länge im Gesamtprüfling | Änderung zur Basis | Vias vorher → nachher |
| --- | --- | --- | --- |
| CH018_P_MUX | 65,6531 mm | +65,1531 mm | 0 → 9 |
| CH018_N_MUX | 35,3721 mm | 0,0000 mm | 2 → 2 |
| CH017_N_MUX | 35,2632 mm | +1,8064 mm | 4 → 3 |
| CH021_N_ELECTRODE | 69,2976 mm | +69,2976 mm | 0 → 5 |
| CH023_N_ELECTRODE | 30,7906 mm | +17,6503 mm | 2 → 3 |
| CH027_P_ELECTRODE | 37,6582 mm | +11,0111 mm | 4 → 4 |

S1 bleibt gegenüber der Basis um 49,7111 mm verlängert. Das CH018-Paar ist
leitend vollständig; Laufzeitabgleich, Impedanz, Übersprechen, analoges
Settling und Rauschen sind hier nicht nachgewiesen. Die Längen- und
Via-Kosten sind in `net-lengths-inventory.json` vollständig offengelegt.
Diese Routing-Diagnosen werden deshalb nicht als fertiges Layout oder als
neuer bestätigter Release-Checkpoint ausgegeben.

Im Gesamtprüfling bleiben 74 MUX- und 63 Elektroden-Luftlinien offen.
Block 2 besitzt keine offene Elektrodenverbindung mehr; offen bleiben sieben
MUX-Netze: CH020_N, CH020_P, CH024_N, CH024_P, CH028_N, CH029_N und CH030_N.
Das 0/0/0-Gate ist weiterhin nicht erreicht.

## Replay und Integrität

`replay_trunks139.py --case p|n|joint --output-dir NEUES_VERZEICHNIS`
extrahiert stets die unveränderte 139er-Basis, prüft sie nativ, führt die
gepinnte Mutation in einem eigenen Prozess aus und prüft danach separat
Zonenfill/DRC, schematische Parität, exakte Kupfer-/Power-Geometrie sowie
PCB- und ZIP-SHA-256. Alle drei Fälle sind in der nativen CI verdrahtet.
Alle Release-Flags und `accepted=false` werden vor der Mutation geprüft.

- Gemeinsames PCB: `8d25968ffff8564334a4ba21c45c25b58dece7b27e2ca77be6118eb28817b187`.
- Gemeinsames ZIP: `50e62977c202838640dfb00a6580f1e010c71503711e8a8fb85c7244a9d4a6f3`.
- CH018-P-ZIP: `957b2f612755c78d8642e1b8bdbc66204668b36aade4748a36d286140166e02b`.
- CH021-N-ZIP: `c8ff56348c75392c0f03e88c101cdd5f3b15ca7a9f6f982ce3bb69d795e5238b`.

70 Hardware-Tests bestehen in getrennten Prozessen, darunter 15 neue
Replay-Guards für die drei vollständigen Prüflinge. Root-pytest besteht mit
21 PASS / 3 SKIP; Ruff und Zero-Debt bestehen. `--assert-blocked` bestätigt,
dass keine Fertigungsdateien erzeugt werden. Gerber, Drill, CPL und BOM
wurden nicht generiert.

Rohberichte, Rezepte, unabhängige Ergebnisse, Komponentenmodelle und
archivierte Suchquellen liegen unter `followup-2026-10-16-trunks139/`.
Die SHA-256-Manifeste binden jeden gelieferten Schritt an seine Prüfquellen.

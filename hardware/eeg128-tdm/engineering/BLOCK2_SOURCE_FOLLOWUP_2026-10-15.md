# Block-2-Fortsetzung ab dem bestätigten 147er-Stand – 2026-10-15

## Ergebnis und Arbeitsbasis

Ausgangspunkt ist der vom Nutzer bestätigte CH099-Stand, Online-Commit
`97649467eecf5a1d9359fdb39f5d0089b834968c`, mit unverändertem
147er-Archiv `block2-ch099-closed147.zip`. Archiv- und PCB-Hash wurden vor
Beginn geprüft; KiCad 8.0.9 bestätigte erneut 0 DRC-Verletzungen,
0 Warnungen und 147 Luftlinien. Das R38-VCM-Via bleibt auf **39,65/26,00 mm**.

Vier RC-/Elektroden-Verbindungen wurden nacheinander geschlossen:

| Neue Verbindung | Vorher → nachher | DRC-Verletzungen | Warnungen | Diagnostische Parität | L3-Power-Verlust |
| --- | --- | --- | --- | --- | --- |
| CH020_N_ELECTRODE | 147 → 146 | 0 | 0 | 0 | 0 mm² |
| CH023_N_ELECTRODE | 146 → 145 | 0 | 0 | 0 | 0 mm² |
| CH016_P_ELECTRODE | 145 → 144 | 0 | 0 | 0 | 0 mm² |
| CH027_N_ELECTRODE | 144 → 143 | 0 | 0 | 0 | 0 mm² |

Der neue Engineering-Stand liegt in **`block2-electrode-closed143.zip`**.
Er enthält ausschließlich PCB, PRO und DRU. Die vier Pfade nutzen L1 und
bereits freie L3-Bereiche; es wurden keine vorhandenen Power-Flächen für
Signaltrassen verdrängt. Auch der Power-Flächenzugewinn beträgt 0 mm².
Der kumulative Audit gegen die 147er-Basis bestätigt 102 neue Kupferobjekte,
kein geändertes oder entferntes bestehendes Kupfer, unveränderte Footprints,
Zonen-Umrisse und Projektregeln sowie keine Netzregression. Bestehende
Nachbar-Vias, VCM und das CH099-Paar bleiben erhalten.

PCB SHA-256: `497b588e580caf24766d5d60e9753def8dfe10ad3495b75faf5cd3fdd6276f24`

ZIP SHA-256: `e8d60a9835aea686af2d34d9e0e31b3a948b8c7dd2caae81c2c24786e4a3a8e1`

## CH018 zuerst: Quell- und Zielzugang getrennt untersucht

Die Quell-Anbindung von CH018_N an R38 bleibt bei **38,250/26,000 mm**.
Für CH018 wurden vollständige L1/L4-Trassen in beiden Richtungen gesucht
(Raster 0,025 mm, Rand 20 mm, A*-Budget 20 Sekunden/600000 Knoten).
Kein vollständiger Pfad wurde gefunden. Die vier gezielten L4-Probes ab
38,75/26,00 mm mit 0,01-mm-Raster fanden ebenfalls keinen Ausgang zu den
geprüften Nachbarkorridoren. Hierbei wurde kein Probe-Via als Kupfer gespeichert.

Das geometrische Modell zeigt an diesem Quellfenster eine eingeschlossene
L4-Tasche, begrenzt durch CH025_P_MUX, CH028_P_MUX, CH019_N_MUX und VCM.
Ihre Fläche beträgt rund **0,586526 mm²**; sie berührt den Rand des lokalen
Suchfensters nicht. Ein reiner Via-Positionsvergleich im Speicher ergibt
für X=39,45 mm rund **0,445685 mm²**. Die freigegebene Verschiebung vergrößert
also diese Tasche, öffnet im Modell jedoch keinen durchgehenden L4-Korridor.
Dies ist ein Modellvergleich, kein DRC-Nachweis einer hypothetischen Rückmutation.

Am N-Ziel U4.7 bei **41,135/58,150 mm** gibt es im konservativen lokalen
Modell geometrische Via-Fläche, aber keine davon erfüllt zugleich die
Vorgabe, das vorhandene L3-Power-Kupfer unverändert zu lassen. Das zuvor
verworfene Ziel-Via 41,135/59,650 mm wurde nicht erneut übernommen.
Die Suchergebnisse sind keine allgemeinen Unmöglichkeitsnachweise:
Fremd-Pads werden konservativ als Bounding-Box modelliert und neue
Via-Zentren im Pad-Bereich ausgeschlossen.

## CH020, CH024 und benachbarte Glieder

Für CH018/CH020/CH024 wurden Quelle und Ziel separat nach L1-Necks zu
Ø0,60/0,30-mm-Through-Vias untersucht (Raster 0,025 mm, Rand 8 mm).
P-seitig bestehen Fenster für CH018 und CH020. Die N-Quellen beider Kanäle
lieferten keines unter den vollständigen Modellbedingungen; ihre N-Ziele
lieferten kein Fenster ohne Power-Verdrängung. CH024 blieb an beiden Quellen
und am N-Ziel blockiert. Ein zusätzlich freigeschlossenes MUX-Paar durch die
VCM-Verschiebung ist damit nicht nachgewiesen.

Die direkten L1/L4-Suchen für CH020 und CH024 in beiden Richtungen fanden
keinen vollständigen akzeptierbaren Kandidaten. Auch CH028_N_MUX,
CH029_N_MUX und CH030_N_MUX wurden geprüft und bleiben offen.

Alle acht anfangs offenen Block-2-Elektrodennetze wurden erfasst. Für
CH020_N und CH023_N wurden zunächst getrennte L1-Necks/L4-Trunks geprüft;
dieser Ansatz blieb erfolglos. Die anschließenden L1/L3-Suchen mit harter
Power-Sperre führten zu den oben dokumentierten vier Schließungen.
CH019_N, CH021_N, CH025_P und CH029_P_ELECTRODE bleiben in den geprüften
Suchbudgets offen. `inventory143.json` bündelt die tatsächliche Restliste:
**76 MUX- und 67 Elektroden-Verbindungen**, davon in Block 2 noch 9 MUX-
und 4 Elektroden-Verbindungen.

Ein zunächst aus dem 147er-Modell übernommener CH023-Pfad kollidierte auf
der neuen 146er-Basis mit CH020. Die native Prüfung meldete 9 Verletzungen;
der Kandidat wurde gelöscht. CH023 wurde auf der 146er-Basis neu geplant
und erst nach einem eigenen sauberen Prüflauf übernommen. Die verworfenen
Diagnosen sind getrennt unter `rejected-ch023-overlap-*` gespeichert.

## Prozess, Replays und verbleibende Gates

`replay_mux147_routes.py` bindet jeden Eingangs-Archiv- und PCB-Hash.
Die Mutation läuft im Apply-Prozess; Zonenfüllung/DRC und diagnostische
Parität laufen danach in anderen Prozessen. Die Replay-Ketten werden
zusätzlich serialisiert. Die Original-PRO/DRU werden nach SaveBoard
wiederhergestellt und bytegleich geprüft. Einseitig angebundene Signal-Vias
werden vor jeder PCB-Schreiboperation abgewiesen; ein eigener Negativtest
prüft dies sowie den Schutz von L2. Ein unvollständiger Pfad wird nicht als
Kandidat übernommen.

Deterministische Kupfer-UUIDs ermöglichen bytegleiche PCB-/Archiv-Replays.
Die archivierten Rezepte binden auch die erwarteten Ausgangs-Hashes.
Jede übernommene Stufe wurde separat erneut abgespielt; die Rezeptkette
rekonstruiert den 143er-Stand aus dem ursprünglichen 147er-Archiv.
Die Prüfungen umfassen native 8.0.9-DRCs, diagnostische Parität,
Netzvergleich, gesamte gefüllte L3-Power-Geometrie und geschütztes Kupfer.

Reproduktion vom Repository-Root, mit einem neuen Ausgabeordner:

```bash
baseline=hardware/eeg128-tdm/engineering/block2-ch099-closed147.zip
output=/tmp/eeg128-followup-2026-10-15-NEU
for step in 147-146-ch020n 146-145-ch023n 145-144-ch016p 144-143-ch027n; do
  /usr/bin/python3 hardware/eeg128-tdm/replay_mux147_routes.py \
    --baseline-zip "$baseline" \
    --recipe "hardware/eeg128-tdm/engineering/followup-2026-10-15/$step-recipe.json" \
    --output-dir "$output/$step"
  baseline="$output/$step/candidate.zip"
done
```

`BLOCK2_WORKING_BASELINE.json` verweist auf den neuen 143er-Arbeitsstand;
die vorherigen 147er- und Recovery-Archive bleiben unverändert.
**`routing_completed=false` und `fabrication_release=false` bleiben gesetzt.**
Die lokale Routing-Fortsetzung erzeugte keine Gerber, NC-Drill-,
Pick&Place- oder BOM-Ausgaben. Nach der Veröffentlichung von `6fac6cb`
erzeugte der bereits bestehende native CI-Smoke-Test allerdings automatisch
`placement.csv` aus der primären PCB (Lauf `38704290646`). Das widersprach
der Vorgabe, vor dem 0/0/0-Gate keine Fertigungsartefakte zu erzeugen.
Dieser Export und sein Artefakt-Upload wurden aus dem nativen Workflow
entfernt und durch eine Kontrolle auf unerwartete Fertigungsdateien ersetzt.
Die beiden älteren A1-Export-Schritte (Placement sowie Gerber/Drill) sind
zusätzlich an einen nativen 0/0/0-Bericht und explizit gesetzte Release-Gates
gebunden; bei den weiter falschen Release-Flags werden sie übersprungen.
Die historische CI-CSV ist kein Bestandteil des 143er-Archivs und keine
Fertigungsfreigabe; ihre bereits erfolgte Erzeugung wird hier ausdrücklich
als Prozessabweichung dokumentiert.
Das 0/0/0-Gate ist bei 143 Luftlinien nicht erreicht. Die diagnostische
Parität verwendet weiter den PCB-abgeleiteten Schaltplan und ersetzt weder
einen unabhängigen Primärschaltplan-LVS noch Rückstrom-/Kopplungs-/Skew-
oder elektrische Qualifizierung.

Der nächste lokale CH018-Schritt ist ein überprüfter F.Cu-/B.Cu-Neck oder
eine kontrollierte Umlegung der begrenzenden bestehenden Leiterzüge; ein
weiteres isoliertes Via in der eingeschlossenen Quelltasche hilft nicht.
Die verbleibenden Block-2-Netze sind in der Restliste für die nächste Iteration
gebündelt. Alle neuen Nachweise bindet `MUX147_FOLLOWUP_2026-10-15_SHA256SUMS`.

# Block-2-Escape: geprüfter BANK-Korridor-Kandidat

## Ausgangspunkt

Der GitHub-Recovery-Stand `6974aab` (PCB-Sicherung `45bb114e`) wurde aus
`latest-pcb.zip` frisch entpackt. Das bestehende `CHECKPOINT_SHA256SUMS` ist in
einem Linux-Checkout vollständig gültig. `verify_recovery167.py` bestätigte
KiCad 8.0.9, 0 DRC-Verletzungen, 0 Warnungen, 149 offene Verbindungen
(78 MUX, 71 Elektroden/RC), keine neu geöffneten Netze und bytegleiches
Replay des 149er-Checkpoints.

## Lokale Änderung auf einer Kopie

Bei U3-Pad 7 (`CH018_P_MUX`, 41,135/45,150 mm) sperrte der bestehende
`BANK1_P_MUX_OUT`-Zug auf F.Cu bei Y=46,4358 mm den Zugang zu einem Via.
Das alte BANK-Via bei 41,7285/46,4358 mm sowie je ein daran angeschlossener
F.Cu- und B.Cu-Abschnitt wurden durch drei kurze F.Cu-Segmente, ein Via bei
34,7881/46,6358 mm und fünf B.Cu-Segmente ersetzt. Das Via hat Ø 0,60 mm
und 0,30 mm Bohrung. Die anderen Netze, Fußabdrücke, Zonen-Umrisse und
Projektregeln wurden nicht geändert.

Der neue Stand ist **ein Engineering-Kandidat mit weiterhin 149 offenen
Verbindungen**. Der native DRC nach Zonenfüllung ergab 0 Verletzungen und
0 Warnungen. Die Netzregression ist leer; insbesondere bleiben `3V3A` und
`BANK1_P_MUX_OUT` verbunden. Die gefüllte L3-Fläche von `3V3A` änderte sich
von 5075,565517424537 auf 5075,565517325985 mm² (numerisch rund
−0,000000099 mm²). Das ist keine Power-Integrity-Qualifizierung.

Der zusätzliche native DRC mit `--schematic-parity` ergab 0 Verletzungen,
0 Warnungen und 0 Paritätsbefunde bei 149 offenen Verbindungen; sein Bericht
liegt in `block2-bank-escape-drc-parity.json`. Er verwendet den im Recovery-Branch
enthaltenen, aus dem PCB erzeugten Diagnose-Schaltplan. Die unabhängige
Primärschaltplan-Parität ist damit nicht abgeschlossen.

Das freigelegte U3-Escape erlaubt dem Sucher einen legalen Ø0,60-mm-Via-Ort
für `CH018_P_MUX` bei etwa 40,485/46,500 mm. U4-Pad 7
(`CH018_N_MUX`) besitzt ein Fenster bei etwa 41,135/59,650 mm. Der
N-seitige Quellanschluss an R38 bei 38,250/26,000 mm bleibt blockiert:
Das CH025_P-Via bei 38,755/25,000 mm, die CH019_N-Rückseitenführung und
der VCM-Stamm begrenzen dort die möglichen Übergänge. Das probeweise
Entfernen des CH025_P-Vias und zweier B.Cu-Segmente ergab zwei native
Dangling-Fehler und 150 offene Verbindungen; dieser Versuch wurde verworfen.
Kein CH018-Paar wurde als geschlossen oder längengleich behauptet.

Ein begrenzter Ø0,60-mm-Escape-Suchlauf auf demselben Kandidaten fand für
`CH020_P_MUX` Quell- und Ziel-Fenster und für `CH020_N_MUX` ein Ziel-Fenster,
jedoch kein Fenster am RC-Quellanschluss. Bei CH024 fehlten Quell-Fenster für P und N
sowie das N-Ziel-Fenster; nur das P-Ziel lieferte einen Kandidaten. Diese
Suchergebnisse sind keine Unmöglichkeitsnachweise und wurden nicht als
Kupferänderungen übernommen.

## Nachweise und Status

`block2-bank-escape-recipe.json` enthält exakt drei Entfernungen und neun
Ergänzungen ausschließlich auf `BANK1_P_MUX_OUT`. `replay_block2_escape.py`
prüft Archiv- und Einzeldatei-Hashes, Ausgangs- und End-DRC, den
Netzregressionsschutz und den bytegleichen PCB-Hash. Das reproduzierbare
Archiv `block2-bank-escape-candidate.zip` hat SHA-256
`104d59f57f47df1f5e456287b9eda389fd0e30bc11f93b708f67670bd03002c4`;
der PCB-Inhalt hat SHA-256
`c8fefc8f70b4ae8adeb107a7389422b7f28737f20cbfa9aac6516a12d1446acb`.
`BLOCK2_ESCAPE_SHA256SUMS` bindet die neuen Artefakte und ist mit
`sha256sum --check BLOCK2_ESCAPE_SHA256SUMS` zu prüfen.

Beispiel aus dem Repository-Root in einer KiCad-8.0.9-Python-Umgebung mit
Shapely 2 (ein neues Ausgabeverzeichnis verwenden):

```bash
/usr/bin/python3 hardware/eeg128-tdm/replay_block2_escape.py \
  --baseline-zip hardware/eeg128-tdm/engineering/latest-pcb.zip \
  --recipe hardware/eeg128-tdm/engineering/block2-bank-escape-recipe.json \
  --output-dir /tmp/eeg128-block2-bank-replay-NEU
```

Der autoritative 149er-Checkpoint `latest-pcb.zip`, `STATUS.json` und
`RELEASE_STATUS.json` bleiben unverändert. `routing_completed` und
`fabrication_release` sind `false`. Die Primärschaltplan-Parität,
unabhängige LVS, P/N-Skew- und Rückstrom-Qualifizierung stehen weiter aus.
Es wurden keine Fertigungsdateien erzeugt.

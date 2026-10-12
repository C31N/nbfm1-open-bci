> Korrektur 2026-10-07: Die native Schaltplanparität enthält 398 Befunde im separaten JSON-Feld schematic_parity. Eine frühere PASS-Einordnung dieses 180er-Standes war unzutreffend. Aktueller Stand: ANALOG_CLOSURE_179.md.

# Analog-Priorisierung und tatsächlicher Routing-Start — 2026-10-07

**Weiterhin 0 DRC-Verletzungen / 0 Warnungen / 180 offene Verbindungen. Kein neuer Kupferstand wurde angenommen.**

## Priorität und realer Restbestand

| Priorität | Signalgruppe | Offen | Aktion |
|---|---|---:|---|
| Review vor weiterer Schließung | ADC0–ADC7 P/N und VCM/ADC_REFIN/ADS_CAP/CMS/DRL | 0 | Bestehende Paargeometrie und Referenzführung prüfen; Connectivity allein qualifiziert die Analogqualität nicht. |
| 1 | BANK0_N_BUFFER | 1 | Fehlende U17-Bufferverbindung nach R514 Pin1 schließen, am bestehenden P-Pfad orientiert. |
| 2 | CHxxx_P/N_MUX | 102 | Eingangspfade an den Multiplexern kanalweise als P/N-Paare behandeln; lokale Escapes und Trunk-Anschlüsse. |
| 3 | CHxxx_P/N_ELECTRODE | 77 | Hochohmige Steckverbinder-/RC-Eingangspfade, jeweils zusammen mit dem Gegenstück. |

Diese 180 Luftlinien betreffen am aktuellen Stand auch 180 unterschiedliche Netznamen. Es sind keine 180 vollständigen differentiellen Kanalpaare. Analog-Paare werden nach CH/BANK/ADC plus Segmentfamilie zusammengefasst. `analog-priority.json` enthält alle Endpunkte, Breiten, Layerlängen und Via-Zahlen.

## Paargeometrie und Referenzführung

- ADC6: P-Kupfer 19,246845 mm, N-Kupfer 11,839654 mm; Differenz 7,407191 mm und zwei Vias Unterschied.
- ADC7: Differenz 0,393617 mm und zwei Vias Unterschied.
- BANK0_BUFFER: P ist geschlossen und besitzt 57,488950 mm Kupfer auf L1, ohne Via. N besitzt nur den 0,650000-mm-Ausgangsstub und ist offen. Daraus darf keine fertige Paar-Längenbilanz abgeleitet werden.
- Die genannten Längen summieren sämtliche Leiterbahnen eines Netzes einschließlich möglicher Abzweige. Sie sind kein Laufzeit-/Impedanznachweis. Verbindliche Grenzwerte für Längendifferenz, Paarabstand, Via-Symmetrie, Eingangskapazität und Einkopplung sind hier nicht spezifiziert; ein Symmetrie-PASS wird nicht behauptet.
- L2 besitzt weiterhin die zusammenhängende AGND-Fläche mit einer gefüllten Insel. Lokale Aussparungen und Rückstromkontinuität müssen entlang der tatsächlich angenommenen Analogwege geprüft werden. Ein Inselkontakt allein ist kein flächendeckender Shielding-Nachweis.
- Guard-Ringe werden erst mit aus der Schaltung bestimmtem Potential und definiertem Treiber eingefügt. Ein beliebiger AGND-Ring ist bei hochohmigen EEG-Eingängen keine automatisch qualifizierte Maßnahme. Guard-Geometrie und Eingangskapazität bleiben Review-Punkte.
- L1 bleibt für empfindliche lokale Analogpfade bevorzugt. L4 wird nur als Engineering-Korridor verwendet; lange L4-Strecken bestehen nicht automatisch die vorhandene konservative Analog-Layer-Policy.

## Was tatsächlich ausgeführt wurde

1. Zielgerichteter BANK0_N_BUFFER-Pass: 150 Sekunden, 0,10-mm-Raster, bis 35 Sekunden pro Pfadsuche, separate Mutation und nativer Refill/DRC. Kein geeigneter Vorschlag gefunden; frisch geprüfter Ausgang bleibt 0/0/180.
2. Paarweise eingeschränkter MUX-Escape-Pass: CH008/011/016/017/018/019, jeweils P und N; 210 Sekunden, 0,05-mm-Raster. Kein Connectivity-Gewinn; Ausgang bleibt 0/0/180. Dieser Router unterstützt unabhängige Pfade, keinen vollständig gekoppelten Differentialpaar-Router. Der Audit macht die fehlende Paarqualifikation sichtbar.
3. BANK0-N-Nachbarführung diagnostisch vorbereitet: F.Cu-Leitweg nahe BANK0_P_BUFFER, anschließend lokale L1/L4-Suche zum ADC-Filterbereich um R514. Der 75-Sekunden-Tail-Suchlauf fand keinen vollständigen Weg. Der unvollständige Kandidat wurde nicht in den Checkpoint übernommen.
4. Native KiCad 8.0.9-Prüfung mit `--schematic-parity`: 0 Verstöße, 0 Warnungen, 180 offene Verbindungen. `drc-schematic-parity-180.json` enthält den vollständigen Nachweis. Das vorhandene Schema ist aus PCB-Padzuordnungen erzeugt; die Parität ist deshalb keine unabhängige Schaltungsprüfung.

Der verbleibende BANK0-Anschluss ist am Buffer-/ADC-Korridor blockiert. Das nächste konkrete Arbeitsziel ist ein gemeinsam betrachteter P/N-Korridor um U17 und R513/R514 mit lokalen Escapes/Layerwechseln. Geschlossene Nachbarn dürfen nur in atomaren, vollständig nativ geprüften Varianten verschoben werden. Die Netz-Regressionsprüfung schützt die geschlossenen POWER-, AGND-, MUX_CONTROL-, USB- und QSPI-Netze.

## Connectivity- und Release-Gate

Nach vollständiger Schließung folgen Refill, nativer Voll-DRC ohne Ausschluss von Unconnected Items und Schaltplanparität. Zusätzlich muss die Pin-/Netz-Zuordnung gegen die fachlich geprüfte Schaltungsquelle geprüft werden; ein erneut aus derselben PCB erzeugtes Schema liefert keine unabhängige Bestätigung. `routing_completed` wird erst mit nachgewiesener vollständiger Connectivity und 0/0/0 gesetzt. `fabrication_release` bleibt an sämtliche bestehenden Release-Gates und den Analog-Review gebunden.

Beide Flags bleiben `false`. Das 180er-PCB-ZIP und seine Kupfergeometrie wurden nicht verändert. Gerber, NC Drill, Pick&Place, BOM und `PUBLICATION_SHA256SUMS` bleiben unverändert.

```bash
# Mit unverändertem, fachlich geprüftem Schema neben der zu prüfenden PCB:
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128/eeg128-tdm.kicad_pcb
kicad-cli pcb drc --format json --severity-all --all-track-errors \
  --schematic-parity --output /tmp/eeg128/drc-parity.json /tmp/eeg128/eeg128-tdm.kicad_pcb
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

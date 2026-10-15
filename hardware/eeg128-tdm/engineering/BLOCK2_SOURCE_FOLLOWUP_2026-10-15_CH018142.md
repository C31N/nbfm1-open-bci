<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->
# Block 2: CH018-N geschlossen, Arbeitsstand 142 — 2026-10-15

## Ergebnis und verbindlicher Arbeitsstand

CH018_N_MUX verbindet R38.1 (38,250 / 26,000 mm) mit U4.7
(41,135 / 58,150 mm). Der unabhängige Replay ab dem freigegebenen
143er-Archiv reproduziert PCB und Engineering-ZIP byteidentisch.
CH018_P_MUX bleibt offen; das CH018-Paar ist nicht vollständig geschlossen.

| Prüfgröße | Bestätigter Wert |
|---|---:|
| Native KiCad-Version | 8.0.9 |
| Geometrische DRC-Fehler / Warnungen | 0 / 0 |
| Offene Verbindungen | 143 → **142** |
| Diagnostische Paritätsbefunde | 0 |
| Zusätzlicher Verlust / Gewinn gefüllter L3-Power-Fläche | **0,0 / 0,0 mm²** |
| Wieder geöffnete oder verschlechterte Netze | 0 |
| Verbleibende MUX- / Elektroden-RC-Verbindungen | 75 / 67 |
| Davon Block 2 | 8 / 4 |
| `routing_completed` / `fabrication_release` | false / false |

Die DRC-Luftlinien werden getrennt von geometrischen DRC-Verletzungen gezählt.
Die Paritätsprüfung verwendet weiterhin den PCB-abgeleiteten diagnostischen
Schaltplan. Sie ersetzt keine unabhängige Schaltplan-/LVS-Freigabe.

| Artefakt | SHA-256 |
|---|---|
| Eingang `block2-electrode-closed143.zip` | `e8d60a9835aea686af2d34d9e0e31b3a948b8c7dd2caae81c2c24786e4a3a8e1` |
| Eingangs-PCB | `497b588e580caf24766d5d60e9753def8dfe10ad3495b75faf5cd3fdd6276f24` |
| Ergebnis `block2-ch018n-closed142.zip` | `d084ed667e46e542b6dfe780e01f4f735e12f507e27492fc2226f9f194acd1d7` |
| Ergebnis-PCB | `6e562b5600a861c2933f81473b71aa47cc71b908f9060cf9c0d74e95d876c076` |
| Unveränderliche Mutationsrezeptur | `14156cd0dd7f53f6ae25a3400659aaad5065b49bc9f020ecce17c88cd09801e2` |

Aktueller Zeiger: [current-routing-status.json](current-routing-status.json).
Die primäre Pre-Route-Platine und ältere Recovery-/149er-Archive wurden nicht
als 142er-Arbeitsstand überschrieben. Es wurden keine Gerber-, NC-Drill-,
BOM- oder CPL-Dateien erzeugt.

## Gezielte Nachbarumlegung

Ein reiner L4-Neck löste die gesamte Quell- und Zielanbindung nicht.
Die übernommene Lösung kombiniert vollständige F.Cu/B.Cu-Nachbarumlegungen
mit der Übernahme eines bestehenden L3-Trunks. Dadurch bleiben insbesondere
die Antipad-Geometrien innerhalb der L3-Power-Zone erhalten.

1. **CH028_P_MUX:** Das Via bei 38,8366 / 27,0565 mm und seine drei
   lokalen Anschlusssegmente werden durch eine vollständige F.Cu/B.Cu-Route
   zwischen 41,2508 / 27,0565 mm auf F.Cu und dem vorhandenen Via
   38,8466 / 34,1843 mm ersetzt. Neue Vias: 41,346599 / 27,106499;
   40,071599 / 32,656499; 38,846599 / 32,431499 mm. Alle liegen vor
   dem Beginn der L3-Power-Zonen bei Y=37 mm. Diese Umlegung öffnete den
   ursprünglichen lokalen R38-B.Cu-Bereich nach unten.
2. **MUX_S0:** Das F.Cu-Segment zwischen 21,945 / 56,8757 und
   43,9869 / 56,8757 mm wird bei X=39,5 und X=42,5 aufgeteilt.
   Ein vollständig angeschlossener F.Cu-Umweg unterhalb der Padreihe schafft
   den Zugang von U4.7 nach oben. Keine neuen MUX_S0-Vias.
3. **VCM-Querleitung:** Beide überlappenden B.Cu-Segmente bei Y=36,4 mm
   erhalten denselben Durchgang zwischen X=36,3 und X=37,5 mm.
   Eine durchgehende, 0,20 mm breite L3-Verbindung zwischen den vorhandenen
   VCM-Vias 34,750 / 31,200 und 39,450 / 31,200 mm erhält die elektrische
   Verbindung beider Seiten. Sie verläuft vollständig in schon powerfreiem
   Raum. Das freigegebene R38-VCM-Via bei **39,650 / 26,000 mm** und
   dessen Anschluss bleiben unverändert.
4. **CH019_N_MUX → CH018_N_MUX:** Elf vorhandene L3-Segmente ab
   38,750 / 28,229999 mm und das vorhandene Via bei
   42,850 / 53,129999 mm wechseln ihre Netzzuordnung zu CH018_N_MUX.
   Ihre Kupfer-, Bohr- und Positionsgeometrie bleibt unverändert.
   Der neue R38-F.Cu-Neck führt zum Via **38,847 / 27,058 mm**, außerhalb
   des R38-Pads. Vier neue L3-Segmente schließen dieses Via an den bestehenden
   Trunk an. Der Zielanschluss vom vorhandenen Via nach U4.7 verläuft auf F.Cu.
5. **CH019_N_MUX bleibt geschlossen:** Die bisherige B.Cu-Zielzuführung
   wird durch eine vollständige neue B.Cu-Verbindung vom bestehenden
   Quellpfad bei 38,300 / 27,579999 mm zum vorhandenen Ziel-Via
   39,915 / 58,150 mm ersetzt. Das dadurch unnötige Via bei
   38,300 / 27,579999 mm wird entfernt; die Verbindung dort liegt vollständig
   auf B.Cu. Es bleibt kein einlagig angeschlossenes Probe-Via zurück.

CH025_P_MUX wird in dieser Lösung nicht verändert. Der Trassentausch vermeidet
eine weitere Verschiebung seines oberen Via-Riegels. Sämtliche Footprints,
Pad-Netzzuordnungen, Projektregeln und Zonenränder bleiben unverändert.
L2 wird nicht für Signalrouting verwendet.

Die Rezeptur beschreibt 37 entfernte Objekte, zwölf bestehende Objekte mit
reiner Netzänderung und 176 neue Kupferobjekte. Die vier neuen Vias besitzen
jeweils vollständige Kupferunterstützung auf zwei Lagen; die native Prüfung
meldet keine `via_dangling`-Warnung. Die bestehende additions-only-Replay-Kette
`replay_mux147_routes.py` bleibt unverändert. Nach dem CH019-N-Rückweg ist
der lokale B.Cu-Freiraum an R38 erneut begrenzt; die geschlossene CH018-N-
Verbindung verwendet deshalb ausdrücklich den übernommenen L3-Trunk.

## Verworfene Probes und entscheidende Erkenntnisse

| Probe | Native Fehler / Warnungen / Luftlinien | Entscheidung |
|---|---|---|
| CH028-Quellumlegung allein | 0 / 0 / 143 | Lokale Öffnung nachgewiesen, noch kein Abschluss |
| MUX_S0-Umweg nach Norden | 0 / 0 / 143 | Ziel-Neck weiterhin zu kurz eingeschlossen |
| MUX_S0-Umweg nach Süden | 0 / 0 / 143 | Zielzugang geöffnet, noch kein Abschluss |
| Schmaler VCM-Schnitt ohne Ersatzverbindung | 0 / 0 / 144 | VCM elektrisch geöffnet; sofort verworfen |
| Erweiterter VCM-Schnitt mit vollständigem L3-Ersatz | 0 / 0 / 143 | Größerer B.Cu-Bereich erreicht den geplanten Zielpunkt |
| CH018-N mit neuem Via bei 35,047 / 52,207999 mm | 0 / 0 / 142 | Power-Gate verworfen: Verlust `2.9047470490204747e-08 mm²` |
| CH018-N mit neuem Via bei 41,734999 / 53,499999 mm | 0 / 0 / 142 | Power-Gate verworfen: Verlust `5.944407245705687e-08 mm²` |
| Gemeinsamer CH018-P/N-Kandidat mit neuen Vias in Zonenlücken | 0 / 0 / 141 | Power-Gate verworfen: Verlust `2.5200337042708537e-07 mm²` |
| Direkter Replay desselben 141er-Kandidaten ab 143 | 0 / 0 / 141 | Identischer Power-Verlust; nicht übernommen |
| CH018-N mit geometrieerhaltendem Trunktausch | **0 / 0 / 142** | **Exakt null Power-Verlust/-Gewinn; unabhängig reproduziert** |

Die kleinen Flächenabweichungen der verworfenen Kandidaten wurden weder
weggerundet noch mit einer neuen Toleranz akzeptiert. Ihre bloße DRC-Sauberkeit
genügte nicht. Auch die unveränderte 143er-Basis wurde in der wiederhergestellten
KiCad-8.0.9-Laufzeit frisch gefüllt: exakt null Power-Verlust und -Gewinn.
Das Gate selbst bleibt unverändert streng.

## Replay und Prüfung

```sh
/usr/bin/python3 hardware/eeg128-tdm/replay_ch018_neighbors.py \
  --output-dir /tmp/ch018-reviewed-replay
/usr/bin/python3 -m unittest discover -s hardware/eeg128-tdm \
  -p test_ch018_neighbor_replay.py -v
```

Voraussetzung: KiCad 8.0.9 einschließlich Python-`pcbnew`, NumPy und Shapely;
das Ausgabeverzeichnis darf noch nicht existieren. Das Skript bindet die
Rezeptur an ihren fest eingetragenen SHA-256 und prüft die drei unveränderten
Projektdateien aus dem 143er-Archiv. Es serialisiert native Replays über
denselben Lock wie die bisherige additions-only-Kette.

Die Mutation läuft in einem eigenen, beendeten Apply-Prozess. Erst danach
folgen frischer nativer Zonenfill/DRC und eine gesonderte native Paritätsprüfung.
Unvollständige neue oder umgewidmete Vias werden vor dem PCB-Schreiben
abgewiesen. Der Supervisor verlangt die exakten Kupferänderungen, unveränderte
geschützte Geometrie, keine Netzregression, 0,0 mm² Power-Differenz in beiden
Richtungen sowie identische PCB- und ZIP-Prüfsummen. Erst dann entsteht
`candidate.zip` mit genau PCB/PRO/DRU.

Der neue Replay ist zudem in `kicad-native.yml` eingebunden. Der Native-Job
führt die fünf Guard-Tests und die tatsächliche 143→142-Reproduktion aus.
Die bestehenden Export-Sperren bleiben aktiv. Der Replay erzeugt ausschließlich
Engineering- und Prüfdateien.

Vollständige native Befunde, Rezepte, Suchpfade und verworfene Probes liegen in
[followup-2026-10-15-ch018](followup-2026-10-15-ch018/). Der unabhängige positive
Nachweis steht in [replay-result.json](followup-2026-10-15-ch018/replay-result.json).

## Verbleibende Arbeit

Die aktualisierte [Restliste](followup-2026-10-15-ch018/inventory142.json)
enthält 75 MUX- und 67 Elektroden-/RC-Verbindungen. Block 2:

- MUX: CH018_P, CH020_P/N, CH024_P/N, CH028_N, CH029_N, CH030_N.
- Elektroden: CH019_N, CH021_N, CH025_P, CH029_P_ELECTRODE.

Ein analoger Trunktausch für CH018_P wurde als nicht angewandtes Modell geprüft.
Der Quell-Neck zum vorhandenen Via 33,500 / 24,229999 mm war auffindbar;
für den vollständigen CH019-P-Rückweg und den Ziel-Neck vom Via
43,500 / 43,279999 mm ergaben die begrenzten Suchen keine Route. Es wurden
keine Teil-Vias eingebracht und keine P-seitigen Netzänderungen übernommen.

Am gesicherten 142er-Kandidaten wurden die vier Elektrodennetze jeweils in
beiden Richtungen auf L1/L3 geprüft: 0,025-mm-Raster, 20-mm-Rand,
20 Sekunden je Suchlauf, harte Power-Sperre. Die acht verbliebenen Block-2-
MUX-Netze wurden jeweils in beiden Richtungen auf F.Cu/B.Cu geprüft:
0,025-mm-Raster, 20-mm-Rand, 15 Sekunden je Suchlauf. Kein vollständiger
zusätzlicher Pfad wurde gefunden. Das sind begrenzte Suchergebnisse,
keine geometrischen Unmöglichkeitsbeweise.

Als nächster Schritt bleibt CH018_P mit einem vollständigen Quell-/Zielplan
priorisiert. Weitere Via-Positionen innerhalb bestehender Power-Zonenlücken
dürfen nicht allein aufgrund ihres nominalen Abstands als flächenneutral
angenommen werden: Maßgeblich bleibt der frisch gefüllte exakte Vergleich.
Es bestehen weiterhin keine Routing- oder Fertigungsfreigaben.

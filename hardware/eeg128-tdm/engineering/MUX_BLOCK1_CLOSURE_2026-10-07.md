> Historischer 178er-Checkpoint. Aktuelle Fortsetzung: MUX_BLOCK1_CORRIDOR_2026-10-07.md.

# MUX-Block CH000–CH015: erste angenommene Tranche — 2026-10-07

**KiCad 8.0.9: 0 DRC-Verletzungen / 0 Warnungen / 178 offene Verbindungen.** Eine Verbindung gegenüber dem 179er-Checkpoint geschlossen: CH011_P_MUX, RC-Stufe → U1. Der erste Block ist noch nicht abgeschlossen.

| Restbestand | Vorher | Jetzt |
|---|---:|---:|
| MUX gesamt | 102 | 101 |
| Elektroden/RC gesamt | 77 | 77 |
| Gesamt | 179 | 178 |
| MUX CH000–CH015 | 9 | 8 |
| Elektroden/RC CH000–CH015 | 14 | 14 |

## Konkrete Trace-Führung

Die RC-Verbindung von R279.2 (19,750 / 20,800 mm) zu R23.1 (20,250 / 20,800 mm) bleibt unverändert. Der neue Drop-Via bei (20,150 / 20,800 mm) liegt auf diesem vorhandenen 0,50-mm-Trunk. Eine redundante neue Überlappungsstrecke wurde entfernt. Der MUX-Drop bei (15,595 / 35,750 mm) wird mit U1.20 (15,595 / 35,850 mm) verbunden. Beide Endpunkt-Vias: Ø0,60 / Bohrung0,30 mm.

Der neue 0,15-mm-Signalweg verwendet feste L1/L4-Korridore mit vier weiteren Ø0,65/0,30-mm-Übergängen:

| Übergang | X mm | Y mm |
|---|---:|---:|
| L4 → L1 | 19,494999 | 27,050 |
| L1 → L4 | 13,994999 | 27,750 |
| L4 → L1 | 13,894999 | 32,350 |
| L1 → L4 | 14,294999 | 33,550 |

Alle Eckpunkte sind in `mux-block1-ch011p-path.json`, die tatsächlich angenommenen Kupferblöcke in `mux-block1-recipes.json` hinterlegt. Insgesamt sechs Signal-Vias. Die Strecke schließt eine Luftlinie, ist aber **noch keine kompakte oder symmetrisch gekoppelte P/N-Führung**.

CH011_N_MUX bleibt offen, ebenso CH011_P_ELECTRODE (Connector → RC). Damit wurde noch kein zusätzlicher vollständiger Connector-/RC-/MUX-P/N-Kanal geschlossen. Im Block bleiben diese acht MUX-Verbindungen offen: CH002_N, CH004_N, CH005_N, CH008_P, CH008_N, CH010_N, CH011_N und CH014_N. Die schon vorhandenen Gegenleitungen wurden nicht zurückgebaut.

Es wurden kanalweise feste RC-/MUX-Drop-Punkte, unterschiedliche Endlayer, außen liegende Pin-Escapes und 0,60-mm-Zwischenvias geprüft. CH008 wurde zusätzlich mit expliziten versetzten L-Escapes untersucht. Diese weiteren Versuche lieferten keine angenommene Verbindung. Der Pfadplaner bildet die tatsächlich gewählte Via-Geometrie jetzt als Parameter ab; die bisherigen 0,65-mm-Defaults und sämtliche nativen Clearance-Regeln bleiben erhalten. Kandidaten unter 0,60 mm werden vom Helper zurückgewiesen.

## Lokale AGND-Anbindung und Rückstromprüfung

Ein kurzer 0,20-mm-F.Cu-AGND-Streifen wurde von (20,250;19,700) zu (20,950;19,700) mm geführt. Beide Enden besitzen Ø0,65/0,30-mm-Vias mit realem Kontakt zur gefüllten L2-AGND-Fläche. Länge 0,70 mm. Dies ist eine angebundene lokale Guard-Struktur im RC-Bereich, **kein geschlossener Guard-Ring um den gesamten Signalweg**.

Zwei zunächst einzeln platzierte AGND-Vias wurden wegen zwei nativer `via_dangling`-Warnungen verworfen. Erst der mit F.Cu-Kupfer an beiden Enden verbundene Streifen wurde mit 0 Warnungen übernommen. Der abgelehnte Bericht bleibt als `mux-block1-rejected-stitching.json` dokumentiert.

AGND/L2 bleibt eine gefüllte Insel, jetzt mit 151 Via-Kontakten (zuvor149). L3 bleibt mit je einer angebundenen Insel unverändert: 3V3A=39, 5V_ISO=8, 3V3D=23 Via-Kontakte. Keine gefüllte Insel ohne gleichnamigen Via-Kontakt.

Die Abtastung mit ≤0,05-mm-Schritt findet L2-AGND unter 66,81 % der CH011_P-Mittellinie auf L1 und 79,58 % auf L4. Die gesamte abgetastete L4-Länge von etwa 13,899 mm liegt ohne gefüllte L3-Powerzone darüber. Fehlende L2-Treffer enthalten Signal-Via-Antipads; sie sind weder ein Beweis für einen Plane-Split noch ein Nachweis ausreichender lokaler Rückstromführung. Der native DRC und eine einzige globale GND-Insel ersetzen keinen elektrischen Rückstromnachweis. Für CH011_N ist nur der vorhandene kurze RC-Trunk berücksichtigt, da seine MUX-Strecke noch offen ist.

`return_current_qualified`, `pair_coupling_qualified` und `guard_ring_qualified` bleiben `false`. Die RC-/MUX-Drop-Vias liegen in SMD-Padbereichen und benötigen vor Fertigungsfreigabe eine Prüfung des Füll-/Kappen-, Masken- und Lötprozesses. Es wurde keine Fertigungsfreigabe erteilt.

## Unveränderte ADC- und Paritätsnachweise

ADC6/ADC7-Kupfer wurde nicht verändert. Via-Anordnung und Kupferlängendifferenzen bleiben wie im vorherigen Checkpoint (<0,001 mm). Die weiterhin offenen elektrischen Kopplungs-, Referenz- und Guard-Prüfungen wurden nicht als erledigt markiert.

Native Diagnose-Parität: 0 Befunde; erneuter nativer XML-Abgleich: 2.054/2.054 Pin-/Netzzuordnungen stimmen mit dem Engineering-Board überein. Der Diagnose-Schaltplan ist PCB-generiert und liefert weiterhin keinen unabhängigen Primärschaltplan-LVS-PASS.

## Reproduktion und Release-Gate

Nur neue Kupferblöcke auf CH011_P_MUX und AGND werden hinzugefügt; keine bestehende Leitung, Pad-/Netzzuordnung, Footprint-Position, Zonen-Umriss oder DRC-Regel wird verändert. Mutation, Fill und DRC laufen in getrennten Prozessen. Der unabhängige Replay erzeugt bytegenau dieselbe PCB, reproduziert 179 → 178 und weist keine Regression eines anderen Netzes nach. Hardware-/BOM-/CPL-Identität: 642 Positionen, PASS.

`routing_completed=false`, `fabrication_release=false`, `schematic_parity_passed=false`. Primäre KiCad-Dateien, PUBLICATION_SHA256SUMS, BOM und CPL bleiben unverändert; keine Fertigungsartefakte erzeugt oder überschrieben.

Vom Repository-Root mit KiCad-8-Python, kicad-cli, numpy und shapely; neue Ausgabeordner verwenden:

```sh
unzip hardware/eeg128-tdm/engineering/mux-block1-baseline-179.zip -d /tmp/eeg128-mux-base
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-mux-base/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/mux-block1-recipes.json \
  --output-dir /tmp/eeg128-mux-replay
cp hardware/eeg128-tdm/engineering/eeg128-tdm.kicad_sch /tmp/eeg128-mux-replay/
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity \
  --output /tmp/eeg128-mux-replay/drc-parity.json /tmp/eeg128-mux-replay/eeg128-tdm.kicad_pcb
/usr/bin/python3 hardware/eeg128-tdm/audit_analog_return_geometry.py \
  --board /tmp/eeg128-mux-replay/eeg128-tdm.kicad_pcb \
  --net CH011_P_MUX --net CH011_N_MUX \
  --output /tmp/eeg128-mux-replay/return-geometry.json
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der Replay führt den nativen Python-Zonen-Fill vor und nach der Mutation aus. Ein separater Fill für eine Archivkopie ist möglich mit:

```sh
/usr/bin/python3 hardware/eeg128-tdm/fill_zones.py /tmp/eeg128-mux-replay/eeg128-tdm.kicad_pcb
```

## Nativer DRC-Kopfbericht

```json
{
  "kicad_version": "8.0.9",
  "date": "2026-10-07T15:26:26+0500",
  "source": "eeg128-tdm.kicad_pcb",
  "violations": 0,
  "warnings": 0,
  "unconnected": 178,
  "schematic_parity_items": 0,
  "schematic_parity_warnings": 0,
  "independent_lvs_signoff": false
}
```

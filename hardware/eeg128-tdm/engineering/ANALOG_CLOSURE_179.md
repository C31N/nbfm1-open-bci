> Historischer BANK0-Checkpoint. Aktueller ADC6/ADC7- und Paritätsstand: ANALOG_ADC67_PARITY_2026-10-07.md.

# Analog-Checkpoint 179 — 2026-10-07

Native KiCad 8.0.9: **0 Verletzungen, 0 Warnungen, 179 offene Verbindungen**. Gegenüber Checkpoint 180 wurde genau BANK0_N_BUFFER geschlossen. Keine andere Netzgruppe wurde wieder geöffnet. POWER, AGND, MUX_CONTROL und QSPI bleiben geschlossen. Offen: 102 Multiplexer- und 77 Elektroden-/RC-Verbindungen.

## Angenommene Geometrie

BANK0_N_BUFFER: F.Cu-Trace 0,15 mm von U17 über (59,1375;66,45), (59,6;66,45), (61;67,85), (64,5;67,85), (69,9;73,25), (107,6;73,25) nach (107,6;73,6) mm. L3/In2.Cu weiter über (108,7;74,15), (110,4;74,15), (111,1;73,8), (114,2;73,8) nach R514 (115,2;72,8) mm. Durchgangsvias Ø0,65/Bohrung0,30 mm an beiden L3-Enden. Das Via an R514 liegt im Pad; Assembly-/Maskenqualifikation bleibt ausstehend. BANK0_P bleibt auf L1. Die einseitige L3-Migration ist ein Engineering-Zwischenstand, kein Symmetrie-Signoff.

ADC7_P: Ein Teil der vorhandenen L1-Diagonale wurde über L4 geführt, mit zwei Vias Ø0,60/Bohrung0,30 mm bei (134,42;69,9948) und (132,211;72,2045) mm. ADC7 hat jetzt P=2/N=2 Vias gleicher Geometrie. Positionssymmetrie, Paarabstand und Längenfreigabe sind weiterhin offen.

ADC6: P=2/N=0 Vias, Kupfer-Gesamtlängendifferenz ungefähr 7,407 mm. Der N-L4-Diagonalversuch kollidierte mit vorhandenen BANK-/ADC-Trunks und einem ADC0_N-Via; der alternative P-L1-Suchlauf fand keinen Pfad. Beide Versuche verworfen. Es wurden keine zusätzlichen Vias allein zur kosmetischen Angleichung der Anzahl eingebaut.

Ein gemeinsamer BANK0-P/N-L3-Versuch erreichte zwar 179 Luftlinien, erzeugte aber Kurzschluss-/Clearance-/Bohrabstandsfehler zu BANK2_P, BANK5_P und BANK6_P. Er ist verworfen und separat dokumentiert. DRC-Regeln wurden nicht abgeschwächt.

## Nachweise und Grenzen

Mutationen und Zonen-Fill/native DRC liefen in getrennten Prozessen. Das hashgebundene Rezept wurde unabhängig vom exakten 180er-Archiv wiederholt: 0/0/179, ohne Rückschritt anderer Netze. **Schaltplanparität NICHT sauber:** Native KiCad meldet 398 Paritätsbefunde im separaten Feld `schematic_parity`; sie sind identisch zum 180er-Checkpoint. Darunter sind Footprint-/Wert-Abweichungen und Pad-Netzkonflikte. PCB-DRC 0/0/179 darf nicht als Paritäts-/LVS-PASS interpretiert werden. Die frühere Meldung zur sauberen Parität war unzutreffend. Kein unabhängiger Schaltungs-LVS-Signoff.

Nach Refill bestehen weiterhin genau vier angebundene Kupferinseln: AGND/L2 mit 149 Via-Kontakten; L3: 3V3A=39, 5V_ISO=8, 3V3D=23. Keine Insel ohne gleichnamigen Via-Kontakt. Dies qualifiziert weder Rückstrompfade noch Shielding/Guarding. Hardware-Identität/BOM/CPL: 642 Positionen, PASS.

`routing_completed=false`, `fabrication_release=false`. Primäre Fertigungs-PCB, Gerber/Drill/Pick&Place/BOM und PUBLICATION_SHA256SUMS wurden nicht erzeugt oder überschrieben.

## Reproduktion (KiCad-8-Python und CLI)

```sh
unzip hardware/eeg128-tdm/engineering/analog-baseline-180.zip -d /tmp/eeg128-baseline-180
/usr/bin/python3 hardware/eeg128-tdm/replay_copper_checkpoint.py \
  --board /tmp/eeg128-baseline-180/eeg128-tdm.kicad_pcb \
  --recipe hardware/eeg128-tdm/engineering/analog-prio1-recipes.json \
  --output-dir /tmp/eeg128-replay-179
(cd hardware/eeg128-tdm/engineering && sha256sum --check CHECKPOINT_SHA256SUMS)
```

Der bestehende RP2040-/U23-Bericht dokumentiert den vorigen 180er-Stand; maßgeblich für diesen Checkpoint sind drc-native.json, STATUS.json und latest-pcb.zip. Nächster Layout-Prüfpunkt: echte ADC6-P/N-Layerarchitektur und ADC7-Positionssymmetrie, anschließend P/N-gekoppelte MUX-Escapes und AGND-Guarding.

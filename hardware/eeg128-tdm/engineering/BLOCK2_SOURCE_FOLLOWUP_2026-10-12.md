# Block-2: CH018-N-Quellfenster und begrenzter Paarversuch – 2026-10-12

## Ergebnis

Der Online-Kandidat aus Commit `4433c0e0608c564e093f5348231afe8455dcf28e` ist lokal exakt reproduziert: PCB-SHA `c8fefc8f70b4ae8adeb107a7389422b7f28737f20cbfa9aac6516a12d1446acb`, ZIP-SHA `104d59f57f47df1f5e456287b9eda389fd0e30bc11f93b708f67670bd03002c4`. Native KiCad 8.0.9: 0 DRC-Verletzungen, 0 Warnungen, 149 Luftlinien; zusätzliche diagnostische Paritätsprüfung: 0 Befunde. Dies ist kein unabhängiger LVS-Pass.

Eine weitere lokale VCM-Korrektur erhält diesen Status: **0 / 0 / 149**, keine Netzregression. Es wurde **kein CH018-Paar geschlossen**. Die autoritative `latest-pcb.zip`, `STATUS.json` und beide `RELEASE_STATUS.json` bleiben unverändert; Routing- und Fertigungsfreigabe bleiben `false`.

## Geometrischer Nachweis

- VCM-Via an R38: von X=39,45 / Y=26,00 auf **39,65 / 26,00 mm** verschoben; Ø **0,65 / Drill 0,30 mm** unverändert.
- F.Cu-VCM-Segment: von (39,85;26,00)–(39,45;26,00) auf (39,85;26,00)–(39,65;26,00) verkürzt; **0,20 mm Breite**.
- Zusätzliche B.Cu-Verbindung: (39,65;26,00)–(39,45;26,00), **0,25 mm Breite**, Länge **0,20 mm**. Der bestehende lange VCM-Stamm ist unverändert.

Die Änderung betrifft exakt zwei vorhandene VCM-Objekte und eine neue Verbindung. Projekt-/DRC-Regeln, Footprints, Zonen-Umrisse und ADC6/ADC7-Kupfer bleiben unverändert. Gegen den BANK-Kandidaten ist die gefüllte L3-Power-Fläche **nach nativem Refill geometrisch identisch: 0 mm² Verlust, 0 mm² Zugewinn**. Das ersetzt keinen VCM-Settling-, Kopplungs-, Rückstrom- oder Power-Integrity-Signoff.

Die VCM-Verschiebung schafft im Suchmodell ein N-Via-Fenster bei **38,75 / 26,00 mm** mit einem 0,50-mm-F.Cu-Neck von R38. Ein isolierter Probeaufbau dieses Ø0,60/0,30-mm-Vias hatte keine Clearance-Verletzung, aber **eine `via_dangling`-Warnung**, da nur F.Cu angeschlossen war. Dieser Probeaufbau wurde verworfen und ist nicht Bestandteil des sauberen Kandidaten.

Die bereits geschlossene `CH028_P_MUX`-Führung blockiert den direkten B.Cu-Ausgang zusätzlich (Via bei 38,8366 / 27,0565 mm sowie Rückseiten-Trunk). Für das N-Signal wurden lokale L3-Pfade aus der RC-Tasche bis (40,00;25,30) bzw. (40,50;24,70) gefunden. Ein weiterer Suchpfad erreicht ein modellgeometrisch freies Through-Via-Fenster bei (43,60;25,00). **Diese Pfade wurden nicht als durchgehend geroutetes Kupfer übernommen.**

Acht normale B.Cu/In2.Cu-Paarversuche und vier Versuche mit vorgegebenem L3-Escape/Wegpunkt fanden keinen vollständigen akzeptierten P/N-Pfad innerhalb der jeweiligen Suchbudgets. Das ist kein Unmöglichkeitsnachweis. Der nächste konkrete Schritt ist die manuelle oder interaktive Trunk-Führung hinter dem Fenster (43,60;25,00) unter Schutz der U3/U4-3V3A-Zuführungen; dabei CH018_P und CH018_N gemeinsam vollständig anschließen.

## Replay und Integrität

`replay_block2_source_window.py` bindet den BANK-Baseline-Archivhash und alle drei Projektdateien. Die Mutation erlaubt nur die zwei exakt identifizierten VCM-Endpunktverschiebungen sowie das 0,20-mm-B.Cu-Linkstück. Mutation und native Zonenfüllung/DRC laufen in getrennten Prozessen. Der gültige Datensatz besteht; **8 negative Rezeptvarianten** (Netz, Position, Via-Geometrie, Layer, Umfang, fehlender Link, doppelte UUID, falsches Original) werden vor einer PCB-Schreiboperation abgewiesen.

Das frische Replay erreicht denselben PCB-Hash wie der VCM-Kandidat. Der neue Kandidat enthält genau PCB, PRO und DRU und bleibt Engineering-only. Die beiden vollständigen P/N-Suchprotokolle und der verworfene Via-Probebericht sind separat gespeichert.

Reproduktion aus dem Repository-Root in einer KiCad-8.0.9-Python/CLI-Umgebung; ein neues Ausgabeverzeichnis verwenden:

```bash
/usr/bin/python3 hardware/eeg128-tdm/replay_block2_source_window.py \
  --baseline-zip hardware/eeg128-tdm/engineering/block2-bank-escape-baseline-4433c0e.zip \
  --recipe hardware/eeg128-tdm/engineering/block2-vcm-source-recipe.json \
  --output-dir /tmp/eeg128-source-window-NEU
cd hardware/eeg128-tdm/engineering
sha256sum -c BLOCK2_SOURCE_FOLLOWUP_SHA256SUMS
sha256sum -c CHECKPOINT_SHA256SUMS
```

Fertigungspfad und primäre PCB wurden nicht geändert. P/N-Skew, Rückstrom-/Guard-Qualifizierung und unabhängiger Primärschaltplan-LVS bleiben offen.

## Gebundene Hashes

```text
VCM-Kandidaten-PCB feb5eeedd8458e05fc9a7e3756b28b63555f81da3fd8720d63857706b2a798b7
VCM-Kandidaten-ZIP 777b9f77a975e441b75279e3b83f105db7bdcc47306ba52e8ea066104ad74672
Autoritativer 149er-ZIP 71ffc3d06dd38d3c2c9434549f711e8356cba4ee8acaa54fb52f92140443c2b0
```

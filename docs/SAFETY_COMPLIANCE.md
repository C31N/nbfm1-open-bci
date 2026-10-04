<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Hardware Safety, Human-Subject Use and Regulatory Compliance

## 1. Status of this project

The NBFM-1 Open BCI Stack and EEG128-TDM hardware are **research engineering prototypes**.

They are not represented as:

- CE-marked medical devices;
- MDR-conforming finished medical devices;
- FDA-cleared, FDA-approved or FDA-exempt finished devices;
- IEC 60601-1 certified medical electrical equipment;
- IEC 60601-1-2 certified EMC systems;
- ISO 14971-compliant risk-managed finished medical devices;
- IEC 62304-compliant medical-device software;
- IEC 62366-1 validated usability-engineered medical devices;
- clinically validated diagnostic or therapeutic systems.

The regulatory classification of any derivative depends on its **actual intended purpose, claims, users, patient population, risk and jurisdiction**. In the European Union, a product can fall under Regulation (EU) 2017/745 when the manufacturer's intended purpose is medical. Software classification can be affected by MDR Rule 11. In the United States, device classification and any 510(k), De Novo, PMA, IDE or exemption pathway must be determined for the actual device and intended use.

There is no blanket "FDA Class II/III exemption" for this project.

## 2. Mandatory research-prototype restrictions

When any electrode, DRL/reference electrode, fNIRS optode assembly or other conductive patient/subject interface is attached to a person, the following project rules apply.

### 2.1 Power

The patient-connected analog domain shall be powered only from an isolated battery-operated domain.

**Prohibited while a subject is connected:**

- charging the patient-connected battery from mains;
- connecting a non-isolated bench supply;
- connecting an earth-referenced oscilloscope or logic analyzer;
- connecting a desktop PC, powered USB hub or mains-powered SBC directly to the patient-connected USB/data domain;
- defeating protective resistors, isolation barriers or enclosure interlocks.

Disconnect the subject before charging, probing, programming or attaching non-isolated laboratory equipment.

### 2.2 USB/data isolation

A USB connection that crosses from a patient-connected battery domain to a mains-referenced host shall use a separately engineered isolation barrier.

An **ADuM3160-class USB isolator** may be used only as a research-prototype data-isolation component for USB low/full-speed links. The ADuM3160 family supports USB low/full speed, up to 12 Mbit/s, and provides a rated digital isolation barrier. It is **not, by itself, proof of IEC 60601-1 compliance**, a complete Means of Patient Protection, or a substitute for creepage/clearance, isolated power, leakage-current, dielectric-strength and system-level verification.

If a final design requires high-speed USB, use an isolation architecture explicitly designed for that data rate and re-run the complete safety analysis.

### 2.3 DRL / driven reference

The driven-reference output shall:

- include current-limiting impedance located close to the patient connector;
- default to a high-impedance/non-driving state on firmware reset, power loss or op-amp fault where practicable;
- have bounded loop bandwidth;
- be tested for oscillation and worst-case DC output;
- not be used to claim patient protection.

For prototype work, use at least one high-value series resistor in the driven electrode path; a production medical design should evaluate redundant current limiting and single-fault behavior under the applicable standard.

### 2.4 Electrode inputs

Each subject-contacting acquisition conductor shall include input-current limiting and ESD/transient design appropriate to the intended environment.

The present low-cost TDM architecture does not, merely by including high-value resistors, demonstrate compliance with IEC 60601 patient-leakage-current limits or defibrillation protection.

### 2.5 Mechanical and optical safety

For fNIRS derivatives:

- calculate optical irradiance and thermal rise at the skin;
- enforce LED/laser current limits in hardware where feasible;
- use only emitters suitable for the wavelength and power;
- perform skin-contact and thermal testing;
- assess applicable photobiological safety requirements.

For head-mounted assemblies:

- eliminate exposed conductive edges;
- strain-relieve all electrode leads;
- prevent connector pins from becoming accessible during use;
- evaluate mechanical pressure points and skin-contact materials.

## 3. Required isolation architecture for human-connected bench research

Minimum research topology:

```text
                       PATIENT-CONNECTED DOMAIN

electrodes
    |
input protection
    |
EEG128-TDM analog front end
    |
battery-only isolated power
    |
MCU / local acquisition
    |
    +---- isolated data barrier ----> non-isolated host
          e.g. engineered
          ADuM3160-class FS USB
          barrier where bandwidth
          is sufficient

NO galvanic mains path to the patient-connected side
```

A USB isolator does not isolate a separate charger, oscilloscope ground, shield bond or any other parallel path. Every conductive path must be included in the isolation analysis.

## 4. Release gates before any human-connected prototype

Before attaching a revision to a person, document and pass at minimum:

1. schematic ERC and PCB DRC;
2. visual inspection and continuity/short test;
3. power-rail current-limit startup;
4. isolated-domain verification;
5. measured DC resistance from every subject-contacting conductor to each powered rail and ground;
6. worst-case DRL/reference output test;
7. electrode fault/open/short tests;
8. battery-only operation test;
9. leakage-current measurements with suitable calibrated instrumentation;
10. ESD/transient review;
11. temperature rise test;
12. firmware watchdog/fail-safe test;
13. data-integrity/CRC test;
14. documented risk assessment and approval by the responsible laboratory/person.

For clinical investigation or medical-device development, these prototype checks are not substitutes for formal standards and regulatory processes.

## 5. Software/control safety

NBFM-1 output shall not directly energize a safety-critical actuator.

A physical actuator path shall contain a separate deterministic safety layer implementing, as appropriate:

- watchdog timeout;
- command freshness;
- velocity/force/torque limits;
- workspace/end-stop limits;
- uncertainty rejection;
- explicit enable/dead-man state;
- emergency stop;
- fail-to-zero behavior.

The local LLM/action-router path is constrained to enumerated action identifiers and shall not generate arbitrary shell commands or arbitrary actuator parameters.

## 6. Data and neuro-privacy safety

Treat the following as sensitive:

- raw EEG, MEG and fNIRS;
- derived embeddings/features;
- decoded speech or semantic labels;
- personalized model adapters;
- device/session keys;
- subject calibration data.

The default system is local-first. Sensitive speech logits are zeroized at fixed shape below the intent threshold before authenticated export. Security controls do not make the system legally compliant by themselves; applicable privacy, research-ethics and data-protection rules still apply.

## 7. Human research

Use on human subjects may require institutional/ethics review, informed consent and jurisdiction-specific approval even when the hardware is non-invasive.

In the United States, investigational device requirements depend on the study and device risk. Significant-risk device studies generally require FDA IDE approval in addition to IRB approval; non-significant-risk studies remain subject to abbreviated IDE requirements and IRB oversight.

Do not infer an exemption from the repository's research label.

## 8. Liability limitation

Open-source license warranty disclaimers apply only to the extent permitted by applicable law.

Nothing in this document:

- waives non-waivable product-liability, personal-injury or statutory rights;
- guarantees immunity for maintainers, manufacturers, integrators or users;
- transfers a manufacturer's regulatory obligations to upstream contributors;
- authorizes clinical or commercial deployment without required conformity work.

Any party manufacturing, modifying, integrating, marketing or using a derivative is responsible for determining and meeting the laws and standards applicable to that derivative and its intended purpose.

## 9. Production medical-device path

A party intending medical use should establish a formal regulatory and quality program including, as applicable:

- ISO 14971 risk management;
- IEC 60601-1 electrical safety;
- IEC 60601-1-2 EMC;
- IEC 62304 software lifecycle;
- IEC 62366-1 usability engineering;
- cybersecurity lifecycle and threat management;
- biocompatibility for patient-contact materials;
- clinical evaluation/investigation;
- EU MDR or applicable FDA submission/classification work.

The exact set depends on the product, market and intended purpose.

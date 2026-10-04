<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Dual-Licensing and License-Boundary Audit

## 1. Repository license map

### CERN-OHL-S-2.0

Covered source:

```text
hardware/**
firmware/**
```

This project intentionally selects **CERN Open Hardware Licence Version 2 — Strongly Reciprocal**, SPDX identifier:

```text
CERN-OHL-S-2.0
```

### AGPL-3.0-only

Covered source:

```text
bin/**
software/**
scripts/**
systemd/**
config/**
.github/**
docs/**
tests/**
deploy_bci_stack.sh
README.md
PATENT_DISCLOSURE.md
SECURITY.md
CONTRIBUTING.md
NOTICE.md
CITATION.cff
```

SPDX identifier:

```text
AGPL-3.0-only
```

## 2. Why the two licenses can coexist

The repository is a multi-license aggregate with an explicit architectural boundary.

The CERN-OHL-S-covered hardware/firmware domain and AGPL-covered host/inference domain communicate through documented hardware/protocol interfaces such as:

- USB CDC / serial framing;
- the 128-byte packet header;
- CRC32C-protected frames;
- the 4096-byte DMA/shared-memory slot;
- local encrypted socket framing.

Mere interoperability across such an interface does not require declaring the entire repository to be under one single license.

Each covered work must independently satisfy its own license when conveyed, modified or distributed.

## 3. Strong reciprocity boundary

CERN-OHL-S-2.0 is the **strongly reciprocal** CERN OHL v2 variant.

Contributors shall not assume it is permissive. Modifications to covered hardware Source and other material falling within the licence's reciprocal scope must be handled under CERN-OHL-S-2.0 as required by that licence.

## 4. AGPL network obligations

AGPL-3.0-only applies to the covered software. A modified AGPL-covered program that users interact with remotely through a network can trigger the AGPL section 13 corresponding-source requirement.

Do not remove the network-source obligation by placing the software behind a proprietary web/API layer.

## 5. Cross-copying rule

Do not copy implementation source from an AGPL-covered file into a CERN-OHL-S-covered file, or vice versa, merely because both live in this repository.

Before intentionally combining code/source into a single derivative work:

1. identify the source licence of every copied element;
2. determine whether the resulting work can satisfy all applicable terms;
3. preserve notices and complete corresponding/source requirements;
4. obtain legal review for non-trivial mixed derivatives.

Protocol definitions, numeric constants, factual pin mappings and independently reimplemented interface descriptions should still retain appropriate attribution/notices where copyrightable expression is copied.

## 6. Firmware classification

The project intentionally treats device/bridge firmware under `firmware/**` as part of the open hardware Source and licenses it under CERN-OHL-S-2.0.

Host-side Python, deployment services and model/inference code remain AGPL-3.0-only.

If firmware is later linked against third-party libraries, verify the third-party library terms separately.

## 7. Third-party dependencies

No repository notice relicenses:

- TensorRT/CUDA;
- PyTorch;
- ONNX Runtime;
- Arduino cores/SDKs;
- Pico SDK;
- Ollama;
- vendor datasheets/reference designs;
- externally sourced KiCad symbols/footprints;
- pretrained model weights.

Third-party components retain their upstream licences.

## 8. REUSE metadata

REUSE metadata is authoritative for per-path machine-readable attribution.

The root `.reuse/dep5` contains:

- a repository-wide AGPL default stanza; and
- a more specific `hardware/* firmware/*` CERN-OHL-S stanza.

The canonical full licence texts are stored under `LICENSES/`.

The CI runs:

```bash
reuse lint
```

and treats any missing licence/copyright association as a release failure.

## 9. No patent licence expansion

Copyright/open-hardware licensing and prior-art publication are distinct.

The licences grant only the rights actually stated in their terms. The defensive publication is evidence of disclosed technical teaching; it is not a blanket patent licence from unknown third parties and not a freedom-to-operate opinion.

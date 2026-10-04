<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Contributing

Contributions must preserve deterministic packet formats, privacy-state semantics and repository license boundaries.

All commits should be signed off using:

```bash
git commit -s
```

## License boundaries

- `hardware/**` and `firmware/**`: `CERN-OHL-S-2.0`.
- `software/**`, `scripts/**`, `.github/**`, `docs/**` and root documentation: `AGPL-3.0-only` unless explicitly stated otherwise.
- Third-party files must not be copied into the repository unless redistribution terms are known and documented.

Changes affecting cryptography, zeroization, packet validation, action routing, actuator limits, session-key handling or neural-data retention require explicit security review.

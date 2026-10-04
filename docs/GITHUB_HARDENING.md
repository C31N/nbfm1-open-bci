<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# GitHub Repository Hardening

Use `main` and protect it. Require pull requests, approving review, resolution of review conversations and successful required checks. Do not permit force pushes or branch deletion.

Enable dependency graph, Dependabot alerts, Dependabot security updates, secret scanning, push protection, CodeQL and private vulnerability reporting where available.

Maintainer release tags should be annotated and cryptographically signed. Do not move or recreate a published defensive-publication tag.

Before a release:

```bash
./scripts/vendor_licenses.sh
./scripts/generate_release_manifest.sh
git diff --check
git status --short
```

The tree must contain no raw neural data, keys, trained personal weights or runtime caches.

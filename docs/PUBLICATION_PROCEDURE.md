<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Defensive Publication Release Procedure

A local file or private repository is not public prior art merely because it has a timestamp. The publication objective is to establish public availability, exact content and an independently verifiable date.

## 1. Freeze the disclosure

Synchronize NOTICE and CITATION to an existing, explicit source snapshot first.
The managed notice stores the manifest hash from that snapshot; this avoids
self-referential current-file hash cycles. It does not invent a DOI or a signed
publication date. After this operation, stage new files before regenerating the
current manifest so every new tracked file is covered.

```bash
git status --short
python3 scripts/update_notice_citation.py --revision HEAD
./scripts/vendor_licenses.sh
git add -A
./scripts/generate_release_manifest.sh
git add PUBLICATION_SHA256SUMS
python3 scripts/update_notice_citation.py --check
./scripts/verify_release_manifest.sh
git diff --cached --check
```

Review `PATENT_DISCLOSURE.md` for enablement and confirm that no confidential third-party information, secrets or unpublished patentable material that you intend to keep patentable is included.

## 2. Create a signed commit and signed tag

```bash
git commit -S -s -m "Publish NBFM-1 Open BCI defensive disclosure v1.0.0"
git tag -s v1.0.0-prior-art -m "NBFM-1 Open BCI defensive publication v1.0.0"
```

## 3. Make the repository public and push the exact tag

```bash
git push origin HEAD
git push origin v1.0.0-prior-art
```

Create a public GitHub release from the tag and archive it externally, for example with Zenodo.

## Legal effect

This procedure improves evidence of public availability but does not guarantee the outcome of patent examination, opposition or litigation.

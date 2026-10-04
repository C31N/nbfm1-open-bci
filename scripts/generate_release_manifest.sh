#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="PUBLICATION_SHA256SUMS"
TMP="${OUT}.tmp"
rm -f "$TMP"
find . -type f ! -path './.git/*' ! -path './.venv/*' ! -path './venv/*' ! -path './raw-data/*' ! -path './recordings/*' ! -path './engine-cache/*' ! -path './trt-cache/*' ! -name "$OUT" ! -name "$TMP" -print0 |
  sort -z | xargs -0 sha256sum > "$TMP"
mv "$TMP" "$OUT"
printf 'Wrote %s\n' "$ROOT/$OUT"

#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="PUBLICATION_SHA256SUMS"
TMP="${OUT}.tmp"
rm -f "$TMP"

git ls-files -z \
  | while IFS= read -r -d '' file; do
      case "$file" in
        "$OUT") continue ;;
      esac
      sha256sum -- "$file"
    done \
  | LC_ALL=C sort -k2 > "$TMP"

mv "$TMP" "$OUT"
printf 'Wrote %s with %s tracked-file hashes\\n' \
  "$ROOT/$OUT" "$(wc -l < "$OUT")"

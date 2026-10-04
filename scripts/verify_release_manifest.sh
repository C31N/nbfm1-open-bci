#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="PUBLICATION_SHA256SUMS"
[[ -f "$OUT" ]] || {
  printf 'Missing %s\\n' "$OUT" >&2
  exit 1
}

sha256sum --check --strict "$OUT"

expected="$(mktemp)"
actual="$(mktemp)"
trap 'rm -f "$expected" "$actual"' EXIT

git ls-files \
  | grep -vxF "$OUT" \
  | LC_ALL=C sort > "$expected"

awk '{sub(/^\\*/, "", $2); print $2}' "$OUT" \
  | sed 's#^\\./##' \
  | LC_ALL=C sort > "$actual"

if ! diff -u "$expected" "$actual"; then
  printf 'Release manifest file set does not match tracked repository file set.\\n' >&2
  exit 1
fi

printf 'Release manifest verified: hashes and tracked-file coverage are complete.\\n'

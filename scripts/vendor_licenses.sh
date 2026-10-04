#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/LICENSES"
fetch() {
  local url="$1" output="$2" tmp="${2}.tmp"
  curl --fail --location --proto '=https' --tlsv1.2 --silent --show-error "$url" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$output"
}
fetch "https://raw.githubusercontent.com/spdx/license-list-data/main/text/AGPL-3.0-only.txt" "$ROOT/LICENSES/AGPL-3.0-only.txt"
fetch "https://raw.githubusercontent.com/spdx/license-list-data/main/text/CERN-OHL-S-2.0.txt" "$ROOT/LICENSES/CERN-OHL-S-2.0.txt"
printf 'Vendored canonical SPDX license texts into %s\n' "$ROOT/LICENSES"

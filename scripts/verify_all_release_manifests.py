#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Verify every tracked SHA256SUMS file relative to its own directory."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import subprocess


def verify_manifest(path: Path, root: Path) -> int:
    seen: set[Path] = set()
    for line in path.read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](.+)', line)
        if not match:
            raise ValueError(f'Malformed manifest line: {path}')
        target = (path.parent/match[2]).resolve()
        if not target.is_relative_to(root.resolve()) or target in seen:
            raise ValueError(f'Unsafe or duplicate manifest path: {target}')
        seen.add(target)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != match[1]:
            raise ValueError(f'Manifest mismatch: {path}: {match[2]}')
    if not seen:
        raise ValueError(f'Empty manifest: {path}')
    return len(seen)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(['git','ls-files','-z'], cwd=root).decode().split('\0')
    manifests = [root/n for n in names if n and n.endswith('SHA256SUMS')]
    count = sum(verify_manifest(path, root) for path in manifests)
    print(f'Verified {len(manifests)} manifests / {count} bound files')


if __name__ == '__main__':
    main()

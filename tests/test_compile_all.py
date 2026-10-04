# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from pathlib import Path
import py_compile


def test_all_bin_python_compiles() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "bin").glob("*.py")):
        py_compile.compile(str(path), doraise=True)

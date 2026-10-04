#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys

FORBIDDEN = re.compile(r"\b(TODO|FIXME|TBD|PLACEHOLDER|NotImplementedError)\b", re.IGNORECASE)
TEXT_SUFFIXES = {
    ".py", ".sh", ".ino", ".md", ".yml", ".yaml", ".json", ".toml", ".cff",
    ".csv", ".kicad_sch", ".kicad_pcb", ".kicad_pro", ".conf", ".service", ".target", ".rules"
}
SKIP = {"LICENSES/AGPL-3.0-only.txt", "LICENSES/CERN-OHL-S-2.0.txt", "PUBLICATION_SHA256SUMS"}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(p.decode("utf-8")) for p in output.split(b"\0") if p]


def check_python_annotations(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        for arg in args:
            if arg.arg in {"self", "cls"}:
                continue
            if arg.annotation is None:
                issues.append(f"{path}:{node.lineno}: missing type annotation for {arg.arg}")
        if node.args.vararg is not None and node.args.vararg.annotation is None:
            issues.append(f"{path}:{node.lineno}: missing annotation for *{node.args.vararg.arg}")
        if node.args.kwarg is not None and node.args.kwarg.annotation is None:
            issues.append(f"{path}:{node.lineno}: missing annotation for **{node.args.kwarg.arg}")
        if node.returns is None:
            issues.append(f"{path}:{node.lineno}: missing return type annotation")
    return issues


def main() -> int:
    issues: list[str] = []
    for path in tracked_files():
        rel = path.as_posix()
        if rel in SKIP or not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            ".gitignore", "LICENSE_HARDWARE", "LICENSE_SOFTWARE"
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in FORBIDDEN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            issues.append(f"{rel}:{line}: forbidden debt marker {match.group(0)!r}")
        if path.suffix == ".py":
            try:
                issues.extend(check_python_annotations(path, text))
            except SyntaxError as exc:
                issues.append(f"{rel}:{exc.lineno}: syntax error: {exc.msg}")

    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    print("zero-debt scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

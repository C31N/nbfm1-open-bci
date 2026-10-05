#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
NOTICE = ROOT / "NOTICE.md"
CITATION = ROOT / "CITATION.cff"
HARDWARE_STATUS = ROOT / "hardware" / "eeg128-tdm" / "RELEASE_STATUS.json"

BEGIN = "<!-- BEGIN MANAGED RELEASE METADATA -->"
END = "<!-- END MANAGED RELEASE METADATA -->"


def replace_yaml_scalar(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    replacement = f'{key}: "{value}"'
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    return text.rstrip() + "\n" + replacement + "\n"


def hardware_release_label() -> str:
    status: dict[str, object] = json.loads(HARDWARE_STATUS.read_text(encoding="utf-8"))
    if bool(status.get("fabrication_release")):
        return f"{status.get('revision', 'unknown')} FABRICATION RELEASED"
    return f"{status.get('revision', 'unknown')} NOT RELEASED FOR FABRICATION"


def set_citation(version: str, release_date: str, repository: str, doi: str) -> None:
    text = CITATION.read_text(encoding="utf-8")
    text = replace_yaml_scalar(text, "version", version)
    text = replace_yaml_scalar(text, "date-released", release_date)
    text = replace_yaml_scalar(text, "repository-code", repository)

    doi_block_pattern = re.compile(
        r"(?ms)^# BEGIN MANAGED DOI\n.*?^# END MANAGED DOI\n?"
    )
    if doi:
        doi_block = (
            "# BEGIN MANAGED DOI\n"
            "identifiers:\n"
            "  - type: doi\n"
            f'    value: "{doi}"\n'
            "# END MANAGED DOI\n"
        )
    else:
        doi_block = (
            "# BEGIN MANAGED DOI\n"
            "# No archival DOI has been assigned to this release.\n"
            "# END MANAGED DOI\n"
        )

    if doi_block_pattern.search(text):
        text = doi_block_pattern.sub(doi_block, text, count=1)
    else:
        text = text.rstrip() + "\n" + doi_block

    CITATION.write_text(text, encoding="utf-8")


def set_notice(
    version: str,
    release_date: str,
    repository: str,
    doi: str,
    hardware_status: str,
) -> None:
    text = NOTICE.read_text(encoding="utf-8")
    archive_line = f"- Archival DOI: {doi}" if doi else "- Archival DOI: not assigned"
    block = (
        f"{BEGIN}\n"
        "## Release metadata\n\n"
        f"- Version: {version}\n"
        f"- Release/publication date: {release_date}\n"
        f"- Source repository: {repository}\n"
        f"- Hardware status: {hardware_status}\n"
        f"{archive_line}\n"
        "- Exact released-file identity: PUBLICATION_SHA256SUMS\n"
        f"{END}"
    )
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    NOTICE.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument(
        "--repository",
        default="https://github.com/C31N/nbfm1-open-bci",
    )
    parser.add_argument("--doi", default="")
    args = parser.parse_args()

    status = hardware_release_label()
    set_citation(args.version, args.date, args.repository, args.doi.strip())
    set_notice(args.version, args.date, args.repository, args.doi.strip(), status)
    print(
        f"updated {CITATION.relative_to(ROOT)} and {NOTICE.relative_to(ROOT)}; "
        f"hardware={status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

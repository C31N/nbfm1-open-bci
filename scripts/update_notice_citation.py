#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Synchronize citation and notice to an explicit Git snapshot, without hash cycles."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(['git',*args],cwd=ROOT).decode().strip()


def scalar(text: str, key: str, value: str) -> str:
    line = key+': '+json.dumps(value)
    pattern = rf'(?m)^{re.escape(key)}:.*$'
    return re.sub(pattern,line,text,count=1) if re.search(pattern,text) else text.rstrip()+'\n'+line+'\n'


def synchronize(revision: str, check: bool) -> None:
    sha = git('rev-parse','--verify',revision+'^{commit}')
    stamp = git('show','-s','--format=%cI',sha)[:10]
    snapshot_manifest = subprocess.check_output(['git','show',sha+':PUBLICATION_SHA256SUMS'],cwd=ROOT)
    digest = hashlib.sha256(snapshot_manifest).hexdigest()
    citation = ROOT/'CITATION.cff'
    previous = citation.read_text()
    match = re.search(r'(?m)^version:\s*"?([^"\n]+)', previous)
    if not match:
        raise ValueError('CITATION version absent')
    version = match[1].split('+')[0]+'+g'+sha[:12]
    updated = previous
    for key,value in [('version',version),('date-released',stamp),('commit',sha)]:
        updated = scalar(updated,key,value)
    notice = ROOT/'NOTICE.md'
    old_notice = notice.read_text()
    status = json.loads((ROOT/'hardware/eeg128-tdm/RELEASE_STATUS.json').read_text())
    block = ('<!-- BEGIN MANAGED RELEASE METADATA -->\n## Release metadata\n\n'
             f'- Version: {version}\n- Source snapshot date: {stamp}\n'
             f'- Source commit: {sha}\n'
             '- Source repository: https://github.com/C31N/nbfm1-open-bci\n'
             f'- Snapshot PUBLICATION_SHA256SUMS SHA-256: {digest}\n'
             f'- Fabrication release: {str(status.get("fabrication_release") is True).lower()}\n'
             '- Archival DOI: not assigned\n'
             '- Current file identity: PUBLICATION_SHA256SUMS\n'
             '<!-- END MANAGED RELEASE METADATA -->')
    pattern = r'<!-- BEGIN MANAGED RELEASE METADATA -->.*?<!-- END MANAGED RELEASE METADATA -->'
    if len(re.findall(pattern,old_notice,re.S)) != 1:
        raise ValueError('Expected exactly one managed NOTICE block')
    new_notice = re.sub(pattern,lambda _:block,old_notice,flags=re.S)
    if check:
        if updated != previous or new_notice != old_notice:
            raise ValueError('NOTICE/CITATION snapshot metadata differs')
    else:
        citation.write_text(updated)
        notice.write_text(new_notice)
    print(f'Metadata {"verified" if check else "updated"}: {sha}; snapshot manifest {digest}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision')
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    revision = args.revision
    if revision is None and args.check:
        match = re.search(r'(?m)^commit:\s*"?([0-9a-f]{40})', (ROOT/'CITATION.cff').read_text())
        if not match:
            raise ValueError('No recorded citation commit')
        revision = match[1]
    synchronize(revision or 'HEAD',args.check)


if __name__ == '__main__':
    main()

# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
from datetime import date
import hashlib
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_rejects_corruption_and_path_escape(tmp_path: Path) -> None:
    module = load('all_manifests',ROOT/'scripts/verify_all_release_manifests.py')
    data = tmp_path/'source';data.write_bytes(b'checked bytes')
    manifest = tmp_path/'SHA256SUMS'
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    manifest.write_text(digest+'  source\n')
    assert module.verify_manifest(manifest,tmp_path) == 1
    data.write_bytes(b'tampered bytes')
    with pytest.raises(ValueError):module.verify_manifest(manifest,tmp_path)
    manifest.write_text(digest+'  ../outside\n')
    with pytest.raises(ValueError):module.verify_manifest(manifest,tmp_path)


def test_quote_needs_complete_current_identity_and_valid_price_tier() -> None:
    module = load('bom_quote',ROOT/'hardware/eeg128-tdm/audit_bom_quote.py')
    bom = [{'LCSC Part #':'C2040','Qty':'1','Manufacturer Part #':'RP2040'}]
    quote = {'currency':'EUR','date':'2026-10-15','parts':{'C2040':{'mpn':'RP2040',
             'unit_price_eur':'1.25','multiple':1,'minimum':1,'price_tier_minimum':1,'stock':2}}}
    assert module.evaluate(bom,quote,date(2026,10,15))['component_target_under_50_eur']
    quote['parts']['C2040']['price_tier_minimum'] = 1000
    with pytest.raises(ValueError):module.evaluate(bom,quote,date(2026,10,15))
    quote['parts'] = {}
    with pytest.raises(KeyError):module.evaluate(bom,quote,date(2026,10,15))

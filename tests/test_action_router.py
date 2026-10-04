# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from action_router import ActionRouter  # noqa: E402


def test_exact_allowlist_mapping(tmp_path: Path) -> None:
    config = {
        "schema_version": 1,
        "ollama": {"enabled": False},
        "actions": {
            "noop": {"handler": "noop", "aliases": []},
            "left": {"handler": "noop", "aliases": ["move left"]},
        },
    }
    path = tmp_path / "router.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    router = ActionRouter(str(path))
    assert router.resolve("MOVE   LEFT", allow_llm=False) == "left"
    assert router.resolve("unknown", allow_llm=False) == "noop"

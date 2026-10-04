# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Optional
from urllib import request
from urllib.parse import urlparse


class ActionRouter:
    def __init__(self, config_path: str) -> None:
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if self.config.get("schema_version") != 1:
            raise ValueError("unsupported action-router schema")
        self.actions = self.config["actions"]
        if "noop" not in self.actions:
            raise ValueError("action config must define noop")
        self.alias_map: dict[str, str] = {}
        for action_id, spec in self.actions.items():
            for alias in spec.get("aliases", []):
                key = self.normalize(alias)
                if key in self.alias_map and self.alias_map[key] != action_id:
                    raise ValueError(f"duplicate normalized alias {key!r}")
                self.alias_map[key] = action_id

    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9äöüßʃŋʁçɐə]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def exact(self, text: str) -> Optional[str]:
        return self.alias_map.get(self.normalize(text))

    def spec(self, action_id: str) -> dict:
        if action_id not in self.actions:
            raise KeyError(action_id)
        return self.actions[action_id]

    def resolve(self, text: str, allow_llm: bool = True) -> str:
        exact = self.exact(text)
        if exact is not None:
            return exact
        if not allow_llm or not self.config.get("ollama", {}).get("enabled", False):
            return "noop"
        return self._ollama_select(text)

    def _ollama_select(self, text: str) -> str:
        cfg = self.config["ollama"]
        parsed = urlparse(cfg["url"])
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama endpoint must be loopback HTTP")
        action_ids = list(self.actions.keys())
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": action_ids},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["action", "confidence"],
            "additionalProperties": False,
        }
        aliases = {k: v.get("aliases", []) for k, v in self.actions.items() if k != "noop"}
        system = (
            "Select exactly one predeclared BCI action. The input is a noisy CTC/phoneme sequence. "
            "Do not invent actions, parameters, commands, paths, code, URLs, shell syntax or prose. "
            "If the sequence is ambiguous, select noop with low confidence.\n"
            + json.dumps(aliases, ensure_ascii=False)
        )
        payload = {
            "model": cfg["model"],
            "stream": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": self.normalize(text)},
            ],
            "options": {"temperature": 0.0, "top_p": 0.1},
        }
        req = request.Request(
            cfg["url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=float(cfg.get("timeout_seconds", 5.0))) as response:
                body = json.loads(response.read().decode("utf-8"))
            result = json.loads(body["message"]["content"])
            action_id = result.get("action", "noop")
            confidence = float(result.get("confidence", 0.0))
            if action_id not in self.actions or confidence < 0.80:
                return "noop"
            return action_id
        except Exception:
            return "noop"

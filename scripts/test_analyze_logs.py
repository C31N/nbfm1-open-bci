#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline security and functionality tests for Gemini failure diagnostics."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import analyze_logs


class GeminiLogTests(unittest.TestCase):
    def test_redaction_is_applied_before_upload(self) -> None:
        raw = (
            "##[error] KiCad DRC failed\n"
            "GEMINI_API_KEY=AIzaABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n"
            "Authorization: Bearer github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ\n"
            "password=top-secret-value\n"
            "error: unconnected_items 139\n"
        )
        filtered = analyze_logs.error_excerpt(raw)
        for item in ("AIzaABC", "github_pat_", "top-secret-value"):
            self.assertNotIn(item, filtered)
        self.assertIn("unconnected_items 139", filtered)
        self.assertIn("[REDACTED]", filtered)

    def test_context_and_hard_input_bounds(self) -> None:
        raw = "\n".join(
            "ordinary non-error text" for _ in range(300)
        ) + "\nTraceback: native route failed\nnearby context\n"
        excerpt = analyze_logs.error_excerpt(raw)
        self.assertIn("nearby context", excerpt)
        self.assertLessEqual(len(excerpt), analyze_logs.MAX_SNIPPET)
        self.assertLessEqual(len(excerpt.splitlines()), analyze_logs.MAX_LINES)

    def test_reject_invalid_repo_before_invoking_gh(self) -> None:
        with mock.patch.object(analyze_logs.subprocess, "run") as runner:
            with self.assertRaises(ValueError):
                analyze_logs.fetch_failed_logs("evil/../path", 1)
            with self.assertRaises(ValueError):
                analyze_logs.fetch_failed_logs("C31N/nbfm1-open-bci", -1)
            runner.assert_not_called()

    def test_only_failed_job_logs_are_read(self) -> None:
        result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Error: native DRC\n", stderr=""
        )
        with mock.patch.object(analyze_logs.subprocess, "run",
                               return_value=result) as runner:
            data = analyze_logs.fetch_failed_logs("C31N/nbfm1-open-bci", 15)
        self.assertIn("native DRC", data)
        arguments = runner.call_args.args[0]
        self.assertEqual(arguments[:3], ["gh", "run", "view"])
        self.assertEqual(arguments[-1], "--log-failed")
        self.assertNotIn("checkout", arguments)

    def test_dry_run_never_calls_gemini(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "errors.log"
            file.write_text("##[error] KiCad DRC failed\n", encoding="utf-8")
            argv = [
                "analyze_logs.py", "--repo", "C31N/nbfm1-open-bci",
                "--log-file", str(file), "--dry-run"
            ]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(analyze_logs, "ask_gemini") as model:
                    with contextlib.redirect_stdout(output):
                        code = analyze_logs.main()
            self.assertEqual(code, 0)
            model.assert_not_called()
            self.assertIn("no Gemini request", output.getvalue())

    def test_native_routing_artifact_uuid_allowlist(self) -> None:
        fixed_uuid = "10000000-0000-4000-8000-000000000001"
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "Block2-Elastic-5"
            report.mkdir()
            (report / "elastic-5.json").write_text(json.dumps({
                "order": ["CH030_N_MUX", "CH029_N_MUX", "CH028_N_MUX"],
                "child_diagnostic": {
                    "status": "rubber_guided_CBS3_bounded_no_solution",
                    "rubber_band_diagnostic": {
                        "topology_crossing_free": True,
                        "rubber_pairwise_minimum_mm": .22,
                        "fixed_copper_cutset_analysis": {
                            "status": "read_only_native_cutset_candidates",
                            "pairwise": [{
                                "nets": ["CH028_N_MUX", "CH029_N_MUX"],
                                "minimum_centreline_mm": .22,
                                "fixed_copper_uuid_candidates": [{
                                    "uuid": fixed_uuid,
                                    "kind": "via",
                                    "net": "VCM",
                                    "centreline_to_copper_mm": .14,
                                    "clearance_deficit_mm": .135,
                                    "note": "GEMINI_API_KEY=AIzaABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
                                }, {
                                    "uuid": "invalid-uuid", "net": "password=secret"
                                }],
                                "other_net_fixed_copper_uuid_candidates": []
                            }],
                        },
                        "topology_separation_attempts": [],
                        "inflated_micro_hops": {"CH030_N_MUX": 4},
                    }
                }
            }), encoding="utf-8")
            compact = analyze_logs.routing_summary_from_dir(Path(folder))
        self.assertIn(fixed_uuid, compact)
        self.assertIn("CH028_N_MUX", compact)
        self.assertIn("0.22", compact)
        self.assertNotIn("AIza", compact)
        self.assertNotIn("password", compact)
        self.assertNotIn("invalid-uuid", compact)
        prompt = analyze_logs.routing_prompt(
            "C31N/nbfm1-open-bci", 123, compact)
        for gate in ("accepted=false", "0.15-mm", "In1.Cu", "keine neuen Vias"):
            self.assertIn(gate, prompt)

    def test_invalid_routing_artifact_is_not_sent_to_gemini(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "elastic-5.json").write_text(
                json.dumps({"child_diagnostic": {}}), encoding="utf-8")
            summary = analyze_logs.routing_summary_from_dir(Path(folder))
            self.assertIn("not_produced", summary)
            self.assertNotIn("exec", summary)
        with mock.patch.object(analyze_logs.subprocess, "run") as runner:
            with self.assertRaises(ValueError):
                analyze_logs.fetch_routing_artifacts("bad/../../", 10)
            runner.assert_not_called()

    def test_gemini_transient_503_retried_and_401_not_retried(self) -> None:
        calls = []
        ServerError = type("ServerError", (Exception,), {})
        ClientError = type("ClientError", (Exception,), {})

        class Models:
            def generate_content(self, *, model: str, contents: str):
                calls.append((model, contents))
                if len(calls) <= 2:
                    raise ServerError("503 UNAVAILABLE high demand")
                return types.SimpleNamespace(text="UUID analysis")

        class Client:
            models = Models()

            def __init__(self, api_key: str):
                self.api_key = api_key

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        google = types.ModuleType("google")
        genai = types.ModuleType("google.genai")
        genai.Client = Client
        google.genai = genai
        with mock.patch.dict(sys.modules, {"google": google, "google.genai": genai}):
            with mock.patch.object(analyze_logs.time, "sleep") as sleep:
                result = analyze_logs.ask_gemini("safe routing metrics", "test", "mock")
        self.assertEqual(result, "UUID analysis")
        self.assertEqual(len(calls), 3)
        self.assertEqual([a.args[0] for a in sleep.call_args_list], [2, 5])

        class BadModels:
            def generate_content(self, *, model: str, contents: str):
                raise ClientError("401 INVALID_API_KEY")
        Client.models = BadModels()
        with mock.patch.dict(sys.modules, {"google": google, "google.genai": genai}):
            with mock.patch.object(analyze_logs.time, "sleep") as sleep:
                with self.assertRaises(ClientError):
                    analyze_logs.ask_gemini("safe", "test", "mock")
                sleep.assert_not_called()

    def test_hardware_gates_explicitly_blocked(self) -> None:
        prompt = analyze_logs.prompt(
            "C31N/nbfm1-open-bci", 12, "error: DRC 139"
        )
        for value in ("accepted=false", "fabrication_release=false",
                      "routing_completed=false", "3V3A", "In1.Cu"):
            self.assertIn(value, prompt)


if __name__ == "__main__":
    unittest.main()

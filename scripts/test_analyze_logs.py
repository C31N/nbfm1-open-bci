#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline security and functionality tests for Gemini failure diagnostics."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
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

    def test_hardware_gates_explicitly_blocked(self) -> None:
        prompt = analyze_logs.prompt(
            "C31N/nbfm1-open-bci", 12, "error: DRC 139"
        )
        for value in ("accepted=false", "fabrication_release=false",
                      "routing_completed=false", "3V3A", "In1.Cu"):
            self.assertIn(value, prompt)


if __name__ == "__main__":
    unittest.main()

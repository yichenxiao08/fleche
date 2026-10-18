"""No later question may run after a missing assistant reply."""

import contextlib
import importlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fencecoach.coach.hosted_fallback import HostedError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
runner = importlib.import_module("run_fewshot_v5_clean_review")


class HistoryRunnerTests(unittest.TestCase):
    def test_saved_turn_four_without_prior_replies_is_invalid(self):
        with self.assertRaises(ValueError):
            runner.stored_reply_prefix({"turns": [{"turn": 4, "answer": "Orphaned reply"}]})
        self.assertEqual(runner.stored_reply_prefix({"turns": []}), [])

    def test_first_outage_stops_before_turn_two_on_either_provider(self):
        work = (ROOT / "work/history_hygiene_tests").resolve()
        work.mkdir(parents=True, exist_ok=True)
        for provider in ("groq", "gemini"):
            for status in (503, 429):
                with self.subTest(provider=provider, status=status):
                    root = work / str(uuid4())
                    root.mkdir()
                    try:
                        (root / "docs").mkdir()
                        inputs = root / "evals/layer2/inputs.json"
                        inputs.parent.mkdir(parents=True)
                        inputs.write_text(
                            json.dumps(
                                [
                                    {
                                        "id": "case",
                                        "saved_request": {
                                            "session_id": "clip",
                                            "question": "placeholder",
                                        },
                                    }
                                ]
                            ),
                            encoding="utf-8",
                        )
                        legacy = root / "evals/conversational_kb/model_review"
                        out = legacy / "test-pass"
                        with (
                            patch.object(runner, "ROOT", root),
                            patch.object(runner, "LEGACY", legacy),
                            patch.object(runner, "OUT", out),
                            patch.object(runner, "FROZEN", ()),
                            patch.object(runner, "PROMPT_REVISION", "fewshot-v5"),
                            patch.object(
                                runner, "CHAINS", [("case", ["first", "second", "third", "fourth"])]
                            ),
                            patch.object(runner, "ORDERS", {"groq": [1], "gemini": [1]}),
                            patch.object(runner, "settings", SimpleNamespace()),
                            patch.object(runner, "writer_reference", return_value="Test reference"),
                            patch.object(runner, "daily_attempts", return_value=0),
                            patch.object(runner, "HostedFallback"),
                            patch.object(runner, "chat_model"),
                            patch.object(
                                runner,
                                "run_packet_core",
                                side_effect=HostedError(status, "test outage"),
                            ) as invoke,
                            patch.object(sys, "argv", ["runner", provider]),
                            contextlib.redirect_stdout(io.StringIO()),
                        ):
                            runner.main()
                        self.assertEqual(invoke.call_count, 1)
                        request = invoke.call_args.args[0]
                        self.assertEqual(request.question, "first")
                        self.assertEqual(request.conversation_history, [])
                        directory = out / runner.SLUGS[provider]
                        row = json.loads((directory / "C01.json").read_text(encoding="utf-8"))
                        self.assertEqual(row["turns"], [])
                        self.assertEqual([e["turn"] for e in row["errors"]], [1])
                        self.assertEqual(len(list((directory / "requests").glob("*.json"))), 1)
                        self.assertFalse(list((directory / "requests").glob("C01-T2-*.json")))
                        saved = json.loads((directory / "status.json").read_text(encoding="utf-8"))
                        self.assertEqual(saved["status"], "blocked")
                        self.assertGreater(saved["resume_after"], 0)
                    finally:
                        # Only remove this test's new UUID directory under the verified workspace path.
                        root.resolve().relative_to(work)
                        shutil.rmtree(root)

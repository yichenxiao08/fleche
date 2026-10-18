"""Acceptance instrumentation records raw output and stops after one real error."""

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage

from fencecoach.coach.hosted_fallback import HostedError
from fencecoach.settings import settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
acceptance = importlib.import_module("run_live_acceptance_v7")


class LiveAcceptanceTransportTests(unittest.TestCase):
    def test_groq_413_allows_fallback_but_429_and_503_stop_execution_fallback(self):
        for status in (413, 429, 503):
            with self.subTest(status=status):
                client = Mock()
                client.invoke.side_effect = HostedError(status, "mocked provider error", 1)
                with patch("fencecoach.coach.core_packet.gemini_circuit") as circuit:
                    with self.assertRaises(HostedError):
                        acceptance.RecordingClient("groq", client).invoke(
                            [HumanMessage(content="assigned test question")]
                        )
                    if status == 413:
                        circuit.failure.assert_not_called()
                    else:
                        circuit.failure.assert_called_once_with("owner_stop_after_groq_error", 3600)

    def test_owner_v72_order_and_required_two_turn_gemini_suffix(self):
        ids = ["L01", "L06", "L05", "L07", "L04", "L10", "L02", "L03", "L09", "L08"]
        cases = [{"id": ident, "turns": [], "questions": ["one", "two"]} for ident in ids]
        with patch.object(acceptance, "cooldown", return_value=float("inf")):
            self.assertEqual([c["id"] for c in acceptance.ordered_cases(cases)], ids)
            self.assertEqual(acceptance.candidates_for(cases[5], []), ["groq"])
        with patch.object(acceptance, "cooldown", return_value=0):
            self.assertEqual(acceptance.ordered_cases(cases)[5]["id"], "L10")
            cases[1]["turns"] = [{"run": {"mode": "groq"}}]
            self.assertEqual(acceptance.ordered_cases(cases)[0]["id"], "L06")
            self.assertEqual(acceptance.candidates_for(cases[1], []), ["groq"])
            cases[1]["turns"].append({"run": {"mode": "gemini"}})
            self.assertEqual(acceptance.candidates_for(cases[1], []), ["gemini"])
            self.assertEqual(acceptance.candidates_for(cases[5], ["groq"]), ["gemini"])
            cases[5]["turns"] = [{"run": {"mode": "groq"}}] * 2
            self.assertEqual(acceptance.candidates_for(cases[5], []), ["gemini"])
            cases[5]["turns"].append({"run": {"mode": "gemini"}})
            self.assertEqual(acceptance.candidates_for(cases[5], []), ["gemini"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(acceptance, "WORK", root / "work"),
            patch.object(acceptance, "LEDGER", root / "ledger"),
            patch.object(acceptance, "CASES", root / "work/cases.json"),
        ]
        for replacement in self.patches:
            replacement.start()
        acceptance.save(
            acceptance.WORK / "control.json",
            {
                "case": "L01",
                "turn": 1,
                "question": "question",
                "force_failure": [],
            },
        )

    def tearDown(self):
        for replacement in reversed(self.patches):
            replacement.stop()
        self.temp.cleanup()

    def test_raw_reply_and_messages_are_not_rewritten(self):
        response = AIMessage(content="Keep this wording.\nAnd these 3 numbers: 1, 2.")
        client = Mock()
        client.invoke.return_value = response
        messages = [HumanMessage(content="actual question")]
        actual = acceptance.RecordingClient("groq", client).invoke(messages)
        self.assertIs(actual, response)
        client.invoke.assert_called_once_with(messages)
        record = acceptance.read(next(acceptance.LEDGER.glob("qwen/requests/*.json")))
        self.assertEqual(record["response"]["content"], response.content)
        self.assertEqual(record["request"][0]["content"], "actual question")

    def test_real_429_or_503_reaches_normal_router_without_retry(self):
        for status in (429, 503):
            with self.subTest(status=status):
                client = Mock()
                error = HostedError(status, "Real provider failure", retry_after=123)
                client.invoke.side_effect = error
                with self.assertRaises(HostedError) as raised:
                    acceptance.RecordingClient("groq", client).invoke([HumanMessage(content="q")])
                self.assertIs(raised.exception, error)
                client.invoke.assert_called_once()
                record = acceptance.read(acceptance.WORK / "provider_stop.json")
                self.assertEqual(record["http_status"], status)
                self.assertEqual(record["retry_after_seconds"], 123)
                self.assertTrue(record["reached_provider"])

    def test_failed_provider_stays_stopped_for_same_execution_only(self):
        acceptance.save(
            acceptance.WORK / "control.json",
            {
                "case": "L01",
                "turn": 1,
                "force_failure": [],
                "execution_id": "this-check",
            },
        )
        client = Mock()
        client.invoke.side_effect = HostedError(429, "quota", retry_after=12)
        with self.assertRaises(HostedError):
            acceptance.RecordingClient("groq", client).invoke([HumanMessage(content="q")])
        self.assertTrue(acceptance.stopped_in_run("groq", "this-check"))
        self.assertFalse(acceptance.stopped_in_run("groq", "later-check"))
        self.assertFalse(acceptance.stopped_in_run("gemini", "this-check"))

    def test_forced_failure_is_distinct_and_does_not_send_a_request(self):
        acceptance.save(
            acceptance.WORK / "control.json",
            {
                "case": "L10",
                "turn": 3,
                "question": "is it good?",
                "force_failure": ["groq"],
            },
        )
        client = Mock()
        with self.assertRaises(HostedError):
            acceptance.RecordingClient("groq", client).invoke([HumanMessage(content="q")])
        client.invoke.assert_not_called()
        record = acceptance.read(next(acceptance.LEDGER.glob("qwen/requests/*.json")))
        self.assertTrue(record["forced"])
        self.assertFalse(record["reached_provider"])
        self.assertNotIn("resume_after", record)

    def test_child_settings_do_not_flip_parent_or_real_storage(self):
        before = settings.coach_core
        env = acceptance.test_environment()
        self.assertEqual(env["COACH_CORE"], "new")
        self.assertEqual(settings.coach_core, before)
        self.assertEqual(env["FENCECOACH_DATABASE_URL"], "")
        self.assertEqual(Path(env["FENCECOACH_DB_PATH"]), acceptance.WORK / "acceptance.sqlite3")

    def test_interrupted_harness_recovers_stored_reply_before_another_request(self):
        cases = [
            {
                "id": "L01",
                "session_id": "copy",
                "questions": ["first", "second"],
                "turns": [],
                "errors": [],
            }
        ]
        stored = {
            "run_id": "already-saved",
            "created_at": "2026-10-17T00:00:00Z",
            "question": "first",
            "report": {"summary": "Verbatim stored reply."},
        }
        with patch.object(acceptance, "fetch", return_value=[stored]) as fetch:
            acceptance.reconcile(Mock(), cases)
            acceptance.reconcile(Mock(), cases)
        self.assertEqual(len(cases[0]["turns"]), 1)
        self.assertEqual(cases[0]["turns"][0]["run"], stored)
        self.assertIsNone(cases[0]["turns"][0]["wall_latency_ms"])
        self.assertTrue(all(call.args[1] == "GET" for call in fetch.call_args_list))

    def test_recovered_prefix_restarts_child_without_submitting_a_duplicate_or_wrong_fault(self):
        cases = [
            {
                "id": "L10",
                "title": "fallback",
                "session_id": "copy",
                "questions": ["first", "second"],
                "turns": [],
                "errors": [],
            }
        ]
        acceptance.save(acceptance.CASES, cases)
        acceptance.save(acceptance.WORK / "control.json", {"case": "L10", "turn": 1})
        stored = {
            "run_id": "saved",
            "created_at": "2026-10-17T00:00:00Z",
            "question": "first",
            "report": {"summary": "Already answered."},
        }
        with (
            patch.object(acceptance, "fetch", return_value=[stored]) as fetch,
            patch.object(acceptance, "render"),
        ):
            acceptance.conversations(Mock(), "same-execution")
        self.assertTrue(all(call.args[1] == "GET" for call in fetch.call_args_list))
        self.assertEqual(
            acceptance.read(acceptance.WORK / "status.json")["status"], "reconciled_reply_prefix"
        )


if __name__ == "__main__":
    unittest.main()

"""Exercise the shipped default through direct HTTP and the durable chat queue."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from fencecoach.api import app
from fencecoach.coach.hosted_fallback import HostedError
from fencecoach.coach.router import CircuitBreaker
from fencecoach.coaching_jobs import CoachingJobs, CoachingWorker
from fencecoach.repository import Repository
from fencecoach.schemas import SessionCreate
from fencecoach.settings import Settings, settings


class DefaultCoachTests(unittest.TestCase):
    def test_default_direct_and_queued_chat_withholds_rejected_readings_and_falls_back(self):
        # Resolve the real default without a developer's .env/process override.
        with patch.dict(os.environ):
            os.environ.pop("COACH_CORE", None)
            default = Settings(_env_file=None).coach_core
        self.assertEqual(default, "new")
        primary = Mock()
        primary.invoke.side_effect = [
            AIMessage(content="Verbatim mocked direct reply."),
            HostedError(429, "Mocked quota failure", retry_after=120),
        ]
        fallback = Mock()
        fallback.invoke.return_value = AIMessage(content="Verbatim mocked queued reply.")
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(Path(directory) / "chat.sqlite3")
            session = repo.create_session(
                SessionCreate(
                    title="Rejected tracking fixture",
                    metrics=[
                        dict(
                            metric_id="rejected", name="knee", value=111, unit="deg", confidence=0.9
                        )
                    ],
                )
            )
            jobs = CoachingJobs(repo)
            client = TestClient(app)
            self.addCleanup(client.close)
            with (
                patch.object(settings, "coach_core", default),
                patch("fencecoach.api.repository", repo),
                patch("fencecoach.api.coaching_jobs", jobs),
                patch(
                    "fencecoach.api.require_supported_session",
                    side_effect=HTTPException(422, "Rejected tracking fixture"),
                ),
                patch("fencecoach.coach.core_packet.groq_circuit", CircuitBreaker()),
                patch("fencecoach.coach.core_packet.gemini_circuit", CircuitBreaker()),
                patch("fencecoach.coach.core_packet.HostedFallback", return_value=primary),
                patch("fencecoach.coach.core_packet.chat_model", return_value=fallback),
                patch(
                    "fencecoach.coach.conversation._run_conversation",
                    side_effect=AssertionError("Legacy writer must not run by default"),
                ),
            ):
                direct = client.post(
                    f"/api/sessions/{session.session_id}/reports",
                    json={"question": "my arm on rep 2"},
                )
                self.assertEqual(direct.status_code, 201, direct.text)
                first = direct.json()
                self.assertEqual(first["mode"], "groq")
                self.assertEqual(first["report"]["summary"], "Verbatim mocked direct reply.")
                queued = client.post(
                    f"/api/sessions/{session.session_id}/coaching-jobs",
                    json={"question": "why does that matter?"},
                )
                self.assertEqual(queued.status_code, 202, queued.text)
                owner = "default-core-test"
                job = jobs.claim(owner)
                self.assertIsNotNone(job)
                CoachingWorker(jobs).execute(job, owner)
                completed = client.get("/api/coaching-jobs/" + queued.json()["job_id"]).json()
                self.assertEqual(completed["status"], "completed", completed)
                second = client.get("/api/reports/" + completed["run_id"]).json()
                self.assertEqual(second["mode"], "gemini")
                self.assertIn("groq:rate_limit", second["fallback_reason"])
                self.assertEqual(second["report"]["summary"], "Verbatim mocked queued reply.")
                for run in (first, second):
                    contract = run["answer_contract"]
                    self.assertEqual(contract["core"], "new")
                    self.assertFalse(contract["output_checks"])
                    self.assertEqual(contract["packet"]["measurements"], [])
                    self.assertEqual(contract["packet"]["scope"]["topics"], ["arm"])
                    self.assertEqual(contract["packet"]["scope"]["rep_numbers"], [2])
                    self.assertEqual(
                        contract["packet"]["availability"]["status"], "tracking_unsupported"
                    )
                self.assertEqual(primary.invoke.call_count, 2)
                fallback.invoke.assert_called_once()
                for call in primary.invoke.call_args_list:
                    packet = json.loads(call.args[0][1].content.split("\n", 1)[1])
                    self.assertEqual(packet["measurements"], [])
                self.assertEqual(len(repo.list_runs(session.session_id)), 2)

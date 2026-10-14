"""Exercise the production queue boundary, persistence and legacy isolation."""

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk

from fencecoach.coach.verified_dialogue import run_verified_conversation
from fencecoach.coaching_jobs import CoachingJobs, CoachingWorker
from fencecoach.repository import Repository
from fencecoach.schemas import CoachRequest, SessionCreate
from fencecoach.settings import settings


class Selector:
    def stream(self, messages):
        for unit in json.loads(messages[-1].content)["units"]:
            yield AIMessageChunk(content=unit["id"] + "\n")


class CoachingQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_setting = patch.object(settings, "fencecoach_database_url", "")
        self.database_setting.start()
        self.addCleanup(self.database_setting.stop)
        self.repo = Repository(Path(self.temp.name) / "queue.sqlite3")
        fixture = Path(__file__).resolve().parents[1] / "evals/coach_audit/current.json"
        self.request = CoachRequest.model_validate_json(fixture.read_text())
        session = self.repo.create_session(
            SessionCreate(title="Saved measurement regression", metrics=self.request.metrics)
        )
        self.request.session_id = session.session_id
        self.request.question = "How was my torso?"
        self.request.dialogue_state = None
        self.request.conversation_history = []
        self.jobs = CoachingJobs(self.repo)

    def seed_legacy(self):
        record = {
            "job_id": "legacy-job",
            "session_id": self.request.session_id,
            "status": "queued",
            "created_at": "2026-01-01T00:00:00Z",
            "request": self.request.model_dump(mode="json"),
            "mode": "gemini",
        }
        with closing(self.repo._connect()) as db, db:
            db.execute(
                "INSERT INTO coaching_jobs VALUES (?,?,?,?)",
                (record["job_id"], record["status"], record["created_at"], json.dumps(record)),
            )
        return record

    def test_legacy_and_current_workers_cannot_claim_each_others_jobs(self):
        self.seed_legacy()
        current = self.jobs.create(self.request, "gemini")
        claimed = self.jobs.claim("current-worker")
        self.assertEqual(claimed["job_id"], current["job_id"])
        self.assertIsNone(self.jobs.claim("second-current-worker"))
        with closing(self.repo._connect()) as db:
            legacy = db.execute("SELECT id FROM coaching_jobs WHERE status='queued'").fetchall()
        self.assertEqual(legacy, [("legacy-job",)])

    def test_legacy_records_remain_pollable_and_cancellable(self):
        self.seed_legacy()
        self.assertEqual(self.jobs.get("legacy-job")["status"], "queued")
        self.assertEqual(self.jobs.cancel("legacy-job")["status"], "cancelled")

    def test_queued_turn_publishes_and_persists_a_grounded_answer(self):
        queued = self.jobs.create(self.request, "gemini")
        claimed = self.jobs.claim("worker")

        def run(request, mode, **callbacks):
            return run_verified_conversation(request, mode, model=Selector(), **callbacks)

        with patch("fencecoach.coaching_jobs.run_coach", side_effect=run):
            CoachingWorker(self.jobs).execute(claimed, "worker")
        result = self.jobs.get(queued["job_id"])
        self.assertEqual(result["status"], "completed", result.get("error"))
        saved = self.repo.list_runs(self.request.session_id)[0]
        self.assertIn("torso", saved.dialogue_state.topics)
        self.assertEqual(result["partial_reply"], saved.report.summary)
        self.assertGreater(saved.citation_count, 0)

    def test_internal_failure_is_diagnosable_and_does_not_blame_the_provider(self):
        queued = self.jobs.create(self.request, "gemini")
        claimed = self.jobs.claim("worker")
        with (
            patch("fencecoach.coaching_jobs.run_coach", side_effect=ValueError("private detail")),
            patch("fencecoach.coaching_jobs.logging.exception"),
        ):
            CoachingWorker(self.jobs).execute(claimed, "worker")
        result = self.jobs.get(queued["job_id"])
        self.assertIn("internal error", result["error"])
        self.assertNotIn("private detail", result["error"])
        self.assertNotIn("failure_detail", result)
        with closing(self.repo._connect()) as db:
            payload = json.loads(
                db.execute(
                    "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (queued["job_id"],)
                ).fetchone()[0]
            )
        self.assertEqual(payload["failure_detail"]["exception_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()

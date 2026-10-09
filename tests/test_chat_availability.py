import unittest
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage

from fencecoach.api import coaching_request
from fencecoach.coach.graph import run_coach
from fencecoach.schemas import CoachRequest, ReportRequest, SessionRecord


class ChatAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.session = SessionRecord(
            session_id="rejected-video",
            title="Rejected footage",
            created_at="2026-10-09T12:00:00Z",
            video_job_id="video",
            metrics=[dict(metric_id="bad", name="knee", value=111, unit="deg", confidence=0.9)],
        )
        self.context = dict(
            training_history=[{"notes": "old"}],
            previous_reviews=[{"summary": "old"}],
            session_history=[{"metrics": self.session.metrics}],
            conversation_history=[],
        )

    def test_rejected_clip_allows_general_chat_without_metrics_or_history_tools(self):
        with (
            patch("fencecoach.api.repository.coaching_context", return_value=self.context),
            patch(
                "fencecoach.api.require_supported_session",
                side_effect=HTTPException(422, "Body out of frame"),
            ),
        ):
            request = coaching_request(
                self.session, ReportRequest(question="What is recovery in fencing?")
            )
        self.assertEqual(request.metrics, [])
        self.assertEqual(request.previous_reviews, [])
        self.assertEqual(request.session_history, [])
        self.assertEqual(request.training_history, [])
        self.assertIn("Body out of frame", request.session_notes)

    def test_personal_analysis_remains_rejected(self):
        with (
            patch("fencecoach.api.repository.coaching_context", return_value=self.context),
            patch(
                "fencecoach.api.require_supported_session",
                side_effect=HTTPException(422, "Body out of frame"),
            ),
        ):
            for question in (
                "What's wrong with my lunge?",
                "Compare with baseline",
                "Review this clip",
            ):
                with self.subTest(question=question), self.assertRaises(HTTPException):
                    coaching_request(self.session, ReportRequest(question=question))

    def test_supported_video_keeps_measurements(self):
        with (
            patch("fencecoach.api.repository.coaching_context", return_value=self.context),
            patch("fencecoach.api.require_supported_session"),
        ):
            request = coaching_request(self.session, ReportRequest(question="Review my lunge"))
        self.assertEqual(request.metrics, self.session.metrics)

    def test_general_conversation_with_no_measurements_needs_no_citation(self):
        class Model:
            model = "general-chat-fixture"

            def bind(self, **kwargs):
                return self

            def invoke(self, messages):
                return AIMessage(
                    content="Recovery is the return to en garde after a lunge. It prepares you for the next action."
                )

        run = run_coach(
            CoachRequest(session_id="general", question="What is recovery in fencing?"),
            "local",
            model=Model(),
        )
        self.assertIn("return to en garde", run.report.summary)
        self.assertEqual(run.citation_count, 0)
        self.assertEqual(run.report.observations, [])


if __name__ == "__main__":
    unittest.main()

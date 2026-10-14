import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from fencecoach.api import app, coaching_request
from fencecoach.coach.graph import run_coach
from fencecoach.schemas import CoachRequest, ReportRequest, SessionRecord
from fencecoach.settings import settings


class MissingEvidenceModel:
    model = "missing-evidence-fixture"

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(
            content="This clip has no usable lunge measurements. For a basic lunge, reach the sword arm toward the target, then recover to en garde."
        )


# These fixtures exercise the retained free-prose writer and evidence-tool protocol.
@patch.object(settings, "fencecoach_verified_dialogue", False)
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
            reviewed_feedback={},
        )

    def test_rejected_clip_allows_general_chat_without_current_video_metrics(self):
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
        self.assertEqual(request.session_history, self.context["session_history"])
        self.assertEqual(request.training_history, self.context["training_history"])
        self.assertIn("Body out of frame", request.session_notes)

    def test_personal_questions_use_live_coach_with_session_evidence_gap(self):
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
                with self.subTest(question=question):
                    request = coaching_request(self.session, ReportRequest(question=question))
                    self.assertEqual(request.metrics, [])
                    model = MissingEvidenceModel()
                    run = run_coach(request, "local", model=model)
                    self.assertNotEqual(run.model_id, "evidence-check")
                    self.assertTrue(any(e.step == "assess_current_session" for e in run.trace))
                    self.assertTrue(any("Body out of frame" in m.content for m in model.messages))
                    self.assertNotIn("111", run.report.summary)

    def test_both_chat_endpoints_accept_quality_rejected_question(self):
        with (
            patch("fencecoach.api.get_session", return_value=self.session),
            patch("fencecoach.api.repository.coaching_context", return_value=self.context),
            patch("fencecoach.api.repository.save_run", side_effect=lambda run: run),
            patch("fencecoach.coach.conversation.chat_model", return_value=MissingEvidenceModel()),
            patch(
                "fencecoach.api.require_supported_session",
                side_effect=HTTPException(422, "Body out of frame"),
            ),
            patch(
                "fencecoach.api.coaching_jobs.create",
                return_value={"job_id": "fixture", "status": "queued"},
            ) as create,
        ):
            client = TestClient(app)
            body = {"question": "What's wrong with my lunge?", "mode": "local"}
            direct = client.post("/api/sessions/rejected-video/reports", json=body)
            self.assertEqual(direct.status_code, 201, direct.text)
            self.assertNotEqual(direct.json()["model_id"], "evidence-check")
            queued = client.post("/api/sessions/rejected-video/coaching-jobs", json=body)
            self.assertEqual(queued.status_code, 202, queued.text)
            self.assertEqual(create.call_args.args[0].metrics, [])
            invalid = client.post(
                "/api/sessions/rejected-video/coaching-jobs", json={"question": ""}
            )
            self.assertEqual(invalid.status_code, 422)

    def test_sample_report_handles_missing_video_evidence(self):
        request = CoachRequest(
            session_id="missing",
            question="Review my lunge",
            evidence_unavailable_reason="Video unavailable",
        )
        run = run_coach(request, "demo")
        self.assertEqual(run.model_id, "evidence-check")
        self.assertIn("Video unavailable", run.report.summary)

    def test_supported_video_keeps_measurements(self):
        with (
            patch("fencecoach.api.repository.coaching_context", return_value=self.context),
            patch("fencecoach.api.require_supported_session"),
        ):
            request = coaching_request(self.session, ReportRequest(question="Review my lunge"))
        self.assertEqual(request.metrics, self.session.metrics)

    def test_general_conversation_with_no_measurements_uses_technique_references(self):
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
        self.assertGreater(run.citation_count, 0)
        self.assertTrue(
            all(
                ref.source_type == "knowledge"
                for obs in run.report.observations
                for ref in obs.evidence
            )
        )


if __name__ == "__main__":
    unittest.main()

"""Evidence regressions from the owner's saved-session v7.6 conversations."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage

from fencecoach.coach.core_new import _session_key, _snapshot
from fencecoach.coach.core_packet import run_packet_core
from fencecoach.coach.turn_packet import build_packet, resolve_scope
from fencecoach.schemas import CoachRequest


def evaluation():
    reps = []
    for number, phase in ((1, "lunge_hold"), (2, "lunge_finish"), (3, "lunge_finish")):
        reps.append(
            {
                "rep_number": number,
                "status": "unsupported" if number == 3 else "available",
                "geometry_available": number != 3,
                "lunge_ms": number * 1000,
                "measurements": {
                    "front_knee_angle": {"value": 140 + number, "unit": "deg", "phase": phase},
                    "projected_torso_tilt": {"value": 10 + number, "unit": "deg", "phase": phase},
                },
                "reference_comparison": {
                    "status": "available",
                    "comparison_scope": "projected side views; camera equivalence unverified",
                    "references": [{"rep_number": 4, "stated_corrections": "arm points too high"}],
                    "rows": [
                        {
                            "metric": "front_knee_angle",
                            "phase": "finish",
                            "unit": "deg",
                            "current": 140 + number,
                            "reference_range": [88.6, 98.5],
                            "direction": "higher",
                        },
                        {
                            "metric": "front_knee_angle",
                            "phase": "active_recovery",
                            "unit": "deg",
                            "current": 120,
                            "reference_range": [110, 130],
                        },
                    ],
                },
            }
        )
    return {"whole_clip_quality": "unsupported", "reps": reps}


class CapturingModel:
    def invoke(self, messages):
        self.packet = json.loads(messages[1].content.split("\n", 1)[1])
        return AIMessage(content="A mocked response, preserved exactly.")


class ReferenceCoachRegressionTests(unittest.TestCase):
    def request(self, question="how is my front knee bend?"):
        return CoachRequest(session_id="clip", question=question, technique_evaluation=evaluation())

    def packet(self, request):
        snapshot = json.loads(_snapshot(_session_key(request)))
        state = resolve_scope(request, snapshot)
        return build_packet(request, state, snapshot, conversation_only=True)

    def test_local_geometry_survives_whole_clip_rejection_but_rejected_reps_do_not(self):
        packet = self.packet(self.request())
        self.assertEqual(packet["availability"]["status"], "measurements_available")
        self.assertEqual({row["rep"] for row in packet["measurements"]}, {1, 2})
        self.assertEqual(
            {row["phase"] for row in packet["measurements"]}, {"lunge_hold", "lunge_finish"}
        )
        self.assertIn("Whole-clip", packet["availability"]["tracking_warning"])

    def test_explicit_rejection_withholds_even_previously_saved_reference_geometry(self):
        request = self.request()
        request.evidence_unavailable_reason = "Saved tracking was rejected."
        packet = self.packet(request)
        self.assertEqual(packet["measurements"], [])
        self.assertEqual(packet["reference_comparisons"], [])
        self.assertEqual(packet["availability"]["status"], "tracking_unsupported")
        self.assertEqual(packet["availability"]["cause"], "unknown")
        self.assertIn("Tracking marked unsupported", packet["availability"]["tracking_warning"])

    def test_actual_writer_receives_knee_and_references_on_typo_reach_followup(self):
        model = CapturingModel()
        run = run_packet_core(
            self.request("wouldnt a deepr kinee bend give you more reach"), "groq", model=model
        )
        packet = model.packet
        self.assertEqual(set(packet["scope"]["topics"]), {"distance", "front_leg"})
        self.assertEqual(packet["availability"]["requested_missing_topics"], ["distance"])
        self.assertEqual({row["feature"] for row in packet["measurements"]}, {"front_knee_angle"})
        self.assertEqual(len(packet["reference_comparisons"]), 2)
        for row in packet["reference_comparisons"]:
            self.assertEqual(row["reference_range"], [88.6, 98.5])
            self.assertEqual(row["phase"], "finish")
        self.assertEqual(len(packet["reference_contexts"]), 1)
        self.assertEqual(
            packet["reference_contexts"][0]["references"][0]["stated_corrections"],
            "arm points too high",
        )
        self.assertEqual(run.report.summary, "A mocked response, preserved exactly.")
        self.assertFalse(run.answer_contract["output_checks"])

    def test_explicit_rep_phase_general_scope_and_missing_reference_are_respected(self):
        packet = self.packet(self.request("my front knee in rep 2 at the finish"))
        self.assertEqual([row["rep"] for row in packet["reference_comparisons"]], [2])
        self.assertEqual([row["phase"] for row in packet["measurements"]], ["lunge_finish"])
        self.assertEqual(
            self.packet(self.request("generally how should my knee bend"))["reference_comparisons"],
            [],
        )
        request = self.request()
        for rep in request.technique_evaluation["reps"]:
            rep["reference_comparison"]["status"] = "no_reference_set"
        self.assertEqual(self.packet(request)["reference_comparisons"], [])

    def test_no_local_geometry_does_not_revive_whole_clip_rejection(self):
        request = self.request()
        for rep in request.technique_evaluation["reps"]:
            rep["geometry_available"] = False
        self.assertEqual(self.packet(request)["availability"]["status"], "tracking_unsupported")

    def test_reach_followup_retains_established_knee_subject(self):
        request = self.request("my front knee in rep 2")
        snapshot = json.loads(_snapshot(_session_key(request)))
        request.dialogue_state = resolve_scope(request, snapshot)
        request.question = "would bending deeper give me more reach?"
        packet = self.packet(request)
        self.assertEqual(set(packet["scope"]["topics"]), {"distance", "front_leg"})
        self.assertEqual([row["rep"] for row in packet["reference_comparisons"]], [2])

    def test_http_request_preserves_local_knee_geometry_without_requiring_torso(self):
        from fencecoach.api import coaching_request

        evaluation_data = evaluation()
        for rep in evaluation_data["reps"]:
            rep["measurements"].pop("projected_torso_tilt")
        session = SimpleNamespace(
            session_id="clip",
            video_job_id="video",
            skill_level="beginner",
            capture_profile={},
            notes="",
        )
        context = {"training_history": [], "session_history": [], "conversation_history": []}
        with (
            patch("fencecoach.api.repository.coaching_context", return_value=context),
            patch(
                "fencecoach.coaching_evidence_cache.coaching_evaluation",
                return_value=evaluation_data,
            ),
            patch(
                "fencecoach.api.require_supported_session",
                side_effect=HTTPException(422, "Rejected"),
            ),
        ):
            request = coaching_request(session, SimpleNamespace(question="my front knee"))
        self.assertEqual(request.metrics, [])
        self.assertEqual(request.evidence_unavailable_reason, "")
        self.assertEqual({row["rep"] for row in self.packet(request)["measurements"]}, {1, 2})

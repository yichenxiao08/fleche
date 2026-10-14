"""Body-role evidence and missing-data answers share the same conversation contract."""

import json
import unittest
from unittest.mock import patch

from fencecoach.coach.answer_review import (
    AnswerDraft,
    AnswerReview,
    cited_subject_issues,
    review_issues,
)
from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.intent import arm_roles, arm_sides
from fencecoach.coach.latency import coaching_session_context, compact_measurements
from fencecoach.coach.technique_evidence import (
    question_scoped_session_context,
    requested_feature_names,
)
from fencecoach.coach.turns import contextual_question
from fencecoach.phase_metrics import rep_phases
from fencecoach.schemas import MetricObservation
from fencecoach.settings import settings
from tests.test_coach_evidence_followups import ReviewedWriter, Writer, session
from tests.test_technique_phases import PROFILE, pose_frame


def arm_session(question, weapon="right"):
    request = session(question, previous="How was my non-sword arm?")
    request.capture_profile = {"weapon_arm": weapon}
    request.metrics = [
        MetricObservation(
            metric_id=f"video-rep-01-{side}-elbow",
            name=f"{side}_elbow_angle_at_peak",
            value=value,
            unit="deg",
            confidence=0.95,
            start_ms=2000,
            end_ms=2000,
        )
        for side, value in (("left", 110), ("right", 175))
    ]
    for rep in request.technique_evaluation["reps"]:
        rep["measurements"]["weapon_elbow_angle"] = {
            "value": 175,
            "unit": "deg",
            "phase": "lunge_finish",
            "time_ms": 2000,
        }
    return request


# These fixtures exercise the legacy structured writer/reviewer citation contract.
@patch.object(settings, "fencecoach_verified_dialogue", False)
class ArmScopeTests(unittest.TestCase):
    def test_playback_bookmark_does_not_repeat_the_same_geometry(self):
        answer = "Rep 1's left elbow was bent at 110 degrees."
        draft = AnswerDraft(
            answer=answer,
            supporting_example="At 2.0 seconds in rep 1, your left elbow reached 110 degrees.",
        )
        self.assertEqual(draft.conversational_text, answer)

    def test_role_resolution_preserves_negation_and_handedness(self):
        self.assertEqual(arm_roles("How was my non-sword arm?"), ("non_weapon",))
        self.assertEqual(arm_sides("How was my non-sword arm?", {"weapon_arm": "left"}), {"right"})
        self.assertEqual(arm_sides("How was my non-sword arm?", {}), set())
        self.assertEqual(
            arm_roles("Compare my sword arm and non-sword arm"), ("non_weapon", "weapon")
        )
        self.assertEqual(arm_sides("How was my left arm?", {}), {"left"})

    def test_raw_non_weapon_records_survive_when_rep_evaluation_exists(self):
        request = arm_session("How was my non-sword arm here?")
        packet = json.loads(question_scoped_session_context(request))
        self.assertEqual(
            [row["name"] for row in packet["session_measurements"]], ["left_elbow_angle_at_peak"]
        )
        self.assertTrue(all(not rep["measures"] for rep in packet["per_rep_measurements"]))
        row = packet["session_measurements"][0]
        self.assertEqual((row["rep"], row["phase"]), (1, "lunge_finish"))
        self.assertEqual(packet["answer_affordances"]["supported_corrections"], [])

    def test_weapon_query_gets_weapon_evidence_without_requiring_a_correction(self):
        request = arm_session("How was my sword arm here?")
        packet = json.loads(coaching_session_context(question_scoped_session_context(request)))
        self.assertEqual(
            [row["name"] for row in packet["session_measurements"]], ["right_elbow_angle_at_peak"]
        )
        self.assertEqual(packet["answer_affordances"]["supported_corrections"], [])
        answer = "Your sword arm was nearly straight at the finish. Rep 1's sword elbow measured 175 degrees."
        model = ReviewedWriter(answer, "rep:1:measurement:weapon_elbow_angle")
        self.assertEqual(run_conversation(request, "gemini", model=model).report.summary, answer)

    def test_non_weapon_observation_is_accepted_without_weapon_reference(self):
        request = arm_session("How was my non-sword arm here?")
        answer = "Your non-sword arm was bent at the peak. Rep 1's left elbow measured 110 degrees."
        model = ReviewedWriter(answer, "video-rep-01-left-elbow")
        self.assertEqual(run_conversation(request, "gemini", model=model).report.summary, answer)

    def test_missing_role_does_not_require_other_arm_evidence(self):
        request = arm_session("How was my non-sword arm here?", weapon="unknown")
        packet = json.loads(question_scoped_session_context(request))
        self.assertEqual(packet["session_measurements"], [])
        decision = AnswerReview(addresses_question=True, grounded=True, uses_session_evidence=False)
        self.assertEqual(review_issues(decision, packet, requested_feature_names(request)), [])
        answer = "Your non-sword arm isn't identified in this clip's setup, so I can't assess it yet. Set your sword-arm side so I can use the opposite arm's measurements."
        self.assertEqual(
            run_conversation(request, "local", model=Writer(answer)).report.summary, answer
        )

    def test_wrong_arm_citation_is_rejected_even_if_requested_data_is_absent(self):
        request = arm_session("How was my non-sword arm here?")
        from fencecoach.coach.technique_evidence import current_session_context

        packet = json.loads(current_session_context(request))
        issues = cited_subject_issues(
            packet, ["rep:1:measurement:weapon_elbow_angle"], requested_feature_names(request)
        )
        self.assertIn("The cited records omit the requested measured feature.", issues)

    def test_followups_keep_the_active_arm_role(self):
        for question in ("Can you give me a number?", "So was it good or bad?", "What about that?"):
            self.assertIn("non-sword arm", contextual_question(arm_session(question)))
        request = arm_session("How was my sword arm here?")
        self.assertNotIn("non-sword", contextual_question(request))

    def test_compact_metrics_do_not_fallback_to_the_other_arm(self):
        request = arm_session("How was my non-sword arm here?")
        rows = [metric.model_dump() for metric in request.metrics]
        self.assertEqual(
            [
                row["name"]
                for row in compact_measurements(rows, request.question, request.capture_profile)
            ],
            ["left_elbow_angle_at_peak"],
        )
        self.assertEqual(
            compact_measurements(rows[1:], request.question, request.capture_profile), []
        )

    def test_new_phase_analysis_measures_each_visible_arm_separately(self):
        frames = [pose_frame(t) for t in range(600, 1900, 100)]
        for frame in frames:
            frame["features"]["left_elbow_angle"] = 110
        phases = rep_phases(
            frames, {"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}, PROFILE, 1000, 600
        )["phases"]
        measures = phases["lunge_finish"]["measurements"]
        self.assertEqual(measures["non_weapon_elbow_angle"]["value"], 110)
        self.assertEqual(measures["weapon_elbow_angle"]["value"], 170)
        for frame in frames:
            frame["landmarks"][15][3] = 0.1
        phases = rep_phases(
            frames, {"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}, PROFILE, 1000, 600
        )["phases"]
        self.assertNotIn("non_weapon_elbow_angle", phases["lunge_finish"]["measurements"])

"""Regressions for observed wrong-topic answers and interrupted cloud turns."""

import json
import unittest
from unittest.mock import patch

from langchain_core.exceptions import ModelAPIError, ModelAuthenticationError
from langchain_core.messages import AIMessage, ToolMessage

from fencecoach.coach.answer_review import AnswerDraft, AnswerReview, PersonalChange
from fencecoach.coach.conversation import CoachAnswerError, run_conversation
from fencecoach.coach.intent import mentioned_rep_numbers
from fencecoach.coach.latency import compact_session_context, expand_session_context
from fencecoach.coach.technique_evidence import current_session_context
from fencecoach.coach.turns import contextual_question
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings


class Model:
    model = "response-fixture"

    def __init__(self, reply="", error=None, repair=None):
        self.reply, self.error = reply, error
        self.repair = repair
        self.calls = 0
        self.messages = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.messages = messages
        self.calls += 1
        if self.error:
            raise self.error
        return AIMessage(content=self.repair if self.calls > 1 and self.repair else self.reply)


class StructuredModel(Model):
    def __init__(self, draft, review, repair=None):
        super().__init__(draft.model_dump_json())
        self.draft = draft
        self.review = review
        self.repair = repair
        self.repair_called = False

    def bind(self, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        parent = self

        class Reviewer:
            def invoke(self, messages):
                parent.review_messages = messages
                if schema is AnswerDraft:
                    parent.repair_called = True
                    parsed = parent.repair or parent.draft
                elif parent.repair is not None and not parent.repair_called:
                    parsed = parent.review.model_copy(update={"grounded": False})
                else:
                    parsed = parent.review
                return {
                    "parsed": parsed,
                    "raw": AIMessage(content=parsed.model_dump_json()),
                }

        return Reviewer()


def request(question):
    reps = []
    for number, angle in enumerate([95, 120, 135], 1):
        time = number * 2000
        priorities = (
            []
            if number == 1
            else [
                {
                    "rep": number,
                    "what_to_try": "Try settling into a lower finish, closer to the front-leg bend in your reference reps.",
                    "reason": "Your front knee angle is higher at the finish than the observed reference range.",
                    "watch_at_seconds": time / 1000,
                }
            ]
        )
        reps.append(
            {
                "rep_number": number,
                "selected_frame_ms": time,
                "lunge_ms": time,
                "findings": [],
                "unavailable": [],
                "status": "available",
                "measurements": {
                    "front_knee_angle": {
                        "value": angle,
                        "unit": "deg",
                        "time_ms": time,
                        "phase": "lunge_finish",
                    },
                    "weapon_arm_direction": {
                        "value": 5,
                        "unit": "deg",
                        "time_ms": time,
                        "phase": "lunge_finish",
                    },
                    "projected_torso_tilt": {
                        "value": number * 2,
                        "unit": "deg",
                        "time_ms": time,
                        "phase": "lunge_finish",
                    },
                },
                "reference_comparison": {
                    "status": "available",
                    "coaching_priorities": priorities,
                    "rows": [
                        {
                            "metric": "front_knee_angle",
                            "phase": "finish",
                            "current": angle,
                            "reference_median": 95,
                            "reference_range": [90, 100],
                            "direction": "overlaps" if number == 1 else "higher",
                            "watch_at_seconds": time / 1000,
                        },
                        {
                            "metric": "projected_torso_tilt",
                            "phase": "finish",
                            "current": number * 2,
                            "reference_median": 4,
                            "reference_range": [0, 10],
                            "direction": "overlaps",
                        },
                    ],
                },
            }
        )
    return CoachRequest(
        session_id="reliability-fixture",
        question=question,
        technique_evaluation={"coaching_mode": "reference_comparison", "reps": reps},
    )


# These fixtures check legacy writer repair, independent review and tool-grounded prose.
@patch.object(settings, "fencecoach_verified_dialogue", False)
class CoachResponseReliabilityTests(unittest.TestCase):
    def test_missing_timing_can_be_explained_without_unrelated_angle_citations(self):
        draft = AnswerDraft(answer="Your arm should lead the front foot.")
        answer = "The session measures your arm position at the finish, but not its extension onset relative to your foot. I need that timing measurement to assess whether your extension should start earlier."
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=False,
            uses_session_evidence=False,
        )
        out = run_conversation(
            request("Should I extend my arm earlier?"),
            "gemini",
            model=StructuredModel(draft, review, repair=AnswerDraft(answer=answer)),
        )
        self.assertEqual(out.report.summary, answer)

    def test_verified_answer_cannot_cite_a_different_rep(self):
        record = "rep:1:measurement:weapon_arm_direction"
        draft = AnswerDraft(answer="Your arm was near horizontal.", session_evidence_ids=[record])
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
        )
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("What about my arm in rep 3?"),
                "gemini",
                model=StructuredModel(draft, review),
            )

    def test_compaction_preserves_every_rep_value_and_explanation(self):
        original = json.loads(current_session_context(request("what about my arm")))
        self.assertEqual(
            expand_session_context(compact_session_context(json.dumps(original))), original
        )

    def test_review_cannot_bless_a_writer_citing_the_wrong_feature(self):
        draft = AnswerDraft(
            answer="Your sword arm was near horizontal in rep 1.",
            session_evidence_ids=["rep:1:measurement:front_knee_angle"],
        )
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=True,
            session_evidence_ids=["rep:1:measurement:weapon_arm_direction"],
        )
        published = []
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("what about my arm"),
                "gemini",
                model=StructuredModel(draft, review),
                on_text=published.append,
            )
        self.assertEqual(published, [])

    def test_supported_observation_keeps_independent_quality_review(self):
        record = "rep:1:measurement:weapon_arm_direction"
        answer = "Your sword arm stayed near horizontal at the measured finish in rep 1."
        draft = AnswerDraft(answer=answer, session_evidence_ids=[record])
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
        )
        model = StructuredModel(draft, review)
        out = run_conversation(request("what about my arm"), "gemini", model=model)
        self.assertEqual(out.report.summary, answer)
        self.assertTrue(hasattr(model, "review_messages"))
        self.assertTrue(any(e.step == "semantic_review" for e in out.trace))

    def test_wrong_feature_citation_still_gets_independent_review(self):
        draft = AnswerDraft(
            answer="Your arm looked close to the reference at the finish.",
            session_evidence_ids=["rep:1:measurement:front_knee_angle"],
        )
        answer = "Your sword arm was near horizontal at the measured finish in rep 1."
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=True,
            uses_session_evidence=True,
            session_evidence_ids=["rep:1:measurement:weapon_arm_direction"],
        )
        model = StructuredModel(
            draft,
            review,
            repair=AnswerDraft(answer=answer, session_evidence_ids=review.session_evidence_ids),
        )
        out = run_conversation(request("what about my arm"), "gemini", model=model)
        self.assertEqual(out.report.summary, answer)
        self.assertTrue(hasattr(model, "review_messages"))
        self.assertTrue(any(e.step == "answer_repair" for e in out.trace))

    def test_generic_draft_can_be_repaired_using_uncited_session_evidence(self):
        record = "rep:2:measurement:weapon_arm_direction"
        draft = AnswerDraft(answer="In general, reach your sword arm toward the target.")
        answer = "Your sword arm stayed near horizontal at the measured finish in rep 2."
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
        )
        model = StructuredModel(
            draft, review, repair=AnswerDraft(answer=answer, session_evidence_ids=[record])
        )
        out = run_conversation(request("what about my arm"), "gemini", model=model)
        self.assertEqual(out.report.summary, answer)
        packet = expand_session_context(
            json.dumps(json.loads(model.review_messages[1].content)["active_session"])
        )
        self.assertEqual(len(packet["per_rep_measurements"]), 3)
        self.assertTrue(
            any(
                item["feature"] == "weapon_arm_direction"
                for item in packet["per_rep_measurements"][1]["measurements"]
            )
        )

    def test_general_only_answer_is_rejected_when_reviewer_finds_session_evidence(self):
        draft = AnswerDraft(answer="Reach your sword arm toward the target.")
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            session_evidence_relevant=True,
            uses_session_evidence=False,
        )
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("arm extension?"), "gemini", model=StructuredModel(draft, review)
            )

    def test_body_part_followup_does_not_inherit_previous_body_part(self):
        query = request("what about my arm")
        query.conversation_history = [
            ConversationMessage(role="user", content="How was my torso in rep 2?"),
            ConversationMessage(role="assistant", content="Your torso matched the reference."),
        ]
        resolved = contextual_question(query)
        self.assertIn("rep 2", resolved)
        self.assertIn("my arm", resolved)
        self.assertNotIn("torso", resolved)

    def test_changed_scope_does_not_resurrect_an_old_rep(self):
        query = request("what about my arm")
        query.conversation_history = [
            ConversationMessage(role="user", content="How was rep 2?"),
            ConversationMessage(role="assistant", content="It matched your reference."),
            ConversationMessage(role="user", content="How was my torso across the drill?"),
            ConversationMessage(role="assistant", content="Similar at the checked finishes."),
        ]
        self.assertEqual(contextual_question(query), query.question)

    def test_verified_answer_is_published_without_canned_substitution(self):
        record = "rep:1:reference:finish:projected_torso_tilt"
        draft = AnswerDraft(answer="Try leaning forward more.", session_evidence_ids=[record])
        answer = "Your torso position at the checked finish in rep 1 matched your upright reference example."
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
            corrections=["No torso correction is supported."],
        )
        published = []
        out = run_conversation(
            request("How was my torso during the drill?"),
            "gemini",
            model=StructuredModel(
                draft, review, repair=AnswerDraft(answer=answer, session_evidence_ids=[record])
            ),
            on_text=published.append,
        )
        self.assertEqual(out.report.summary, answer)
        self.assertEqual(published, [answer])
        self.assertNotIn("knee", out.report.summary)

    def test_semantic_reviewer_cannot_authorize_a_change_from_a_plain_measurement(self):
        record = "rep:1:measurement:projected_torso_tilt"
        draft = AnswerDraft(answer="Lean forward more.", session_evidence_ids=[record])
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
            personal_changes=[PersonalChange(feature="projected_torso_tilt", evidence_id=record)],
        )
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("How was my torso?"), "gemini", model=StructuredModel(draft, review)
            )

    def test_unregistered_feature_uses_the_same_evidence_pipeline(self):
        query = request("How was my shin position?")
        query.technique_evaluation["reps"][0]["measurements"]["shin_tilt"] = {
            "value": 5,
            "unit": "deg",
            "phase": "lunge_finish",
            "note": "Shin orientation relative to vertical.",
        }
        record = "rep:1:measurement:shin_tilt"
        answer = "Your shin was close to vertical at the measured finish in rep 1."
        draft = AnswerDraft(answer=answer, session_evidence_ids=[record])
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
        )
        out = run_conversation(query, "gemini", model=StructuredModel(draft, review))
        self.assertEqual(out.report.summary, answer)

    def test_invalid_evidence_ids_never_reach_the_athlete(self):
        draft = AnswerDraft(
            answer="Your posture was perfect.", session_evidence_ids=["rep:99:measurement:torso"]
        )
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=False,
        )
        published = []
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("How was my torso?"),
                "gemini",
                model=StructuredModel(draft, review),
                on_text=published.append,
            )
        self.assertEqual(published, [])

    def test_independent_review_can_repair_draft_citations_before_publication(self):
        draft = AnswerDraft(
            answer="Your torso was perfect.", session_evidence_ids=["rep:99:measurement:torso"]
        )
        record = "rep:1:reference:finish:projected_torso_tilt"
        answer = "Your torso tilt at the measured finish in rep 1 overlapped the range in your reference examples."
        review = AnswerReview(
            session_evidence_relevant=True,
            addresses_question=True,
            grounded=True,
            uses_session_evidence=True,
            session_evidence_ids=[record],
            corrections=["Replaced the nonexistent draft citation with actual torso evidence."],
        )
        published = []
        run = run_conversation(
            request("How was my torso?"),
            "gemini",
            model=StructuredModel(
                draft, review, repair=AnswerDraft(answer=answer, session_evidence_ids=[record])
            ),
            on_text=published.append,
        )
        self.assertEqual(run.report.summary, answer)
        self.assertEqual(published, [answer])

    def test_rejected_arm_answer_does_not_become_knee_correction(self):
        run = run_conversation(
            request("At what angle should I extend my sword arm and non-sword arm?"),
            "gemini",
            model=Model(
                "The ideal arm angle is 45 degrees.",
                repair="Reach your sword arm toward the target; in a conventional lunge, the non-sword arm extends behind you.",
            ),
        )
        self.assertIn("sword arm", run.report.summary)
        self.assertIn("non-sword arm", run.report.summary)
        self.assertIn("target", run.report.summary)
        self.assertNotIn("front knee", run.report.summary)
        self.assertNotIn("lower finish", run.report.summary)

    def test_answer_repair_preserves_evidence_retrieved_by_tools(self):
        from tests.test_conversation import ScriptedModel

        answer = (
            "Your sword arm finished slightly above horizontal across the measured repetitions."
        )
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_technique_evaluation",
                            "args": {"feature_names": ["weapon_arm_direction"]},
                            "id": "arm-evidence",
                        }
                    ],
                ),
                AIMessage(content="At 2.0 seconds, your knee angle was 95 degrees."),
                AIMessage(content=answer),
            ]
        )
        run = run_conversation(request("What about my arm direction?"), "local", model=model)
        self.assertEqual(run.report.summary, answer)
        retrieved = [item for item in model.inputs[-1] if isinstance(item, ToolMessage)]
        self.assertEqual(len(retrieved), 1)
        self.assertIn("weapon_arm_direction", retrieved[0].content)

    def test_torso_question_never_falls_back_to_a_knee_measurement(self):
        run = run_conversation(
            request("How was my torso during the drill?"),
            "gemini",
            model=Model(
                "At 2.0 seconds, your knee angle is 95 degrees.",
                repair="Your torso at the checked finish in rep 1 matched your upright reference examples.",
            ),
        )
        self.assertIn("torso", run.report.summary)
        self.assertIn("reference", run.report.summary)
        self.assertNotIn("knee", run.report.summary)
        self.assertTrue(any(e.step == "answer_repair" for e in run.trace))

    def test_torso_provider_failure_keeps_the_correct_body_part(self):
        with self.assertRaises(ModelAPIError):
            run_conversation(
                request("How was my torso during the drill?"),
                "gemini",
                model=Model(error=ModelAPIError("503 unavailable")),
            )

    def test_model_denial_of_saved_rep_data_is_replaced_with_current_evidence(self):
        run = run_conversation(
            request("What should I fix in rep 3?"),
            "gemini",
            model=Model(
                "Your rep breakdown is not available in this recording.",
                repair="Try settling into a lower finish, closer to the front-leg bend in your reference reps. In rep 3 around 6.0 seconds, your front leg finished straighter than those examples.",
            ),
        )
        self.assertIn("lower finish", run.report.summary)
        self.assertIn("6.0 seconds", run.report.summary)
        self.assertNotIn("not available", run.report.summary)

    def test_failover_model_receives_identical_session_and_question(self):
        primary = Model(error=ModelAPIError("503 unavailable"))
        secondary = Model(
            "Try settling into a lower finish, closer to the front-leg bend in your reference reps. In rep 3 around 6.0 seconds, your front leg finished straighter than those examples."
        )
        with (
            patch("fencecoach.coach.conversation.chat_model", side_effect=[primary, secondary]),
            patch(
                "fencecoach.coach.conversation.provider_status", return_value={"local_ready": False}
            ),
        ):
            run = run_conversation(request("What should I fix in rep 3?"), "gemini")
        self.assertIn("lower finish", run.report.summary)
        self.assertIn("provider failover", run.model_id)
        self.assertEqual(primary.messages[1].content, secondary.messages[1].content)
        self.assertTrue(any(e.step == "provider_failover" for e in run.trace))

    def test_failed_repair_does_not_fall_back_to_any_body_part(self):
        from fencecoach.coach.conversation import CoachAnswerError

        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("How was my torso?"),
                "gemini",
                model=Model("Your knee angle is 95 degrees."),
            )

    def test_authentication_errors_are_not_hidden(self):
        with self.assertRaises(ModelAuthenticationError):
            run_conversation(
                request("What should I fix in rep 3?"),
                "gemini",
                model=Model(error=ModelAuthenticationError("Invalid key")),
            )

    def test_compound_all_rep_and_ranking_request_covers_all_reps(self):
        run = run_conversation(
            request("Analyze all 3 reps and tell me the best and worst."),
            "gemini",
            model=Model(
                "Rep 1 was closest to the front-knee reference range. Rep 2 finished with a straighter front leg than the reference. Rep 3 was furthest from that range, with the straightest front leg."
            ),
        )
        self.assertEqual(mentioned_rep_numbers(run.report.summary), {1, 2, 3})
        self.assertIn("closest", run.report.summary)
        self.assertIn("furthest", run.report.summary)

    def test_unrecognized_phrasing_still_receives_actual_rep_measurements(self):
        model = Model("Choose one change for your next set and compare the finish.")
        run_conversation(request("Why do I look cramped when I land?"), "gemini", model=model)
        snapshot = next(
            m.content
            for m in model.messages
            if str(m.content).startswith("Active session evidence checked")
        )
        data = expand_session_context(snapshot.split("(reference data): ", 1)[1])
        self.assertEqual(len(data["per_rep_measurements"]), 3)
        measured = next(
            item
            for item in data["per_rep_measurements"][2]["measurements"]
            if item["feature"] == "front_knee_angle"
        )
        self.assertEqual(measured["value"], 135)


if __name__ == "__main__":
    unittest.main()

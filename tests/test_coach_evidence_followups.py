"""Conversation contract: keep the subject and supply useful supporting evidence."""

import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from fencecoach.coach.answer_review import AnswerDraft, AnswerReview
from fencecoach.coach.answer_style import requests_numbers, response_evidence_issues, style_issues
from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.intent import classify_coach_question, question_phases, question_topics
from fencecoach.coach.latency import coaching_session_context
from fencecoach.coach.technique_evidence import question_scoped_session_context
from fencecoach.coach.turns import contextual_question
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings


def session(question, previous="How was my back leg extension?"):
    reps = []
    for number, (rear, torso) in enumerate([(177.8, 3), (174.1, 6), (177.9, 9)], 1):
        time_ms = number * 2000
        recovery = 100 + number * 5

        def measurement(value, phase="lunge_finish"):
            return {"value": value, "unit": "deg", "phase": phase, "time_ms": time_ms}

        reps.append(
            {
                "rep_number": number,
                "lunge_ms": time_ms,
                "selected_frame_ms": time_ms,
                "findings": [],
                "unavailable": [],
                "status": "available",
                "measurements": {
                    "rear_knee_angle": measurement(rear),
                    "projected_torso_tilt": measurement(torso),
                },
                "phases": {
                    "recovery_peak": {
                        "start_ms": time_ms + 300,
                        "end_ms": time_ms + 500,
                        "method": "phase_median",
                        "sample_count": 3,
                        "measurements": {
                            "rear_knee_angle": {
                                **measurement(recovery, "recovery_peak"),
                                "sample_count": 3,
                                "range": [recovery - 1, recovery + 1],
                            }
                        },
                    }
                },
                "reference_comparison": {
                    "status": "available",
                    "coaching_priorities": [],
                    "rows": [
                        {
                            "metric": "rear_knee_angle",
                            "phase": "finish",
                            "unit": "deg",
                            "current": rear,
                            "reference_range": [174, 180],
                            "reference_median": 177,
                            "direction": "overlaps",
                        },
                        {
                            "metric": "projected_torso_tilt",
                            "phase": "finish",
                            "unit": "deg",
                            "current": torso,
                            "reference_range": [2, 5],
                            "reference_median": 3,
                            "direction": "overlaps" if torso <= 5 else "higher",
                        },
                        {
                            "metric": "rear_knee_angle",
                            "phase": "recovery_peak",
                            "unit": "deg",
                            "current": recovery,
                            "reference_range": [100, 110],
                            "reference_median": 105,
                            "direction": "overlaps" if recovery <= 110 else "higher",
                        },
                    ],
                },
            }
        )
    return CoachRequest(
        session_id="evidence-followup",
        question=question,
        technique_evaluation={"coaching_mode": "reference_comparison", "reps": reps},
        conversation_history=[ConversationMessage(role="user", content=previous)],
    )


class Writer:
    model = "contract-fixture"

    def __init__(self, *answers):
        self.answers = iter(answers)
        self.inputs = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.inputs.append(messages)
        return AIMessage(content=next(self.answers))


class ReviewedWriter(Writer):
    def __init__(self, answer, record, supporting_example=""):
        super().__init__(
            AnswerDraft(
                answer=answer, supporting_example=supporting_example, session_evidence_ids=[record]
            ).model_dump_json()
        )
        self.record = record

    def bind(self, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        self_test = self

        class Judge:
            def invoke(self, messages):
                self_test.judge_input = json.loads(messages[1].content)
                review = AnswerReview(
                    addresses_question=True,
                    grounded=True,
                    uses_session_evidence=True,
                    session_evidence_relevant=True,
                    session_evidence_ids=[self_test.record],
                )
                return {"parsed": review, "raw": AIMessage(content=review.model_dump_json())}

        return Judge()


# These fixtures exercise the legacy writer/reviewer and evidence-tool protocol.
@patch.object(settings, "fencecoach_verified_dialogue", False)
class EvidenceFollowupTests(unittest.TestCase):
    def test_repeated_supporting_value_is_presented_only_once(self):
        answer = "Your later recoveries differed more. Rep 3's rear knee was 115.0 degrees versus 100–110 degrees in the reference."
        draft = AnswerDraft(
            answer=answer, supporting_example="Rep 3's rear knee was 115 deg at the recovery peak."
        )
        self.assertEqual(draft.conversational_text, answer)

    def test_supporting_example_with_new_reference_data_is_kept(self):
        draft = AnswerDraft(
            answer="Your later torso position differed. Rep 3 reached 9 degrees.",
            supporting_example="Rep 3's torso tilt was 9 degrees versus the reference range of 2–5 degrees.",
        )
        self.assertIn("2–5 degrees", draft.conversational_text)

    def test_assessment_and_one_model_written_example_form_one_reply(self):
        assessment = "Your torso differed more from the references on the later reps."
        support = "Rep 3's torso tilt was 9 degrees against your reference range of 2–5 degrees."
        model = ReviewedWriter(assessment, "rep:3:reference:finish:projected_torso_tilt", support)
        result = run_conversation(session("Analyze my torso"), "gemini", model=model)
        self.assertEqual(result.report.summary, assessment + " " + support)
        self.assertEqual(model.judge_input["draft"]["answer"], result.report.summary)

    def test_supporting_example_illustrates_the_requested_difference(self):
        snapshot = question_scoped_session_context(session("Analyze my torso"))
        packet = json.loads(coaching_session_context(snapshot))
        record = packet["representative_support"]["record"]
        self.assertEqual(
            (record["rep"], record["metric"], record["current"]), (3, "projected_torso_tilt", 9)
        )
        self.assertEqual(packet["requested_scope"]["topics"], ["torso"])

    def test_recovery_example_uses_recovery_phase_not_finish(self):
        packet = json.loads(question_scoped_session_context(session("How were my recoveries?")))
        record = packet["representative_support"]["record"]
        self.assertEqual(
            (record["rep"], record["metric"], record["phase"]),
            (3, "rear_knee_angle", "recovery_peak"),
        )

    def test_plural_assessment_is_a_summary_and_explicit_all_reps_is_a_breakdown(self):
        self.assertNotEqual(
            classify_coach_question("How were my recoveries during these reps?").kind, "all_reps"
        )
        self.assertEqual(classify_coach_question("Analyze all 3 reps").kind, "all_reps")

    def test_verdict_followup_does_not_force_an_unrequested_rep_list(self):
        resolved = contextual_question(
            session("so are they good or bad", "How were my recoveries?")
        )
        self.assertEqual(question_topics(resolved), ["recovery"])
        self.assertNotEqual(classify_coach_question(resolved).kind, "all_reps")

    def test_numerical_wordings_keep_body_subject(self):
        for wording in [
            "can you give me a number that supports that",
            "can you give me quantifiable numbers",
            "show me a statistic",
            "quantify that",
            "what are the measurements",
        ]:
            with self.subTest(wording=wording):
                resolved = contextual_question(session(wording))
                self.assertEqual(question_topics(resolved), ["rear_leg"])
                self.assertTrue(requests_numbers(resolved))
                self.assertNotEqual(classify_coach_question(resolved).kind, "all_reps")

    def test_numeric_followup_preserves_recovery_phase_and_rep(self):
        query = session(
            "can you give me quantifiable numbers",
            "Analyze my rear knee at the recovery peak in rep 2",
        )
        resolved = contextual_question(query)
        self.assertIn("rep 2", resolved)
        self.assertEqual(question_phases(resolved), {"recovery_peak"})
        answer = "Rep 2's rear knee was 110 degrees at the recovery peak, within your reference range of 100–110 degrees."
        model = Writer(answer)
        result = run_conversation(query, "local", model=model)
        self.assertEqual(result.report.summary, answer)
        evidence = next(
            message.content
            for message in model.inputs[0]
            if str(message.content).startswith("Active session evidence")
        )
        packet = json.loads(evidence.split("(reference data): ", 1)[1])
        self.assertEqual([rep["rep"] for rep in packet["per_rep_measurements"]], [2])
        self.assertTrue(
            all(
                row["phase"] == "recovery_peak"
                for row in packet["per_rep_measurements"][0]["reference_comparisons"]
            )
        )

    def test_corrected_subject_wins_over_rejected_body_part(self):
        query = session(
            "give me a statistic",
            "Why front leg? I'm asking about my recovery at the recovery peak in rep 2",
        )
        resolved = contextual_question(query)
        self.assertIn("recovery", resolved)
        self.assertNotIn("front leg", resolved)
        self.assertEqual(question_phases(resolved), {"recovery_peak"})

    def test_explicit_new_subject_does_not_inherit_old_one(self):
        query = session("Give me the torso angle for rep 3")
        self.assertEqual(contextual_question(query), query.question)

    def test_broad_session_request_resets_older_specific_subject(self):
        query = session("Give me a number that supports that", "How was my torso in rep 2?")
        query.conversation_history.append(
            ConversationMessage(role="user", content="Analyze all 3 reps")
        )
        resolved = contextual_question(query)
        self.assertNotIn("torso", resolved)
        self.assertNotIn("rep 2", resolved)

    def test_qualitative_reply_to_numeric_request_is_repaired_by_writer(self):
        answer = "For example, rep 2's back knee reached 174.1 degrees at the finish, within your reference range of 174–180 degrees."
        model = Writer("Your back leg extension matched your references at the finish.", answer)
        result = run_conversation(
            session("can you give me quantifiable numbers"), "local", model=model
        )
        self.assertEqual(result.report.summary, answer)
        self.assertEqual(len(model.inputs), 2)
        self.assertTrue(any(step.step == "answer_repair" for step in result.trace))

    def test_repeated_numeric_request_can_repeat_the_same_supported_fact(self):
        answer = "Rep 2's back knee reached 174.1 degrees at the finish, within your reference range of 174–180 degrees."
        query = session("Can you give me quantifiable numbers?")
        query.conversation_history.extend(
            [
                ConversationMessage(role="user", content="Give me a number that supports that"),
                ConversationMessage(role="assistant", content=answer),
            ]
        )
        model = Writer(answer)
        result = run_conversation(query, "local", model=model)
        self.assertEqual(result.report.summary, answer)
        self.assertEqual(len(model.inputs), 1)

    def test_normal_analysis_uses_one_concrete_example(self):
        answer = "Your torso differed from your references on the later reps. For example, rep 3's torso tilt was 9 degrees at the finish versus the reference range of 2–5 degrees."
        model = Writer(answer)
        result = run_conversation(
            session("How was my torso?", "Analyze my torso"), "local", model=model
        )
        self.assertEqual(result.report.summary, answer)
        self.assertEqual(len(model.inputs), 1)

    def test_analysis_without_support_gets_one_rep_example_on_repair(self):
        answer = "Your torso was less consistent at the finish. Rep 3 showed more torso tilt than your reference examples."
        model = Writer("Your torso was less consistent at the finish.", answer)
        result = run_conversation(session("Can you analyze my torso?"), "local", model=model)
        self.assertEqual(result.report.summary, answer)
        self.assertEqual(len(model.inputs), 2)

    def test_wrong_body_stat_is_repaired_without_user_repeating_question(self):
        answer = "Rep 2's back knee reached 174.1 degrees at the finish, within your reference range of 174–180 degrees."
        model = Writer("Rep 2's torso tilt was 6 degrees.", answer)
        result = run_conversation(
            session("give me a number that supports that"), "local", model=model
        )
        self.assertEqual(result.report.summary, answer)

    def test_writer_answer_survives_independent_review_with_finish_alias(self):
        answer = "Your torso differed more on the later reps. Rep 3's finish tilt was 9 degrees against your reference range of 2–5 degrees."
        model = ReviewedWriter(answer, "rep:3:reference:finish:projected_torso_tilt")
        result = run_conversation(session("Analyze my torso"), "gemini", model=model)
        self.assertEqual(result.report.summary, answer)
        self.assertNotIn("final_answer", AnswerReview.model_fields)
        self.assertEqual(model.judge_input["draft"]["answer"], answer)

    def test_one_stat_is_allowed_and_a_default_data_dump_is_flagged(self):
        question = "How was my torso?"
        concise = "Your torso varied at the finish. Rep 3 was 9 degrees versus 2–5 degrees in your reference."
        self.assertEqual(style_issues(question, concise, personal=True), [])
        self.assertTrue(style_issues(question, concise + " Rep 1 was 3 degrees.", personal=True))

    def test_one_example_can_explain_reference_and_value_in_separate_sentences(self):
        answer = "Your back leg matched the reference range of 174–180 degrees. For example, rep 2 reached 174.1 degrees."
        self.assertEqual(style_issues("How was my back leg?", answer, personal=True), [])

    def test_an_explicit_comparison_can_use_two_reps_as_evidence(self):
        answer = "Rep 1's torso tilt was 3 degrees. Rep 3's torso tilt was 9 degrees."
        self.assertEqual(
            style_issues("Compare the torso position in reps 1 and 3", answer, personal=True), []
        )

    def test_numeric_request_requires_a_stat_when_evidence_exists(self):
        self.assertTrue(
            response_evidence_issues(
                "quantifiable numbers", "Your back leg matched your references.", available=True
            )
        )
        self.assertEqual(
            response_evidence_issues(
                "quantifiable numbers", "Rep 2 reached 174.1 degrees.", available=True
            ),
            [],
        )
        self.assertEqual(
            response_evidence_issues("how many reps", "There were 3 reps.", available=True), []
        )
        self.assertEqual(
            response_evidence_issues(
                "give me a number", "No matching measurement is available.", available=False
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()

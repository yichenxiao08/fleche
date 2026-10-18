"""The coach owns its prose and tool choices while application state carries scope."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.exceptions import ModelRateLimitError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fencecoach.coach.conversation import CoachAnswerError, run_conversation
from fencecoach.coach.router import CircuitBreaker
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState, MetricObservation
from fencecoach.settings import settings

FIXTURE = Path(__file__).resolve().parents[1] / "evals/coach_audit/current.json"


class Writer:
    model = "natural-writer-fixture"

    def __init__(self, *replies):
        self.replies = iter(replies)
        self.inputs = []
        self.tools = {}

    def bind_tools(self, tools):
        self.tools = {tool.name: tool for tool in tools}
        return self

    def invoke(self, messages):
        self.inputs.append(messages)
        return next(self.replies)


@patch.object(settings, "fencecoach_verified_dialogue", False)
class NaturalDialogueTests(unittest.TestCase):
    def test_failed_writer_is_not_silently_replaced_with_a_canned_library_reply(self):
        wrong = AIMessage(content="Extend your sword arm sideways at shoulder width.")
        model = Writer(wrong, wrong)
        request = CoachRequest(
            session_id="failed-writer",
            question="In general, how should I extend my sword arm?",
        )
        published = []
        with self.assertRaises(CoachAnswerError):
            run_conversation(request, "local", model=model, on_text=published.append)
        self.assertEqual(published, [])

    def test_writer_can_author_a_reply_outside_a_prebuilt_sentence_inventory(self):
        answer = "Start slowly enough that you can notice the sequence. Add pace once the movement feels familiar."
        model = Writer(AIMessage(content=answer))
        request = CoachRequest(session_id="natural-chat", question="How can I practice calmly?")
        run = run_conversation(request, "local", model=model)
        self.assertEqual(run.report.summary, answer)
        self.assertEqual(run.question, request.question)
        self.assertEqual(run.answer_contract["engine"], "llm_tools")
        self.assertTrue(run.answer_contract["model_authored"])
        self.assertIn("search_coaching_library", model.tools)
        self.assertFalse(any('"units"' in str(message.content) for message in model.inputs[0]))

    def test_writer_chooses_and_reads_a_real_measurement_tool_before_answering(self):
        answer = "Your recorded recovery time was 1.5 seconds. That duration alone doesn't grade the technique."
        model = Writer(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_session_metrics",
                        "args": {"metric_name": "recovery"},
                        "id": "recovery-reading",
                    }
                ],
            ),
            AIMessage(content=answer),
        )
        request = CoachRequest(
            session_id="natural-tools",
            question="What's my recovery time?",
            metrics=[
                MetricObservation(
                    metric_id="rep:1:recovery",
                    name="recovery_time",
                    value=1.5,
                    unit="s",
                    confidence=0.95,
                )
            ],
        )
        run = run_conversation(request, "local", model=model)
        returned = next(message for message in model.inputs[1] if isinstance(message, ToolMessage))
        self.assertEqual(json.loads(returned.content)["measurements"][0]["value"], 1.5)
        self.assertEqual(run.report.summary, answer)
        self.assertTrue(any(event.step == "get_session_metrics" for event in run.trace))
        self.assertIn("rep:1:recovery", run.dialogue_state.last_cited_evidence)

    def test_explanation_followup_can_use_pronouns_without_a_repeated_data_dump(self):
        request = CoachRequest.model_validate_json(FIXTURE.read_text())
        request.question = "Why does that matter?"
        request.dialogue_state = DialogueState(
            session_id=request.session_id,
            subject="my torso at starting guard",
            topics=["torso"],
            phases=["starting_guard"],
            all_reps=True,
        )
        answer = "It describes your starting position. The angle alone doesn't establish your balance or explain what caused it."
        model = Writer(AIMessage(content=answer))
        run = run_conversation(request, "local", model=model)
        self.assertEqual(run.report.summary, answer)
        self.assertEqual(len(model.inputs), 1)
        self.assertTrue(run.dialogue_state.all_reps)
        self.assertEqual(run.dialogue_state.topics, ["torso"])

    def test_fresh_unknown_subject_replaces_old_subject_and_remains_active(self):
        request = CoachRequest.model_validate_json(FIXTURE.read_text())
        request.question = "How was my shoulder mobility?"
        request.dialogue_state = DialogueState(
            session_id=request.session_id,
            subject="my torso",
            topics=["torso"],
            rep_numbers=[2],
        )
        answer = "These records don't measure shoulder mobility, so I can't assess yours from them."
        run = run_conversation(request, "local", model=Writer(AIMessage(content=answer)))
        self.assertEqual(run.report.summary, answer)
        self.assertEqual(run.dialogue_state.topics, [])
        self.assertEqual(run.dialogue_state.rep_numbers, [])
        self.assertIn("shoulder mobility", run.dialogue_state.subject)
        request.conversation_history = [
            ConversationMessage(role="user", content=request.question),
            ConversationMessage(role="assistant", content=answer),
        ]
        request.question = "Why?"
        request.dialogue_state = run.dialogue_state
        explanation = "A mobility assessment needs the range of the movement; a few pose samples don't establish that range."
        followup = run_conversation(request, "local", model=Writer(AIMessage(content=explanation)))
        self.assertEqual(followup.report.summary, explanation)
        self.assertIn("shoulder mobility", followup.dialogue_state.subject)
        self.assertNotIn("torso", followup.dialogue_state.topics)

    def test_real_provider_rate_limit_uses_shared_router_and_same_conversation(self):
        class RateLimited(Writer):
            def invoke(self, messages):
                raise ModelRateLimitError("quota exhausted")

        answer = "Start slowly enough that you can notice the sequence."
        local = Writer(AIMessage(content=answer))
        request = CoachRequest(session_id="provider-route", question="How can I practice calmly?")
        with (
            patch("fencecoach.coach.router.gemini_circuit", CircuitBreaker()),
            patch.object(settings, "fencecoach_local_fallback", True),
            patch(
                "fencecoach.coach.conversation.provider_status", return_value={"local_ready": True}
            ),
            patch("fencecoach.coach.conversation.chat_model", side_effect=[RateLimited(), local]),
        ):
            run = run_conversation(request, "gemini")
        self.assertEqual(run.report.summary, answer)
        self.assertEqual(run.fallback_reason, "rate_limit")
        self.assertEqual(run.question, request.question)
        self.assertEqual(run.dialogue_state.session_id, request.session_id)
        human = [message for message in local.inputs[0] if isinstance(message, HumanMessage)][-1]
        self.assertEqual(human.content.removesuffix("\n/no_think"), request.question)

    def test_original_followup_wording_and_persisted_scope_reach_the_writer(self):
        request = CoachRequest.model_validate_json(FIXTURE.read_text())
        request.question = "What about every rep?"
        request.dialogue_state = DialogueState(
            session_id=request.session_id,
            subject="my torso at starting guard",
            topics=["torso"],
            phases=["starting_guard"],
            rep_numbers=[2],
        )
        answer = " ".join(
            f"Rep {rep['rep_number']}'s torso tilt in starting guard measured "
            f"{rep['phases']['starting_guard']['measurements']['projected_torso_tilt']['value']} degrees."
            for rep in request.technique_evaluation["reps"]
        )
        model = Writer(AIMessage(content=answer))
        run = run_conversation(request, "local", model=model)
        human = [message for message in model.inputs[0] if isinstance(message, HumanMessage)][-1]
        self.assertEqual(human.content.removesuffix("\n/no_think"), request.question)
        scope_message = model.inputs[0][0].content
        self.assertIn('"all_reps":true', scope_message)
        self.assertIn("my torso at starting guard", scope_message)
        self.assertTrue(run.dialogue_state.all_reps)
        self.assertEqual(run.dialogue_state.rep_numbers, [])
        self.assertEqual(run.dialogue_state.topics, ["torso"])
        self.assertEqual(set(run.dialogue_state.phases), {"starting_guard"})
        self.assertEqual(run.question, "What about every rep?")
        self.assertEqual(run.report.summary, answer)


if __name__ == "__main__":
    unittest.main()

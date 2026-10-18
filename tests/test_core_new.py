"""Layer 1 architectural contracts; no grading of model prose here."""

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.core_new import _briefing, _briefing_v2, run_new_core, standing_briefing
from fencecoach.schemas import CoachRequest, ConversationMessage, MetricObservation
from fencecoach.settings import Settings, settings


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.inputs = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.inputs.append(list(messages))
        return next(self.replies)


def call(name, args, ident="1"):
    return {"name": name, "args": args, "id": ident, "type": "tool_call"}


class NewCoreTests(unittest.TestCase):
    def test_context_always_present_with_latest_ten_messages(self):
        history = [
            ConversationMessage(role="user" if i % 2 == 0 else "assistant", content=str(i))
            for i in range(12)
        ]
        request = CoachRequest(
            session_id="saved", question="is it good?", conversation_history=history
        )
        model = Model([AIMessage(content="I am assuming you mean the rear leg.")])
        run = run_new_core(request, "local", model=model, profile="v3")
        self.assertEqual(model.inputs[0][-1], HumanMessage(content="is it good?"))
        self.assertEqual([m.content for m in model.inputs[0][1:-1]], [str(i) for i in range(2, 12)])
        self.assertIn(standing_briefing(request, "v3"), model.inputs[0][0].content)
        self.assertIn("Never substitute a different rep or phase", model.tools[0].description)
        self.assertEqual(run.report.summary, "I am assuming you mean the rear leg.")
        self.assertEqual(run.answer_contract["tool_calls"], 0)

    def test_empty_and_failed_retrieval_do_not_gate_model_answer(self):
        for result in ([], RuntimeError("library unavailable")):
            with (
                self.subTest(result=result),
                patch(
                    "fencecoach.coach.core_new.search_knowledge",
                    side_effect=result if isinstance(result, Exception) else None,
                    return_value=result,
                ),
            ):
                model = Model(
                    [
                        AIMessage(
                            content="",
                            tool_calls=[call("search_coaching_library", {"query": "missing"})],
                        ),
                        AIMessage(content="That drill is missing; we still have the saved timing."),
                    ]
                )
                run = run_new_core(
                    CoachRequest(session_id="saved", question="a drill?"),
                    "local",
                    model=model,
                    profile="v0",
                )
                self.assertEqual(
                    run.report.summary, "That drill is missing; we still have the saved timing."
                )
                self.assertTrue(any(isinstance(m, ToolMessage) for m in model.inputs[1]))

    def test_budget_bounds_parallel_and_repeated_tool_requests(self):
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        call("search_coaching_library", {"query": "lunge"}, str(i))
                        for i in range(4)
                    ],
                ),
                AIMessage(content="I can answer from what I have."),
            ]
        )
        with patch("fencecoach.coach.core_new.search_knowledge", return_value=[]) as search:
            run = run_new_core(
                CoachRequest(session_id="saved", question="How did I do?"),
                "local",
                model=model,
                profile="v0",
            )
        self.assertEqual(search.call_count, 2)
        self.assertEqual(run.answer_contract["tool_calls"], 2)
        replies = [m for m in model.inputs[1] if isinstance(m, ToolMessage)]
        self.assertEqual(len(replies), 4)  # Every call ID is resolved for provider protocol.
        self.assertIn("tool_budget", replies[-1].content)

    def test_briefing_cache_ignores_turns_and_invalidates_evidence(self):
        _briefing.cache_clear()
        metric = MetricObservation(
            metric_id="rep-01-arm",
            name="right_arm_extension_at_peak",
            value=1.0,
            unit="ratio",
            confidence=0.9,
        )
        request = CoachRequest(session_id="saved", question="arm?", metrics=[metric])
        first = standing_briefing(request, "v0")
        request.question = "why?"
        self.assertEqual(standing_briefing(request, "v0"), first)
        self.assertEqual(_briefing.cache_info().hits, 1)
        request.metrics[0].value = 0.8
        self.assertNotEqual(standing_briefing(request, "v0"), first)
        self.assertIn("raw event, not phase median", standing_briefing(request, "v0"))
        self.assertIn("upper-arm plus forearm", standing_briefing(request, "v0"))

    def test_layer1_prompt_variants_are_isolated_and_v3_tools_are_actionable(self):
        _briefing_v2.cache_clear()
        request = CoachRequest(session_id="saved", question="and the second rep?")
        briefing = standing_briefing(request, "v2")
        self.assertIn("Athlete wording to saved feature names", briefing)
        self.assertIn("A rep value describes that rep only", briefing)
        request.question = "why does that matter?"
        self.assertEqual(standing_briefing(request, "v2"), briefing)
        self.assertEqual(_briefing_v2.cache_info().hits, 1)
        request.question = "and the second rep?"
        model = Model([AIMessage(content="I don't have a second-rep value in this briefing.")])
        run_new_core(request, "local", model=model, profile="v3")
        descriptions = {tool.name: tool.description for tool in model.tools}
        self.assertIn(
            "Never substitute a different rep or phase", descriptions["get_session_evidence"]
        )
        self.assertIn(
            "teaching material, not facts about this athlete",
            descriptions["search_coaching_library"],
        )

    def test_opt_in_bypasses_old_resolver_and_review(self):
        request = CoachRequest(session_id="saved", question="hello")
        model = Model([AIMessage(content="A model-authored answer.")])
        with (
            patch.object(settings, "coach_core", "new"),
            patch(
                "fencecoach.coach.conversation.resolve_turn",
                side_effect=AssertionError("old resolver called"),
            ),
        ):
            run = run_conversation(request, "local", model=model)
        self.assertEqual(run.report.summary, "A model-authored answer.")
        self.assertIsNotNone(run.dialogue_state)
        self.assertEqual(run.dialogue_state.core_version, "new2")
        self.assertFalse(run.answer_contract["output_checks"])
        self.assertEqual(run.retrieval_method, "full-authored-knowledge+session-packet")
        with patch.dict(os.environ):
            os.environ.pop("COACH_CORE", None)
            self.assertEqual(Settings(_env_file=None).coach_core, "new")
        self.assertEqual(Settings(_env_file=None, coach_core="old").coach_core, "old")


if __name__ == "__main__":
    unittest.main()

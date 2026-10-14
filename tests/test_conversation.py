from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fencecoach.coach.conversation import _text
from fencecoach.coach.graph import run_coach
from fencecoach.coach.grounding import grounded_fallback, unsupported_claims
from fencecoach.repository import Repository
from fencecoach.schemas import (
    CoachRequest,
    ConversationMessage,
    KnowledgeSource,
    MetricObservation,
    SessionCreate,
)
from fencecoach.settings import settings


def request(question="What do you mean?"):
    return CoachRequest(
        session_id="chat-session",
        question=question,
        metrics=[
            MetricObservation(
                metric_id="rep-1-knee",
                name="left_knee_angle_at_peak",
                value=110,
                unit="deg",
                confidence=0.9,
                start_ms=2000,
                end_ms=3500,
            ),
            MetricObservation(
                metric_id="rep-1-recovery",
                name="recovery_time",
                value=1.5,
                unit="s",
                confidence=0.9,
                start_ms=3500,
                end_ms=5000,
            ),
        ],
    )


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.inputs = []
        self.tools = {}

    def bind_tools(self, tools):
        self.tools = {tool.name: tool for tool in tools}
        return self

    def invoke(self, messages):
        self.inputs.append(messages)
        return next(self.replies)


# ScriptedModel fixtures test the retained legacy tool loop and free-prose writer.
@patch.object(settings, "fencecoach_verified_dialogue", False)
class ConversationTests(unittest.TestCase):
    def test_invented_angle_is_blocked_and_fallback_is_concrete(self):
        data = request("What is wrong with my lunge?")
        self.assertTrue(
            unsupported_claims(
                "Your knee angle is 120 degrees. Lower it to 90 degrees.", data.metrics
            )
        )
        text = grounded_fallback(data, data.metrics)
        self.assertIn("2.00s", text)
        self.assertIn("110", text)
        self.assertIn("reset", text)
        self.assertNotIn("reliable pass or fail", text)

    def test_internal_deliberation_is_not_saved_as_an_answer(self):
        self.assertEqual(_text(AIMessage(content="<think>Still thinking")), "")
        self.assertEqual(
            _text(AIMessage(content="Okay, the user is asking about their lunge.")), ""
        )
        self.assertEqual(
            _text(AIMessage(content="<think>Internal text</think>Here is the explanation.")),
            "Here is the explanation.",
        )

    def test_requested_plan_uses_retrieved_guidance_and_stays_a_draft(self):
        doc = KnowledgeSource(
            source_id="library#one",
            source="test-guidance.md",
            text="Practice a slow, unopposed hand-then-foot sequence.",
        )
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_coaching_library",
                            "args": {"query": "simple foil lunge"},
                            "id": "lookup",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "prepare_practice_plan",
                            "args": {
                                "name": "Slow sequence",
                                "steps": ["Begin with the hand, then launch the foot."],
                                "success_criterion": "Keep the sequence deliberate.",
                                "knowledge_ids": ["library#one"],
                            },
                            "id": "draft",
                        }
                    ],
                ),
                AIMessage(
                    content="Try that sequence slowly; the card below is ready if you want to save it."
                ),
            ]
        )
        with patch("fencecoach.coach.conversation.search_knowledge", return_value=[doc]):
            run = run_coach(request("Give me a drill"), mode="local", model=model)
        self.assertEqual(run.report.next_drill.evidence[0].source_id, "library#one")
        returned = [message for message in model.inputs[2] if isinstance(message, ToolMessage)][-1]
        self.assertFalse(json.loads(returned.content)["saved"])

    def test_short_followup_keeps_actual_exchange_without_forced_tools(self):
        data = request("Why?")
        data.conversation_history = [
            ConversationMessage(role="user", content="What does hand first mean?"),
            ConversationMessage(
                role="assistant",
                content="Begin moving your weapon hand before launching the foot in a simple drill.",
            ),
        ]
        model = ScriptedModel(
            [
                AIMessage(
                    content="It helps you explore the sequence without rushing both movements together."
                )
            ]
        )
        run = run_coach(data, mode="local", model=model)
        self.assertEqual(len(model.inputs), 1)
        self.assertEqual(
            [
                message.content.removesuffix("\n/no_think")
                for message in model.inputs[0]
                if isinstance(message, HumanMessage)
            ],
            ["What does hand first mean?", "Why?"],
        )
        self.assertTrue(any(e.step == "assess_current_session" for e in run.trace))
        self.assertTrue(any(s.source_id == "current-session:chat-session" for s in run.sources))
        self.assertFalse(any(e.step == "get_session_metrics" for e in run.trace))
        self.assertIsNone(run.report.next_drill)

    def test_measurement_tool_uses_the_agents_explicit_feature_filter(self):
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_session_metrics",
                            "args": {"metric_name": "knee"},
                            "id": "measure",
                        }
                    ],
                ),
                AIMessage(
                    content="At 2.0 seconds, the knee reading is 110 degrees. Check which leg is in front, then try a slow repeat so that you can compare the same finish."
                ),
            ]
        )
        run = run_coach(request("Analyze my lunge"), mode="local", model=model)
        returned = next(message for message in model.inputs[1] if isinstance(message, ToolMessage))
        payload = json.loads(returned.content)
        self.assertEqual([item["metric_id"] for item in payload["measurements"]], ["rep-1-knee"])
        self.assertTrue(
            any(
                ref.source_id == "rep-1-knee"
                for observation in run.report.observations
                for ref in observation.evidence
            )
        )
        self.assertIsNone(run.report.next_drill)

    def test_empty_metric_filter_does_not_silently_remove_other_session_features(self):
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "get_session_metrics", "args": {}, "id": "measure"}],
                ),
                AIMessage(
                    content="At 2.0 seconds, the knee reading is 110 degrees. Check which leg is in front, then try a slow repeat so that you can compare the same finish."
                ),
            ]
        )
        run_coach(request("Analyze my lunge"), mode="local", model=model)
        returned = next(message for message in model.inputs[1] if isinstance(message, ToolMessage))
        payload = json.loads(returned.content)
        self.assertEqual(
            [item["metric_id"] for item in payload["measurements"]],
            ["rep-1-knee", "rep-1-recovery"],
        )

    def test_reviewed_timestamp_tool_does_not_claim_intervals_are_lunges(self):
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "inspect_reviewed_rep", "args": {"rep_number": 1}, "id": "rep"}
                    ],
                ),
                AIMessage(content="The first reviewed interval runs from 2 to 3.5 seconds."),
            ]
        )
        run_coach(request("Show me the first rep"), mode="local", model=model)
        payload = json.loads(
            next(message.content for message in model.inputs[1] if isinstance(message, ToolMessage))
        )
        self.assertEqual((payload["start_ms"], payload["end_ms"]), (2000, 5000))
        self.assertEqual(payload["measurements"][0]["value"], 110)

    def test_practice_tool_rejects_unretrieved_sources(self):
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "prepare_practice_plan",
                            "args": {
                                "name": "Drill",
                                "steps": ["Practice"],
                                "success_criterion": "Control",
                                "knowledge_ids": ["invented"],
                            },
                            "id": "plan",
                        }
                    ],
                ),
                AIMessage(content="I need relevant guidance before drafting that card."),
            ]
        )
        run = run_coach(request("Give me a drill"), mode="local", model=model)
        self.assertIsNone(run.report.next_drill)
        self.assertIn(
            "Retrieve relevant coaching guidance",
            next(
                message.content for message in model.inputs[1] if isinstance(message, ToolMessage)
            ),
        )

    def test_conversation_survives_repository_restart_and_is_session_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.sqlite3"
            repo = Repository(path)
            session = repo.create_session(SessionCreate(title="My clip", metrics=request().metrics))
            data = request("Hi")
            data.session_id = session.session_id
            run = run_coach(
                data,
                mode="local",
                model=ScriptedModel([AIMessage(content="Hi. What would you like to work on?")]),
            )
            repo.save_run(run)
            reopened = Repository(path)
            self.assertEqual(len(reopened.list_runs(session.session_id)), 1)
            context = reopened.coaching_context(session.session_id)
            self.assertEqual(
                context["conversation_history"],
                [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hi. What would you like to work on?"},
                ],
            )
            other = repo.create_session(
                SessionCreate(title="Other clip", metrics=request().metrics)
            )
            self.assertEqual(
                reopened.coaching_context(other.session_id)["conversation_history"], []
            )


if __name__ == "__main__":
    unittest.main()

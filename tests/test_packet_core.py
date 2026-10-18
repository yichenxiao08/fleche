"""Conversation boundaries, source separation, retries and runtime deadlines."""

import asyncio
import json
import time
import unittest
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessage, HumanMessage

from fencecoach.coach.core_packet import run_packet_core
from fencecoach.coach.number_trace import trace_numbers
from fencecoach.coach.packet_runtime import PacketQwen
from fencecoach.coach.turn_packet import build_packet, resolve_scope
from fencecoach.schemas import (
    CoachRequest,
    ConversationMessage,
    DialogueState,
    KnowledgeSource,
)


def snapshot():
    rows = []
    for rep in (1, 2, 5):
        measures = {}
        for feature, value in (
            ("front_knee_angle", 140 + rep),
            ("rear_knee_angle", 170 + rep),
            ("weapon_elbow_angle", 160 + rep),
            ("projected_torso_tilt", 4 + rep),
            ("estimated_active_recovery_time", rep / 10),
        ):
            measures[feature] = {
                "evidence_id": f"rep:{rep}:{feature}",
                "feature": feature,
                "rep": rep,
                "value": value,
                "unit": "seconds" if "time" in feature else "deg",
                "phase": None if "time" in feature else "lunge_finish",
                "meaning": "universal target 90 degrees must not enter packet",
            }
        rows.append(
            {
                "rep": rep,
                "measures": measures,
                "phases": {"lunge_finish": {"values": {}, "units": {}}},
                "reference_comparisons": [{"reference_range": [80, 90]}],
            }
        )
    return {"per_rep_measurements": rows, "session_measurements": []}


class FakeModel:
    def __init__(self, *answers):
        self.answers = iter(answers)
        self.inputs = []
        self.binds = 0

    def bind_tools(self, tools):
        self.binds += 1
        return self

    def invoke(self, messages):
        self.inputs.append(messages)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, AIMessage):
            return answer
        return AIMessage(content=answer)


class Busy(Exception):
    status_code = 503


class Limited(Exception):
    status_code = 429


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.request = CoachRequest(session_id="clip", question="how is my arm extension?")
        self.snapshot = snapshot()
        self.library = patch(
            "fencecoach.coach.turn_packet.search_knowledge",
            return_value=[
                KnowledgeSource(
                    source_id="guide#chunk-0",
                    source="guide",
                    text="General teaching: keep the requested movement controlled; inspect the matching phase.",
                )
            ],
        )
        self.library.start()
        self.addCleanup(self.library.stop)

    def turn(self, question, state=None):
        self.request.question = question
        self.request.dialogue_state = state
        state = resolve_scope(self.request, self.snapshot)
        return state, build_packet(self.request, state, self.snapshot)

    def test_topic_rep_and_phase_are_independent(self):
        state, _ = self.turn("my arm at the lunge finish in rep 2")
        state, packet = self.turn("why does that matter?", state)
        self.assertEqual(state.topics, ["arm"])
        self.assertEqual(state.rep_numbers, [2])
        self.assertEqual(state.phases, ["lunge_finish"])
        self.assertEqual({r["rep"] for r in packet["measurements"]}, {2})
        state, packet = self.turn("and my recovery?", state)
        self.assertEqual(state.topics, ["recovery"])
        self.assertEqual(state.phases, ["active_recovery"])
        self.assertEqual(state.rep_numbers, [2])
        self.assertEqual(packet["measurements"][0]["value"], 0.2)

    def test_last_rep_is_available_ordinal_not_count_or_recent_rep(self):
        state, _ = self.turn("my front knee in rep 2")
        state, packet = self.turn("what about my last rep?", state)
        self.assertEqual(state.rep_numbers, [5])
        self.assertEqual({r["rep"] for r in packet["measurements"]}, {5})
        state, packet = self.turn("the second rep", state)
        self.assertEqual(state.rep_numbers, [2])
        self.assertTrue(all(r["rep"] == 2 for r in packet["measurements"]))

    def test_missing_rep_never_substitutes_first(self):
        state, packet = self.turn("my arm in rep 4")
        self.assertEqual(packet["measurements"], [])
        self.assertEqual(packet["scope"]["unavailable_requested_reps"], [4])

    def test_movement_is_carried_when_body_part_changes(self):
        state, _ = self.turn("how should a fleche be performed?")
        state, packet = self.turn("how should my legs move?", state)
        self.assertEqual(state.movement, "fleche")
        self.assertEqual(state.topics, ["front_leg", "rear_leg"])
        self.assertEqual(packet["measurements"], [])
        self.assertEqual(
            packet["availability"]["requested_scope"], "no_measurements_for_requested_movement"
        )

    def test_phase_qualifier_keeps_body_part(self):
        state, _ = self.turn("my arm in rep 2")
        state, packet = self.turn("and at recovery peak?", state)
        self.assertEqual(state.topics, ["arm"])
        self.assertEqual(state.phases, ["recovery_peak"])
        self.assertEqual(packet["measurements"], [])

    def test_drill_as_temporal_scope_does_not_override_explicit_subject(self):
        for subject, expected in (
            ("torso", ["torso"]),
            ("arm", ["arm"]),
            ("front knee", ["front_leg"]),
        ):
            state, packet = self.turn(f"how was my {subject} during the drill")
            self.assertEqual(state.topics, expected)
            self.assertTrue(packet["measurements"])

    def test_plain_writer_needs_no_optional_tool_roundtrip(self):
        self.request.question = "my arm in rep 2"
        model = FakeModel("The weapon elbow measured 162 degrees in rep 2.")
        with patch(
            "fencecoach.coach.core_packet._snapshot", return_value=json.dumps(self.snapshot)
        ):
            run = run_packet_core(self.request, "gemini", model=model)
        self.assertEqual(len(model.inputs), 1)
        self.assertEqual(model.binds, 0)
        self.assertEqual(run.report.summary, "The weapon elbow measured 162 degrees in rep 2.")
        self.assertEqual(run.answer_contract["packet"]["scope"]["rep_numbers"], [2])

    def test_library_outage_does_not_gate_full_knowledge_writer(self):
        self.request.question = "Give me the Moonstep drill from your library."
        model = FakeModel("That drill is not in the written knowledge base.")
        with patch(
            "fencecoach.coach.turn_packet.search_knowledge",
            side_effect=AssertionError("No retrieval"),
        ):
            run = run_packet_core(self.request, "groq", model=model)
        self.assertEqual(len(model.inputs), 1)
        self.assertIn("COACHING KNOWLEDGE BASE (writer's copy)", model.inputs[0][0].content)
        self.assertEqual(run.report.summary, "That drill is not in the written knowledge base.")

    def test_clarification_ordinal_selects_option_not_rep(self):
        state, packet = self.turn("is it good?")
        self.assertEqual(len(packet["clarification"]["options"]), 3)
        state, _ = self.turn("the second one", state)
        self.assertEqual(state.topics, ["front_leg"])
        self.assertEqual(state.rep_numbers, [])
        self.assertIsNone(state.open_clarifying_question)

    def test_new_session_discards_other_session_state(self):
        old = DialogueState(
            session_id="other", core_version="new2", topics=["torso"], rep_numbers=[5]
        )
        state, _ = self.turn("how did I do?", old)
        self.assertEqual(state.topics, [])
        self.assertIsNotNone(state.open_clarifying_question)
        self.assertEqual(state.rep_numbers, [])

    def test_h01_no_measurements_retains_subject_and_retrieves_general_guidance(self):
        self.request.evidence_unavailable_reason = "Tracking is unsupported for coaching."
        state = None
        for question, topics in (
            ("what about my knees and legs", ["front_leg", "rear_leg"]),
            ("is my back in the right position", ["torso"]),
            ("is the speed alright, too slow maybe?", ["speed"]),
        ):
            state, packet = self.turn(question, state)
            self.assertEqual(state.topics, topics)
            self.assertEqual(packet["availability"]["status"], "tracking_unsupported")
            self.assertEqual(packet["measurements"], [])
            self.assertTrue(packet["general_guidance"])
            self.assertNotIn("arm", state.topics)
            self.assertIn(
                "Missing measurements do not establish", packet["availability"]["interpretation"]
            )

    def test_reference_ranges_and_numeric_targets_are_not_athlete_evidence(self):
        _, packet = self.turn("my front knee in rep 2")
        self.assertNotIn("reference_range", json.dumps(packet))
        self.assertNotIn("target 90", json.dumps(packet))
        self.assertEqual(packet["measurements"][0]["value"], 142)

    def test_groq_gets_full_knowledge_and_packet_without_tools(self):
        model = FakeModel("Your weapon elbow measured 162 degrees in rep 2.")
        self.request.question = "my arm in rep 2"
        with patch(
            "fencecoach.coach.core_packet._snapshot", return_value=json.dumps(self.snapshot)
        ):
            run = run_packet_core(self.request, "groq", model=model)
        self.assertEqual(model.binds, 0)
        packet = json.loads(model.inputs[0][1].content.split("\n", 1)[1])
        self.assertEqual(packet["scope"]["rep_numbers"], [2])
        self.assertEqual(run.dialogue_state.last_provider, "groq")
        self.assertFalse(run.answer_contract["output_checks"])

    def test_legacy_assistant_claims_are_not_bootstrap_evidence(self):
        self.request.conversation_history = [
            ConversationMessage(role="user", content="my arm?"),
            ConversationMessage(role="assistant", content="Invented personal value 999 degrees."),
        ]
        model = FakeModel("General advice about the arm.")
        run = run_packet_core(self.request, "local", model=model)
        self.assertNotIn("999", str(model.inputs[0]))
        self.request.dialogue_state = run.dialogue_state
        self.request.conversation_history.extend(
            [
                ConversationMessage(role="user", content=self.request.question),
                ConversationMessage(role="assistant", content=run.report.summary),
            ]
        )
        model = FakeModel("A follow-up explanation.")
        self.request.question = "why?"
        run_packet_core(self.request, "local", model=model)
        self.assertIn("General advice about the arm.", str(model.inputs[0]))

    def test_pinned_provider_errors_are_not_retried_or_substituted(self):
        model = FakeModel(Busy("503 busy"), "The model answered.")
        with patch("fencecoach.coach.core_packet.time.sleep") as backoff, self.assertRaises(Busy):
            run_packet_core(self.request, "gemini", model=model)
        self.assertEqual(len(model.inputs), 1)
        backoff.assert_not_called()
        limited = FakeModel(Limited("429"))
        with self.assertRaises(Limited):
            run_packet_core(self.request, "gemini", model=limited)
        self.assertEqual(len(limited.inputs), 1)

    def test_forced_hosted_switch_preserves_external_scope_and_packet(self):
        from fencecoach.coach.router import CircuitBreaker

        self.request.dialogue_state = DialogueState(
            session_id="clip",
            core_version="new2",
            topics=["arm"],
            current_topic="arm",
            rep_numbers=[2],
        )
        self.request.question = "why does that matter?"
        primary = FakeModel(Limited("429"))
        fallback = FakeModel("A straighter elbow describes extension, not blade control.")
        with (
            patch("fencecoach.coach.core_packet.gemini_circuit", CircuitBreaker()),
            patch("fencecoach.coach.core_packet.groq_circuit", CircuitBreaker()),
            patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(self.snapshot)),
            patch("fencecoach.coach.core_packet.chat_model", return_value=fallback),
            patch("fencecoach.coach.core_packet.HostedFallback", return_value=primary),
        ):
            run = run_packet_core(self.request, "gemini")
        self.assertEqual(run.dialogue_state.topics, ["arm"])
        self.assertEqual(run.dialogue_state.rep_numbers, [2])
        self.assertEqual(run.mode, "gemini")
        self.assertEqual(primary.inputs[0][0].content, fallback.inputs[0][0].content)
        self.assertEqual(primary.inputs[0][1].content, fallback.inputs[0][1].content)


class NumberTracingTests(unittest.TestCase):
    def test_cardinals_ordinals_and_pronouns(self):
        result = trace_numbers(
            "The one holding the sword. The 2nd rep; twenty-five degrees; 1,000 milliseconds.",
            {"values": [2, 25, 1000]},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["mentions"]), 3)

    def test_numbers_must_appear_in_packet_not_ids_or_history(self):
        packet = {
            "measurements": [{"value": 144.3, "rep": 2, "evidence_id": "metric:150"}],
            "last_cited_evidence": ["metric:150"],
        }
        self.assertTrue(trace_numbers("144 degrees in the second rep.", packet)["passed"])
        self.assertFalse(trace_numbers("150 degrees is ideal.", packet)["passed"])
        self.assertTrue(trace_numbers("144.3.", packet)["passed"])

    def test_signed_and_rounded_values_have_packet_paths(self):
        result = trace_numbers(
            "-0.64 torso lengths; recovery 0.07 seconds.",
            {"measurements": [{"value": -0.639}, {"value": 0.066}]},
        )
        self.assertTrue(result["passed"])
        self.assertTrue(
            all(m["packet_matches"][0]["match"] == "rounded" for m in result["mentions"])
        )

    def test_presence_is_not_a_semantic_claim_check(self):
        self.assertTrue(
            trace_numbers("160 degrees means more bend.", {"measurements": [{"value": 160}]})[
                "passed"
            ]
        )


class RuntimeTests(unittest.TestCase):
    def test_total_deadline_cancels_stream_and_closes_connection(self):
        class Slow(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                await asyncio.sleep(0.5)
                yield b'{"message":{"content":"late"}}\n'

            async def aclose(self):
                self.closed = True

        stream = Slow()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
        )
        started = time.perf_counter()
        with (
            patch("fencecoach.coach.packet_runtime.httpx.AsyncClient", return_value=client),
            self.assertRaises(TimeoutError),
        ):
            PacketQwen(timeout=0.02).invoke([HumanMessage(content="hello")])
        self.assertLess(time.perf_counter() - started, 0.3)
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from fencecoach.coach.core_packet import run_packet_core, writer_knowledge, writer_reference
from fencecoach.coach.hosted_fallback import HostedError
from fencecoach.coach.router import CircuitBreaker
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState
from tests.test_packet_core import snapshot


class WriterTests(unittest.TestCase):
    def test_v72_projection_keeps_open_question_options_and_full_saved_packet(self):
        class Model:
            def invoke(self, messages):
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(content="A verbatim offline fixture reply.")

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run = run_packet_core(
                CoachRequest(session_id="clip", question="is it good?"), "groq", model=model
            )
        full = run.answer_contract["packet"]
        sent = model.packet
        self.assertNotIn("session_overview", sent)
        self.assertNotIn("session_comparison", sent)
        self.assertIn("session_overview", full)
        self.assertIn("session_comparison", full)
        self.assertEqual(run.dialogue_state.last_packet, full)
        self.assertEqual(json.loads(run.trace[0].detail)["packet"], full)
        for key in ("scope", "availability", "overview_then_clarify", "clarification"):
            self.assertEqual(sent[key], full[key])
        self.assertTrue(sent["overview_then_clarify"])
        self.assertTrue(sent["availability"]["available_session_topics"])
        self.assertTrue(sent["clarification"])
        for row in full["measurements"]:
            grouped = next(
                r
                for r in sent["measurements"]
                if r["feature"] == row["feature"] and r["phase"] == row.get("phase")
            )
            self.assertEqual(grouped["rep_readings"][str(row["rep"])], row["display"])
            self.assertEqual(sent["measurement_meanings"][row["feature"]], row["definition"])

    def test_v72_two_completed_exchanges_keep_packet_scope_and_saved_history(self):
        from fencecoach.coach.core_packet import TURN_REMINDER

        class Model:
            def invoke(self, messages):
                self.messages = messages
                return AIMessage(content="An unchanged model reply.")

        stored = [
            ConversationMessage(role=role, content=content)
            for question, answer in [
                ("my arm on the second rep", "Arm reply."),
                ("and my front knee?", "Knee reply."),
                ("back to my arm", "Return reply."),
            ]
            for role, content in [("user", question), ("assistant", answer)]
        ]
        request = CoachRequest(
            session_id="clip",
            question="why does that matter?",
            conversation_history=stored,
            dialogue_state=DialogueState(
                session_id="clip",
                core_version="new2",
                current_topic="arm",
                topics=["arm"],
                subject="arm",
                phases=["lunge_finish"],
                scope="session",
                rep_numbers=[2],
                turns_completed=3,
            ),
        )
        before = request.model_dump(mode="json")["conversation_history"]
        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run = run_packet_core(request, "groq", model=model)
        self.assertEqual(len([m for m in model.messages if m.type == "system"]), 2)
        self.assertTrue(model.messages[0].content.endswith(TURN_REMINDER))
        self.assertEqual(
            [(m.type, m.content) for m in model.messages[2:-1]],
            [("human" if m.role == "user" else "ai", m.content) for m in stored[-4:]],
        )
        packet = json.loads(model.messages[1].content.split("\n", 1)[1])
        self.assertEqual(packet["scope"]["topics"], ["arm"])
        self.assertEqual(packet["scope"]["rep_numbers"], [2])
        self.assertTrue(packet["measurements"])
        self.assertTrue(all(set(row["rep_readings"]) == {"2"} for row in packet["measurements"]))
        self.assertEqual(request.model_dump(mode="json")["conversation_history"], before)
        self.assertEqual(json.loads(run.trace[0].detail)["stored_conversation_history"], before)
        self.assertEqual(run.report.summary, "An unchanged model reply.")

    def test_l01_connection_exchanges_stay_saved_but_never_reach_writer(self):
        from fencecoach.coach.core_packet import CONNECTION_MESSAGE

        class Model:
            def invoke(self, messages):
                self.messages = messages
                return AIMessage(content="Aim to repeat the same finish each rep.")

        history = [
            ("user", "how's my arm extension?"),
            ("assistant", "Your finishes vary."),
            ("user", "is it good?"),
            ("assistant", CONNECTION_MESSAGE),
            ("user", "is it good?"),
            ("assistant", "It is inconsistent."),
            ("user", "what should I change?"),
            ("assistant", CONNECTION_MESSAGE),
        ]
        request = CoachRequest(
            session_id="clip",
            question="what should I change?",
            conversation_history=[ConversationMessage(role=r, content=c) for r, c in history],
            dialogue_state=DialogueState(
                session_id="clip",
                core_version="new2",
                current_topic="arm",
                topics=["arm"],
                subject="arm",
                phases=["lunge_finish"],
                turns_completed=4,
                already_given=[{"scope": {}, "reply": CONNECTION_MESSAGE}],
            ),
        )
        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run = run_packet_core(request, "groq", model=model)
        sent = [(m.type, m.content) for m in model.messages if m.type in {"human", "ai"}]
        self.assertEqual(
            sent,
            [
                ("human", "how's my arm extension?"),
                ("ai", "Your finishes vary."),
                ("human", "is it good?"),
                ("ai", "It is inconsistent."),
                ("human", "what should I change?"),
            ],
        )
        self.assertNotIn(CONNECTION_MESSAGE, "\n".join(m.content for m in model.messages))
        self.assertEqual([(m.role, m.content) for m in request.conversation_history], history)
        trace = json.loads(run.trace[0].detail)
        self.assertEqual(len(trace["stored_conversation_history"]), 8)
        self.assertEqual(trace["stored_conversation_history"][3]["content"], CONNECTION_MESSAGE)

    def test_reference_trimming_preserves_coaching_except_approved_background(self):
        from fencecoach.settings import settings

        original = (
            settings.fencecoach_knowledge_dir / "fencing_lunge_knowledge_base.md"
        ).read_text(encoding="utf-8")
        trimmed = writer_knowledge()
        coaching = original.split("## 12. Source quality and known gaps", 1)[0]
        coaching = "\n".join(
            line
            for line in coaching.splitlines()
            if not line.startswith(
                (
                    "- **Ask for observable details:**",
                    "**Purpose:**",
                    "**Compiled:**",
                    "- **Firm-footed lunge**",
                    "- **Mobility:**",
                    "- **Muscle imbalance:**",
                    "- **Foil / épée:**",
                )
            )
        )
        self.assertTrue(trimmed.startswith(coaching.rstrip()))
        self.assertNotIn("**Recommended next step:**", trimmed)
        self.assertNotIn("**Ask for observable details:**", trimmed)
        self.assertIn("**Ask for observable details:**", original)
        self.assertNotIn("**Sources used**", trimmed)
        self.assertNotIn("**Gaps in this research**", trimmed)
        for prefix in ("- **Power:**", "- **Knee safety:**", "- The agent should not diagnose"):
            protected = next(line for line in original.splitlines() if line.startswith(prefix))
            self.assertIn(protected, trimmed)
        drills = original.split("## 9. Drills", 1)[1].split("## 10.", 1)[0]
        self.assertIn(drills, trimmed)

    def setUp(self):
        for provider in ("groq", "gemini"):
            replacement = patch(
                f"fencecoach.coach.core_packet.{provider}_circuit", CircuitBreaker()
            )
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_plain_writer_preserves_prose_and_receives_full_files_without_retrieval(self):
        class Model:
            def invoke(self, messages):
                self.messages = messages
                return AIMessage(content="This is the model's full answer, including 1234.")

        request = CoachRequest(session_id="clip", question="my arm in rep 2")
        for provider in ("gemini", "groq"):
            model = Model()
            with (
                patch(
                    "fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())
                ),
                patch(
                    "fencecoach.coach.turn_packet.search_knowledge",
                    side_effect=AssertionError("retrieval forbidden"),
                ),
            ):
                run = run_packet_core(request, provider, model=model)
            self.assertEqual(run.report.summary, "This is the model's full answer, including 1234.")
            self.assertEqual(model.messages[0].content, writer_reference())
            self.assertFalse(run.answer_contract["output_checks"])
            self.assertNotIn("assessments", run.answer_contract["packet"])
            self.assertEqual({r["rep"] for r in run.answer_contract["packet"]["measurements"]}, {2})

    def test_unsupported_measurements_stay_withheld(self):
        request = CoachRequest(
            session_id="clip",
            question="my arm",
            evidence_unavailable_reason="Athlete selection is unresolved.",
        )

        class Model:
            def invoke(self, messages):
                return AIMessage(content="Which athlete should I review?")

        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run = run_packet_core(request, "gemini", model=Model())
        self.assertEqual(run.answer_contract["packet"]["measurements"], [])
        self.assertEqual(run.answer_contract["packet"]["session_comparison"], [])

    def test_blade_gap_keeps_other_session_topics_explicitly_available(self):
        class Model:
            def invoke(self, messages):
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(content="I don't have blade measurements.")

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run_packet_core(
                CoachRequest(session_id="clip", question="my blade control"), "groq", model=model
            )
        availability = model.packet["availability"]
        self.assertIn("blade", availability["requested_statement"])
        self.assertIn("arm extension/direction", availability["available_session_topics"])
        self.assertEqual(model.packet["measurements"], [])
        self.assertIn("only", availability["gap_scope_note"])

    def test_missing_data_packet_does_not_turn_generic_capture_advice_into_a_cause(self):
        request = CoachRequest(
            session_id="clip",
            question="what about my knees and legs?",
            evidence_unavailable_reason="Unsupported. Move the camera farther back.",
        )

        class Model:
            def invoke(self, messages):
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(
                    content="No usable knee measurements; as general guidance, focus on the finish."
                )

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run_packet_core(request, "gemini", model=model)
        self.assertIn(
            "in this session; cause unknown", model.packet["availability"]["requested_statement"]
        )
        self.assertNotIn("Move the camera", json.dumps(model.packet))
        self.assertNotIn("session_missing_topics", model.packet["availability"])
        self.assertEqual(
            model.packet["availability"]["requested_missing_topics"], ["front knee", "rear knee"]
        )
        self.assertEqual(model.packet["availability"]["verified_visibility_observations"], [])

    def test_packet_compacts_repeated_meanings_without_selecting_a_best_rep(self):
        class Model:
            def invoke(self, messages):
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(content="The set spans different degrees of extension.")

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run_packet_core(
                CoachRequest(session_id="clip", question="my arm"), "gemini", model=model
            )
        self.assertIn("weapon_elbow_angle", model.packet["measurement_meanings"])
        self.assertNotIn("session_comparison", model.packet)
        self.assertEqual(
            model.packet["measurements"][0]["rep_readings"],
            {"1": "161.0 deg", "2": "162.0 deg", "5": "165.0 deg"},
        )

    def test_unresolved_subject_is_not_a_missing_measurement_claim(self):
        class Model:
            def invoke(self, messages):
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(content="Do you mean your arm or your rear leg?")

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run_packet_core(
                CoachRequest(session_id="clip", question="is it good?"), "gemini", model=model
            )
        self.assertEqual(model.packet["availability"]["status"], "measurements_available")
        self.assertIsNone(model.packet["availability"]["requested_statement"])
        self.assertEqual(model.packet["availability"]["requested_scope"], "unresolved_subject")
        self.assertTrue(model.packet["measurements"])
        self.assertTrue(model.packet["overview_then_clarify"])
        self.assertEqual(len(model.packet["clarification"]["options"]), 3)

    def test_only_open_evaluations_without_a_topic_get_overview_clarification(self):
        from fencecoach.coach.turn_packet import build_packet, resolve_scope
        from fencecoach.schemas import DialogueState

        for question in (
            "is it good?",
            "how did I do?",
            "what should I improve?",
            "what should I focus on?",
        ):
            request = CoachRequest(session_id="clip", question=question)
            state = resolve_scope(request, snapshot())
            self.assertTrue(
                build_packet(request, state, snapshot(), conversation_only=True)[
                    "overview_then_clarify"
                ]
            )
            request.dialogue_state = DialogueState(
                session_id="clip", core_version="new2", topics=["arm"]
            )
            state = resolve_scope(request, snapshot())
            self.assertEqual(state.topics, ["arm"])
            self.assertFalse(
                build_packet(request, state, snapshot(), conversation_only=True)[
                    "overview_then_clarify"
                ]
            )

        for question in (
            "teach me the Dragonfly triple-hop drill",
            "give me a drill that is",
            "is that in your knowledge base?",
            "did my point drop?",
            "did I push hard?",
            "how is my front knee?",
            "what should I improve about my arm?",
        ):
            request = CoachRequest(session_id="clip", question=question)
            state = resolve_scope(request, snapshot())
            packet = build_packet(request, state, snapshot(), conversation_only=True)
            self.assertFalse(packet["overview_then_clarify"], question)
            self.assertIsNone(packet["clarification"], question)

    def test_topic_switch_exposes_only_current_question_gap(self):
        from fencecoach.coach.turn_packet import build_packet, resolve_scope
        from fencecoach.schemas import ConversationMessage

        for earlier, question, topic in (
            ("my arm", "and my recovery?", "recovery"),
            ("my torso", "and my rear leg?", "rear_leg"),
        ):
            request = CoachRequest(
                session_id="clip",
                question=question,
                conversation_history=[ConversationMessage(role="user", content=earlier)],
            )
            state = resolve_scope(request, snapshot())
            packet = build_packet(request, state, snapshot(), conversation_only=True)
            self.assertEqual(packet["scope"]["topics"], [topic])
            self.assertEqual(packet["current_question"], question)
            self.assertIsNone(packet["availability"]["requested_statement"])
            self.assertEqual(packet["availability"]["requested_missing_topics"], [])
            self.assertIsNone(packet["availability"]["cause"])
            self.assertNotIn("session_missing_topics", packet["availability"])

    def test_unrequested_missing_topic_is_not_a_gap_and_mixed_request_names_only_missing_topic(
        self,
    ):
        from fencecoach.coach.turn_packet import build_packet, resolve_scope

        data = snapshot()
        for rep in data["per_rep_measurements"]:
            rep["measures"].pop("projected_torso_tilt")
        for question, missing in (
            ("my arm", []),
            ("my arm and torso", ["torso"]),
            ("in general my torso", []),
        ):
            request = CoachRequest(session_id="clip", question=question)
            state = resolve_scope(request, data)
            packet = build_packet(request, state, data, conversation_only=True)
            self.assertEqual(packet["availability"]["requested_missing_topics"], missing)
            if missing:
                self.assertIn("for torso", packet["availability"]["requested_statement"])
                self.assertNotIn("arm", packet["availability"]["requested_statement"])
            else:
                self.assertIsNone(packet["availability"]["requested_statement"])

    def test_c01_t4_three_unanswered_questions_never_reach_writer_history(self):
        from fencecoach.schemas import ConversationMessage

        unanswered = ["how's my arm extension?", "is it good?", "what should I change?"]
        request = CoachRequest(
            session_id="clip",
            question="and my recovery?",
            conversation_history=[ConversationMessage(role="user", content=q) for q in unanswered],
        )
        stored = request.model_dump(mode="json")["conversation_history"]

        class Model:
            def invoke(self, messages):
                self.messages = messages
                return AIMessage(content="Recovery reply.")

        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run = run_packet_core(request, "gemini", model=model)
        self.assertEqual(
            [m.content for m in model.messages if m.type == "human"], [request.question]
        )
        self.assertEqual([m for m in model.messages if m.type == "ai"], [])
        self.assertEqual(request.model_dump(mode="json")["conversation_history"], stored)
        trace = json.loads(run.trace[0].detail)
        self.assertEqual(trace["history"], [])
        self.assertEqual(trace["stored_conversation_history"], stored)
        self.assertEqual(run.answer_contract["packet"]["current_question"], "and my recovery?")

    def test_history_keeps_completed_pairs_and_never_orphans_a_question(self):
        from fencecoach.coach.core_packet import recent_chat
        from fencecoach.schemas import ConversationMessage, DialogueState

        messages = [
            ("user", "unanswered before"),
            ("user", "answered question"),
            ("assistant", "stored reply"),
            ("user", "empty reply question"),
            ("assistant", "   "),
            ("user", "unanswered after"),
        ]
        request = CoachRequest(
            session_id="clip",
            question="current question",
            conversation_history=[ConversationMessage(role=r, content=c) for r, c in messages],
        )
        state = DialogueState(session_id="clip", core_version="new2", turns_completed=1)
        history = recent_chat(request, state)
        self.assertEqual(
            [(m.type, m.content) for m in history],
            [("human", "answered question"), ("ai", "stored reply")],
        )
        self.assertEqual(recent_chat(request, state, limit=5), [])

    def test_restart_then_broad_question_keeps_session_measurements_and_excludes_old_chat(self):
        from fencecoach.schemas import ConversationMessage

        class Model:
            def invoke(self, messages):
                self.messages = messages
                self.packet = json.loads(messages[1].content.split("\n", 1)[1])
                return AIMessage(content="The session has a range of extension readings.")

        request = CoachRequest(
            session_id="clip",
            question="what should I improve?",
            conversation_history=[
                ConversationMessage(role="user", content="my arm in rep 2"),
                ConversationMessage(role="user", content="start over"),
            ],
        )
        model = Model()
        with patch("fencecoach.coach.core_packet._snapshot", return_value=json.dumps(snapshot())):
            run_packet_core(request, "groq", model=model)
        self.assertEqual(model.packet["scope"]["topics"], [])
        self.assertTrue(model.packet["overview_then_clarify"])
        self.assertTrue(model.packet["measurements"])
        self.assertNotIn("my arm in rep 2", str(model.messages))
        self.assertIsNone(model.packet["availability"]["requested_statement"])

    def test_groq_retry_after_cools_primary_and_gemini_answers_with_same_context(self):
        import fencecoach.coach.core_packet as core

        class Model:
            def __init__(self, fail=False):
                self.fail, self.calls = fail, []

            def invoke(self, messages):
                self.calls.append(messages)
                if self.fail:
                    raise HostedError(429, "limited", retry_after=120)
                return AIMessage(content="Your rear leg is consistent with the straight-leg cue.")

        primary, fallback = Model(True), Model()
        request = CoachRequest(session_id="clip", question="my rear leg")
        with (
            patch.object(core, "_snapshot", return_value=json.dumps(snapshot())),
            patch.object(core, "HostedFallback", return_value=primary),
            patch.object(core, "chat_model", return_value=fallback),
        ):
            first = run_packet_core(request, "gemini")
            request.dialogue_state = first.dialogue_state
            request.question = "why?"
            second = run_packet_core(request, "gemini")
        self.assertEqual(first.mode, "gemini")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(fallback.calls), 2)
        self.assertIn("groq:cooldown:rate_limit", second.fallback_reason)
        self.assertGreaterEqual(
            first.answer_contract["provider_attempts"][0]["retry_after_seconds"], 120
        )
        self.assertEqual(primary.calls[0], fallback.calls[0])
        self.assertEqual(second.dialogue_state.topics, ["rear_leg"])

    def test_both_provider_failures_get_only_the_connection_message(self):
        with (
            patch("fencecoach.coach.core_packet.chat_model", side_effect=TimeoutError),
            patch("fencecoach.coach.core_packet.HostedFallback", side_effect=TimeoutError),
        ):
            run = run_packet_core(CoachRequest(session_id="clip", question="hello"), "gemini")
        self.assertEqual(run.report.summary, "I couldn't reach the model, try again shortly.")
        self.assertEqual(
            [r["provider"] for r in run.answer_contract["provider_attempts"]], ["groq", "gemini"]
        )


if __name__ == "__main__":
    unittest.main()

"""Contract, continuity and routing regressions using saved session measurements."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk

from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.dialogue_state import resolve_turn
from fencecoach.coach.evidence_packet import build_packet, verify_rendered
from fencecoach.coach.providers import provider_failure
from fencecoach.coach.router import CircuitBreaker, ProvidersUnavailable, failure_reason, route
from fencecoach.coach.verified_dialogue import run_verified_conversation
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState

FIXTURES = Path(__file__).resolve().parents[1] / "evals/coach_audit"


def fixture(name="current", question="How is my arm extension?"):
    data = CoachRequest.model_validate_json((FIXTURES / (name + ".json")).read_text())
    return data.model_copy(update={"question": question})


class Selector:
    def stream(self, messages):
        for unit in json.loads(messages[-1].content)["units"]:
            yield AIMessageChunk(content=unit["id"] + "\n")


class Malicious:
    def invoke(self, messages):
        return AIMessage(content="Your arm is 37 degrees. Do 99 invented drills to fix it.")


class VerifiedDialogueTests(unittest.TestCase):
    def test_production_entry_uses_verified_dialogue(self):
        run = run_conversation(fixture(), "local", model=Selector())
        self.assertTrue(run.answer_contract)
        self.assertIsNotNone(run.dialogue_state)

    def test_explicit_duration_does_not_get_a_knee_angle(self):
        packet = build_packet(fixture(question="How long was my active recovery?"))
        observations = [u for u in packet.units if u.kind == "observation"]
        self.assertTrue(observations)
        self.assertEqual(observations[0].records[0]["feature"], "estimated_active_recovery_time")

    def test_multiple_rep_request_covers_each_rep(self):
        packet = build_packet(fixture(question="How was my arm extension in reps 1 and 2?"))
        self.assertEqual(
            {r["rep"] for u in packet.units for r in u.records if r.get("feature")}, {1, 2}
        )

    def test_multiple_arm_roles_keep_separate_measurements(self):
        packet = build_packet(fixture(question="How were my sword arm and non-sword arm?"))
        features = {r["feature"] for u in packet.units for r in u.records if r.get("feature")}
        self.assertTrue(any(f.startswith("weapon_") for f in features))
        self.assertTrue(any(f.startswith("non_weapon_") for f in features))

    def test_multiple_followups_retain_subject_and_rep(self):
        request = fixture()
        state = None
        for question in [
            "How is my arm extension?",
            "Is it good?",
            "What should I change?",
            "What about the third rep?",
            "Why does that matter?",
        ]:
            request.question, request.dialogue_state = question, state
            resolved, state = resolve_turn(request)
            self.assertIn("arm", state.topics)
        self.assertEqual(state.rep_numbers, [3])
        self.assertIn("rep 3", resolved)
        request.question, request.dialogue_state = "And my recovery?", state
        resolved, state = resolve_turn(request)
        self.assertEqual(state.topics, ["recovery"])
        self.assertNotIn("arm", resolved)

    def test_session_boundary_discards_state(self):
        first = run_verified_conversation(fixture(), "local", model=Selector())
        request = fixture(question="Why?")
        request.session_id = "another-session"
        request.dialogue_state = first.dialogue_state
        _, state = resolve_turn(request)
        self.assertEqual(state.topics, [])

    def test_incomplete_snapshot_is_rebuilt_from_recent_user_turns(self):
        request = fixture(question="How was my front leg?")
        request.conversation_history = [
            ConversationMessage(role="user", content="How was my front leg?"),
            ConversationMessage(
                role="assistant", content="Your front-knee angle was higher than the reference."
            ),
            ConversationMessage(role="user", content="How should I practice then?"),
        ]
        request.dialogue_state = DialogueState(
            session_id=request.session_id,
            subject="my front leg",
            topics=[],
            last_cited_evidence=[],
        )
        request.question = "How can I improve?"
        resolved, state = resolve_turn(request)
        self.assertIn("front_leg", state.topics)
        self.assertIn("front leg", resolved)

    def test_general_subject_becomes_personal_without_stale_scope_instruction(self):
        request = fixture(question="In general, how should I extend my non-sword arm?")
        _, general = resolve_turn(request)
        self.assertEqual(general.scope, "general")
        for followup in ("How was mine?", "What about mine?", "What about the third rep?"):
            with self.subTest(followup=followup):
                request.question, request.dialogue_state = followup, general
                resolved, state = resolve_turn(request)
                self.assertEqual(state.scope, "session")
                self.assertIn("non-sword arm", resolved)
                self.assertNotIn("in general", resolved.lower())
                self.assertEqual(state.arm_roles, ["non_weapon"])
                if "third" in followup:
                    self.assertEqual(state.rep_numbers, [3])

    def test_neutral_followup_preserves_explicit_general_scope(self):
        request = fixture(question="In general, how should I extend my sword arm?")
        _, state = resolve_turn(request)
        request.question, request.dialogue_state = "Why does that matter?", state
        resolved, state = resolve_turn(request)
        self.assertEqual(state.scope, "general")
        self.assertIn("sword arm", resolved)

    def test_phase_qualifier_followup_replaces_phase_and_preserves_role_and_rep(self):
        request = fixture(question="How was my non-sword arm at starting guard in rep 2?")
        _, state = resolve_turn(request)
        for followup, expected in (
            ("What about it at the recovery peak?", "recovery_peak"),
            ("And at the lunge finish?", "lunge_finish"),
        ):
            request.question, request.dialogue_state = followup, state
            resolved, state = resolve_turn(request)
            self.assertIn("non-sword arm", resolved)
            self.assertEqual(state.arm_roles, ["non_weapon"])
            self.assertEqual(state.rep_numbers, [2])
            self.assertIn(expected, state.phases)
            self.assertNotIn("starting_guard", state.phases)
        request.question, request.dialogue_state = "And my active recovery?", state
        resolved, state = resolve_turn(request)
        self.assertEqual(state.topics, ["recovery"])
        self.assertNotIn("arm", resolved)

    def test_personal_history_followup_preserves_subject_and_history_scope(self):
        request = fixture()
        _, state = resolve_turn(request)
        request.question, request.dialogue_state = "What about mine in the previous session?", state
        resolved, state = resolve_turn(request)
        self.assertIn("arm extension", resolved)
        self.assertEqual(state.scope, "history")

    def test_model_cannot_add_any_prose_numbers_or_drills(self):
        for provider in ("local", "gemini"):
            published = []
            run = run_verified_conversation(
                fixture(), provider, model=Malicious(), on_text=published.append
            )
            self.assertNotIn("37 degrees", run.report.summary)
            self.assertNotIn("99", run.report.summary)
            self.assertTrue(run.answer_contract["provider_contract_rejected"])
            self.assertEqual(published[-1], run.report.summary)
            self.assertTrue(run.citation_ids_valid)

    def test_validated_units_stream_before_model_finishes(self):
        emitted = []

        class Streaming:
            def stream(self, messages):
                for unit in json.loads(messages[-1].content)["units"]:
                    yield AIMessageChunk(content=unit["id"] + "\n")
                    if unit["id"] == "fact0":
                        self_test.assertTrue(emitted)

        self_test = self
        run = run_verified_conversation(
            fixture(), "local", model=Streaming(), on_text=emitted.append
        )
        self.assertEqual(emitted[-1], run.report.summary)
        self.assertIsNotNone(run.first_token_ms)
        self.assertLessEqual(run.first_visible_ms, run.latency_ms)

    def test_rejected_and_low_confidence_footage_do_not_become_facts(self):
        for name in ("unsupported", "low_confidence"):
            req = fixture(name, "How is my recovery?")
            packet = build_packet(req)
            self.assertFalse(packet.has_measurements)
            self.assertFalse(any(u.kind == "observation" for u in packet.units))

    def test_unknown_feature_does_not_get_unrelated_session_data(self):
        packet = build_packet(fixture(question="How was my blade control?"))
        self.assertFalse(packet.has_measurements)
        self.assertFalse(any(u.kind == "observation" for u in packet.units))
        self.assertTrue(packet.has_library)
        self.assertFalse(packet.content_fallback)
        self.assertIn("don't track the blade", " ".join(u.text for u in packet.units))

    def test_named_drill_requires_the_named_technique_in_the_library(self):
        packet = build_packet(fixture(question="Give me a moonwalk parry drill from the library."))
        self.assertFalse(packet.has_library)
        self.assertTrue(packet.content_fallback)

    def test_nonexistent_rep_does_not_silently_select_first(self):
        packet = build_packet(fixture(question="How is my arm extension in rep 999?"))
        self.assertFalse(packet.has_measurements)

    def test_reference_comparison_does_not_reverse_difference(self):
        packet = build_packet(fixture(question="How was my recovery?"))
        for unit in packet.units:
            for record in unit.records:
                ref = record.get("reference_range")
                if ref and unit.kind == "observation":
                    inside = min(ref) <= record["value"] <= max(ref)
                    self.assertEqual("matched the reference range" in unit.text, inside)

    def test_verifier_rejects_numeric_attribution_and_advice_edits(self):
        packet = build_packet(fixture())
        text = " ".join(u.text for u in packet.units)
        self.assertTrue(verify_rendered(text, packet.units))
        self.assertFalse(verify_rendered(text.replace("sword elbow", "front knee"), packet.units))
        self.assertFalse(verify_rendered(text + " Try a new drill.", packet.units))

    def test_state_roundtrip_in_run_json(self):
        run = run_verified_conversation(fixture(), "local", model=Selector())
        restored = type(run).model_validate_json(run.model_dump_json())
        self.assertEqual(restored.dialogue_state, run.dialogue_state)


class RouterTests(unittest.TestCase):
    @staticmethod
    def error(status, retry=None):
        response = httpx.Response(
            status,
            headers={"Retry-After": retry} if retry else {},
            request=httpx.Request("POST", "https://example.invalid"),
        )
        return httpx.HTTPStatusError(
            "forced test error", request=response.request, response=response
        )

    def test_forced_429_between_turns_preserves_state_and_exits_cooldown(self):
        now = [1.0]
        breaker = CircuitBreaker(lambda: now[0])
        called = []
        state = None
        with patch(
            "fencecoach.coach.verified_dialogue.route",
            side_effect=lambda op, mode: route(op, mode, breaker=breaker),
        ):
            for i, question in enumerate(
                [
                    "How is my torso?",
                    "And my arm extension?",
                    "Is it good?",
                    "Why?",
                    "What should I change?",
                ]
            ):
                if i == 4:
                    now[0] = 122

                def factory(provider, index=i):
                    called.append((index, provider))
                    if index == 2 and provider == "gemini":
                        raise self.error(429, "120")
                    return Selector()

                req = fixture(question=question)
                req.dialogue_state = state
                with patch("fencecoach.coach.verified_dialogue.chat_model", side_effect=factory):
                    run = run_verified_conversation(req, "gemini")
                state = run.dialogue_state
                if i >= 1:
                    self.assertIn("arm", state.topics)
                if i == 2:
                    self.assertEqual(run.fallback_reason, "rate_limit")
                if i == 3:
                    self.assertEqual(run.fallback_reason, "cooldown:rate_limit")
            self.assertNotIn((3, "gemini"), called)
            self.assertIn((4, "gemini"), called)
            self.assertEqual(breaker.until, 0)

    def test_request_errors_do_not_fallback(self):
        for status in (400, 401, 403, 404, 422):
            calls = []

            def fail(provider):
                calls.append(provider)
                raise self.error(status)

            with self.assertRaises(httpx.HTTPStatusError):
                route(fail, "gemini", breaker=CircuitBreaker())
            self.assertEqual(calls, ["gemini"])

    def test_timeout_and_unavailable_routes_are_bounded(self):
        self.assertEqual(failure_reason(TimeoutError()), "timeout")
        calls = []

        def fail(provider):
            calls.append(provider)
            raise TimeoutError()

        with self.assertRaises(ProvidersUnavailable):
            route(fail, "gemini", breaker=CircuitBreaker())
        self.assertEqual(calls, ["gemini", "local"])

    def test_double_provider_failure_keeps_safe_cause_for_the_user(self):
        def fail(provider):
            if provider == "gemini":
                raise self.error(429)
            raise RuntimeError("local model is not ready")

        with self.assertRaises(ProvidersUnavailable) as caught:
            route(fail, "gemini", breaker=CircuitBreaker())
        status, message = provider_failure(caught.exception)
        self.assertEqual(status, 503)
        self.assertIn("usage limit", message)
        self.assertIn("local coach isn't ready", message)

    def test_sdk_status_codes_are_normalized_for_user_errors(self):
        class QuotaException(Exception):
            def code(self):
                return 429

        status, message = provider_failure(QuotaException())
        self.assertEqual(status, 429)
        self.assertIn("usage limit", message)

    def test_only_one_half_open_probe(self):
        clock = [0]
        circuit = CircuitBreaker(lambda: clock[0])
        circuit.failure("rate_limit", 5)
        clock[0] = 6
        self.assertTrue(circuit.acquire()[0])
        self.assertFalse(circuit.acquire()[0])
        circuit.success()
        self.assertTrue(circuit.acquire()[0])

    def test_older_success_does_not_clear_a_newer_rate_limit(self):
        now = [0]
        breaker = CircuitBreaker(lambda: now[0])
        _, _, first_lease = breaker.acquire_lease()
        breaker.failure("rate_limit", 120)
        breaker.success(first_lease)
        self.assertFalse(breaker.acquire()[0])
        now[0] = 121
        _, _, probe_lease = breaker.acquire_lease()
        breaker.success(first_lease)
        self.assertTrue(breaker.probing)
        breaker.success(probe_lease)
        self.assertEqual(breaker.until, 0)


if __name__ == "__main__":
    unittest.main()

import asyncio
import time
import unittest
from unittest.mock import patch

from pydantic import SecretStr

from fencecoach.coach.core_packet import recent_chat
from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.packet_meaning import assessments, describe
from fencecoach.coach.semantic_scope import resolve_semantic_scope
from fencecoach.coach.turn_packet import _previous_comparison, resolve_scope
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState
from fencecoach.settings import settings
from tests.test_packet_core import snapshot


class RelativeAssessmentTests(unittest.TestCase):
    def test_semantic_fallback_is_shared_and_cannot_invent_scope_keys(self):
        request = CoachRequest(session_id="clip", question="that bit at the end")
        # This helper accepts low-confidence state; the current deterministic
        # resolver does not produce that state for this phrase. Test the helper's
        # contract explicitly, without claiming it is in the app's writer path.
        state = DialogueState(
            session_id="clip",
            resolution_confidence="low",
            open_clarifying_question={"question": "Which part?", "options": []},
        )
        with (
            patch.object(settings, "groq_api_key", SecretStr("test-only-placeholder")),
            patch.object(
                HostedFallback, "invoke", side_effect=AssertionError("live call forbidden")
            ),
            patch(
                "fencecoach.coach.semantic_scope._lookup",
                return_value={"topics": ["arm"], "phases": ["lunge_finish"], "confidence": "high"},
            ) as lookup,
        ):
            resolved, trace = resolve_semantic_scope(request, state)
        lookup.assert_called_once_with(request.question, state.current_topic)
        self.assertEqual(resolved.topics, ["arm"])
        self.assertEqual(trace["status"], "resolved")
        with (
            patch.object(settings, "groq_api_key", SecretStr("test-only-placeholder")),
            patch.object(
                HostedFallback, "invoke", side_effect=AssertionError("live call forbidden")
            ),
            patch(
                "fencecoach.coach.semantic_scope._lookup",
                return_value={"topics": ["imaginary_metric"], "confidence": "high"},
            ),
        ):
            unresolved, _ = resolve_semantic_scope(request, state)
        self.assertIsNotNone(unresolved.open_clarifying_question)

    def test_hosted_request_has_a_total_deadline(self):
        async def slow(messages):
            await asyncio.sleep(1)

        # Substitute a short deadline while retaining the actual timeout context.
        original_timeout = asyncio.timeout
        started = time.perf_counter()
        with (
            patch.object(HostedFallback, "_request", side_effect=slow),
            patch(
                "fencecoach.coach.hosted_fallback.asyncio.timeout",
                side_effect=lambda seconds: original_timeout(0.01),
            ),
            self.assertRaises(TimeoutError),
        ):
            HostedFallback().invoke([])
        self.assertLess(time.perf_counter() - started, 0.3)

    def test_option_order_is_user_order_and_not_rep_number(self):
        request = CoachRequest(session_id="clip", question="my arm or my recovery?")
        state = resolve_scope(request, snapshot())
        self.assertEqual(
            [o["topics"] for o in state.open_clarifying_question["options"]],
            [["arm"], ["recovery"]],
        )
        request.question, request.dialogue_state = "the second option", state
        state = resolve_scope(request, snapshot())
        self.assertEqual(state.topics, ["recovery"])
        self.assertEqual(state.rep_numbers, [])

    def test_return_instruction_and_reset_history_boundary(self):
        request = CoachRequest(session_id="clip", question="my arm at recovery peak")
        state = resolve_scope(request, snapshot())
        request.question, request.dialogue_state = "back to the finish", state
        state = resolve_scope(request, snapshot())
        self.assertEqual(state.topics, ["arm"])
        self.assertEqual(state.phases, ["lunge_finish"])
        request.conversation_history = [ConversationMessage(role="user", content="my rear leg")]
        request.question, request.dialogue_state = "start over", state
        state = resolve_scope(request, snapshot())
        self.assertEqual(recent_chat(request, state), [])
        request.question, request.dialogue_state = "is it good?", state
        state = resolve_scope(request, snapshot())
        self.assertEqual(state.topics, [])
        self.assertIsNotNone(state.open_clarifying_question)

    def test_capture_mismatch_never_compares_previous_values(self):
        request = CoachRequest(
            session_id="clip",
            question="my arm",
            session_history=[
                dict(
                    session_id="old",
                    date="2026-10-13",
                    capture_profile={"camera_setup_id": "different"},
                    metrics=[],
                )
            ],
        )
        state = resolve_scope(request, snapshot())
        with patch(
            "fencecoach.coach.turn_packet.build_packet",
            side_effect=AssertionError("must not fetch mismatched history"),
        ):
            self.assertEqual(_previous_comparison(request, state)["status"], "not_comparable")

    def test_relative_spread_is_geometry_not_a_correctness_threshold(self):
        rows = [
            describe(
                dict(
                    topic="rear_leg",
                    feature="rear_knee_angle",
                    phase="lunge_finish",
                    unit="deg",
                    value=v,
                    rep=r,
                    evidence_id=f"rep:{r}",
                )
            )
            for r, v in [(1, 160.1), (2, 171.3), (3, 168.4)]
        ]
        result = assessments(
            ["rear_leg"], rows, [dict(source_id="cue", text="Rear leg extended.")]
        )[0]
        relative = result["relative"][0]
        self.assertEqual(result["status"], "relative_only")
        self.assertEqual(relative["spread"], "11.2 deg")
        self.assertEqual(relative["best"]["rep"], 2)
        self.assertEqual(relative["worst"]["rep"], 1)
        self.assertEqual(relative["previous_session"]["status"], "not_comparable")
        self.assertIn("not technique quality", relative["meaning"])

    def test_direction_without_a_known_target_does_not_rank_best(self):
        row = describe(
            dict(
                topic="arm",
                feature="weapon_arm_direction",
                value=18.153,
                unit="deg",
                phase="lunge_finish",
                rep=1,
                evidence_id="arm",
            )
        )
        assessment = assessments(["arm"], [row], [])[0]
        self.assertIsNone(assessment["relative"][0]["best"])
        self.assertEqual(assessment["measured"][0]["display"], "18.2 deg")


if __name__ == "__main__":
    unittest.main()

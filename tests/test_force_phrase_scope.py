"""Narrow force-question resolution; no provider calls or model-quality claims."""

import unittest

from fencecoach.coach.turn_packet import build_packet, resolve_scope
from fencecoach.schemas import CoachRequest
from tests.test_packet_core import snapshot


class ForcePhraseScopeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()

    def resolve(self, question, state=None):
        request = CoachRequest(session_id="clip", question=question, dialogue_state=state)
        return request, resolve_scope(request, self.snapshot)

    def assert_force_packet(self, request, state):
        self.assertEqual(state.topics, ["force"])
        self.assertNotIn("blade", state.topics)
        packet = build_packet(request, state, self.snapshot, conversation_only=True)
        self.assertEqual(packet["measurements"], [])
        self.assertEqual(packet["availability"]["requested_missing_topics"], ["force"])
        self.assertIn("force", packet["availability"]["requested_statement"].lower())

    def test_push_hard_replaces_blade_and_names_force_gap(self):
        _, blade = self.resolve("was my blade control good?")
        request, force = self.resolve("did I push hard?", blade)
        self.assert_force_packet(request, force)

    def test_push_hard_as_first_question_names_force_gap(self):
        request, force = self.resolve("did I push hard?")
        self.assert_force_packet(request, force)

    def test_approved_force_phrasings(self):
        for question in (
            "push hard",
            "how hard did I push?",
            "did I drive?",
            "how much power?",
            "how strong was my push?",
            "did I push hard on the second rep?",
        ):
            with self.subTest(question=question):
                request, force = self.resolve(question)
                self.assert_force_packet(request, force)

    def test_existing_topics_unchanged(self):
        for question, topic in (
            ("was my blade control good?", "blade"),
            ("my arm", "arm"),
            ("my rear leg", "rear_leg"),
            ("my torso", "torso"),
            ("my recovery", "recovery"),
        ):
            with self.subTest(question=question):
                _, state = self.resolve(question)
                self.assertEqual(state.topics, [topic])

    def test_neutral_push_foot_does_not_trigger_force(self):
        _, rear_leg = self.resolve("my rear leg")
        for question in ("my push foot", "my push foot position", "my push foot on rep 2"):
            with self.subTest(question=question):
                _, first = self.resolve(question)
                self.assertNotIn("force", first.topics)
                _, followup = self.resolve(question, rear_leg)
                self.assertEqual(followup.topics, ["rear_leg"])


if __name__ == "__main__":
    unittest.main()

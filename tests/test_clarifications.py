import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk

from fencecoach.coach.conversation import CoachAnswerError
from fencecoach.coach.graph import run_coach
from fencecoach.coach.turns import conversation_issues, general_guidance_query
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings

BAD = "For a lunge, extend your arm to the side, about shoulder-width apart from the body. This position helps in maintaining balance and allows for a smooth transition into the next stroke."


def question(text):
    return CoachRequest(
        session_id="clarification",
        question=text,
        conversation_history=[
            ConversationMessage(role="user", content="Explain the arm in a lunge"),
            ConversationMessage(role="assistant", content=BAD),
        ],
    )


class RepeatingModel:
    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        return AIMessage(content=BAD)


# The legacy writer rejects unsupported drafts; it no longer substitutes canned prose.
@patch.object(settings, "coach_core", "old")
@patch.object(settings, "fencecoach_verified_dialogue", False)
class ClarificationTests(unittest.TestCase):
    def test_identical_reply_is_rejected_and_arm_role_is_required(self):
        self.assertTrue(conversation_issues(question("which arm"), BAD))
        self.assertTrue(
            conversation_issues(question("which arm"), "It extends forward toward the target.")
        )
        self.assertFalse(
            conversation_issues(
                question("which arm"),
                "The sword arm, holding your weapon, reaches toward the target. My earlier sideways instruction was wrong.",
            )
        )

    def test_known_wrong_reply_is_rejected_without_a_canned_replacement(self):
        for text in (
            "can you describe better",
            "which arm",
            "which arm, sword arm or non-sword arm",
        ):
            with self.subTest(text=text), self.assertRaises(CoachAnswerError):
                run_coach(question(text), "local", model=RepeatingModel())

    def test_wrong_draft_is_not_published_while_streaming(self):
        class Stream(RepeatingModel):
            def stream(self, messages):
                yield AIMessageChunk(content=BAD)

        published = []
        with self.assertRaises(CoachAnswerError):
            run_coach(question("which arm"), "local", model=Stream(), on_text=published.append)
        self.assertEqual(published, [])

    def test_new_topic_does_not_retrieve_old_arm_instruction(self):
        query = general_guidance_query(question("What is recovery in fencing?"))
        self.assertNotIn("sword", query)
        self.assertIn("recovery", query)


if __name__ == "__main__":
    unittest.main()

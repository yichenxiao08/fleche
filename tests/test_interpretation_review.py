"""Correct numbers must not override a reviewer's unsupported-inference finding."""

import unittest
from unittest.mock import patch

from fencecoach.coach.answer_review import AnswerDraft, AnswerReview, review_issues
from fencecoach.coach.conversation import CoachAnswerError, run_conversation
from fencecoach.settings import settings
from tests.test_coach_response_reliability import StructuredModel, request


@patch.object(settings, "coach_core", "old")
class InterpretationReviewTests(unittest.TestCase):
    def test_grounded_numbers_do_not_override_unsupported_interpretation(self):
        for inference in (
            "a single sample establishes the whole action",
            "one measured attempt establishes consistency across attempts",
            "a reference difference establishes a causal fault",
        ):
            with self.subTest(inference=inference):
                review = AnswerReview(
                    addresses_question=True,
                    grounded=True,
                    uses_session_evidence=False,
                    unsupported_inferences=[inference],
                )
                issues = review_issues(review, {})
                self.assertTrue(any(inference in issue for issue in issues))

    def test_failed_interpretation_review_never_publishes_the_draft(self):
        review = AnswerReview(
            addresses_question=True,
            grounded=True,
            uses_session_evidence=False,
            unsupported_inferences=["a sampled position establishes an unmeasured outcome"],
        )
        draft = AnswerDraft(answer="The sampled position guarantees a successful next action.")
        published = []
        with self.assertRaises(CoachAnswerError):
            run_conversation(
                request("In general, what can a single measurement tell me?"),
                "gemini",
                model=StructuredModel(draft, review),
                on_text=published.append,
            )
        self.assertEqual(published, [])


if __name__ == "__main__":
    unittest.main()

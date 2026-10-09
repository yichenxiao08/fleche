import unittest

from fencecoach.benchmarks import draft_agreement, render_report


class BenchmarkTests(unittest.TestCase):
    def test_disagreement_is_uncertain(self):
        result = {
            "candidates": [{"candidate_id": "rep-1", "start_ms": 1000, "movement_label": "lunge"}],
            "gestures": [{"start_ms": 900, "end_ms": 1100, "label": "advance"}],
        }
        check = draft_agreement(result)
        self.assertEqual(check["compared"], 1)
        self.assertEqual(len(check["disagreements"]), 1)
        self.assertIn("never auto-accepted", check["note"])

    def test_missing_scores_are_not_success(self):
        report = render_report({})
        self.assertIn("not_run", report)
        self.assertIn("not measured", report)

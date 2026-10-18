import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_fewshot_v5_quota_review as review


class QuotaReviewTests(unittest.TestCase):
    def test_midnight_pacific_is_not_midnight_utc(self):
        now = datetime(2026, 10, 16, 23, tzinfo=UTC)
        self.assertEqual(
            datetime.fromtimestamp(review.next_daily_reset("gemini", now), UTC),
            datetime(2026, 10, 17, 7, tzinfo=UTC),
        )

    def test_winter_reset_observes_standard_time(self):
        now = datetime(2026, 12, 16, 23, tzinfo=UTC)
        self.assertEqual(
            datetime.fromtimestamp(review.next_daily_reset("gemini", now), UTC),
            datetime(2026, 12, 17, 8, tzinfo=UTC),
        )

    def test_pacific_boundary_has_distinct_daily_counts(self):
        # Saved Oct16 UTC attempts happened Oct15 Pacific, before 07:00 UTC.
        now = datetime(2026, 10, 16, 23, tzinfo=UTC)
        root = MagicMock()
        root.glob.return_value = []
        folder = root.__truediv__.return_value.__truediv__.return_value
        folder.glob.return_value = [MagicMock()]
        record = {"started_at": datetime(2026, 10, 16, 6, tzinfo=UTC).timestamp()}
        with (
            patch.object(review, "LEGACY", root),
            patch.object(review.json, "loads", return_value=record),
        ):
            self.assertEqual(review.daily_attempts("gemini", now), 0)

    def test_text_retry_duration(self):
        error = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 3h27m53.943387422s.")
        self.assertAlmostEqual(review.provider_retry_delay(error), 12473.943387422)
        self.assertAlmostEqual(review.error_resume_after("gemini", error, 100), 12573.943387422)

    def test_retry_info_has_precedence(self):
        error = RuntimeError("429 {'retryDelay': '12.5s'} Please retry in 60s")
        self.assertEqual(review.error_resume_after("gemini", error, 100), 112.5)

    def test_explicit_quota_vs_outage_without_hint(self):
        stamp = datetime(2026, 10, 16, 23, tzinfo=UTC).timestamp()
        self.assertEqual(
            review.error_resume_after(
                "gemini",
                RuntimeError("429 GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
                stamp,
            ),
            datetime(2026, 10, 17, 7, tzinfo=UTC).timestamp(),
        )
        self.assertEqual(
            review.error_resume_after("gemini", RuntimeError("503 UNAVAILABLE"), stamp), stamp + 65
        )

    def test_propagated_local_cap_recomputed_not_provider_bypassed(self):
        cap = review.LEGACY / "fewshot-v4-frozen-pass/gemini/status.json"
        with patch.object(review, "daily_attempts", return_value=0):
            self.assertEqual(review.saved_resume_after("gemini", cap), 0)
        with patch.object(review, "daily_attempts", return_value=20):
            self.assertGreater(review.saved_resume_after("gemini", cap), 0)


if __name__ == "__main__":
    unittest.main()

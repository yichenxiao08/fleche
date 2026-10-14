"""Cache invalidation fixtures use metadata and abstentions, never athlete measurements."""

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fencecoach.coaching_evidence_cache import CACHE_FILENAME, coaching_evaluation
from fencecoach.reference_comparison import attach_reference_comparisons


class EvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="coaching-evidence-", dir=Path(__file__).parent
        )
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.job = {
            "job_id": "athlete",
            "reviewed_windows": [{"onset_ms": 0, "start_ms": 100, "end_ms": 200}],
            "capture_profile": {},
        }
        self.jobs = {"athlete": self.job}
        self.source = {
            "width": 720,
            "height": 720,
            "frames": [],
            "candidates": [],
            "quality_gate": {"coaching_allowed": True, "issues": []},
            "source_marker": "before",
        }
        self.write_result("athlete", self.source)
        self.reviews = []
        self.feedback = {}
        self.profile = {}

    def write_result(self, job_id, value):
        directory = self.directory / job_id
        directory.mkdir(exist_ok=True)
        (directory / "result.json").write_text(json.dumps(value), encoding="utf-8")

    def evaluation(self):
        # Fresh adapters model separate requests/processes; no Python object cache.
        repository = SimpleNamespace(list_reference_reviews=lambda: deepcopy(self.reviews))
        jobs = SimpleNamespace(get=lambda job_id: deepcopy(self.jobs.get(job_id)))
        return coaching_evaluation(
            "athlete", self.profile, self.feedback, self.directory, repository, jobs
        )

    def fake_evaluation(self, result, windows, profile):
        return {"status": "unavailable", "reps": [], "source_marker": result["source_marker"]}

    def test_persists_and_reuses_without_recomputing_geometry_or_comparisons(self):
        with (
            patch("fencecoach.coaching_evidence_cache.evaluate_lunges", self.fake_evaluation),
            patch(
                "fencecoach.coaching_evidence_cache.attach_reference_comparisons",
                side_effect=lambda evaluation, *args: evaluation,
            ) as compare,
        ):
            first = self.evaluation()
            self.assertTrue((self.directory / "athlete" / CACHE_FILENAME).is_file())
            first["source_marker"] = "mutated by caller"
            with patch("fencecoach.coaching_evidence_cache.evaluate_lunges") as evaluate:
                second = self.evaluation()
                evaluate.assert_not_called()
            self.assertEqual(second["source_marker"], "before")
            compare.assert_called_once()

    def test_result_hash_invalidates_even_when_size_and_mtime_are_unchanged(self):
        path = self.directory / "athlete" / "result.json"
        with patch(
            "fencecoach.coaching_evidence_cache.evaluate_lunges", side_effect=self.fake_evaluation
        ) as evaluate:
            self.evaluation()
            previous = path.stat()
            self.source["source_marker"] = "change"
            self.write_result("athlete", self.source)
            os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            self.assertEqual(path.stat().st_size, previous.st_size)
            self.assertEqual(self.evaluation()["source_marker"], "change")
            self.assertEqual(evaluate.call_count, 2)

    def test_mtime_windows_profile_review_content_revision_and_code_invalidate(self):
        with patch(
            "fencecoach.coaching_evidence_cache.evaluate_lunges", side_effect=self.fake_evaluation
        ) as evaluate:
            self.evaluation()
            path = self.directory / "athlete" / "result.json"
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            self.evaluation()
            self.job["reviewed_windows"][0]["start_ms"] = 110
            self.evaluation()
            self.profile["weapon_arm"] = "left"
            self.evaluation()
            self.feedback = {
                "status": "submitted",
                "revision": 1,
                "reps": [{"rep_number": 1, "lunge_ms": 120}],
            }
            self.evaluation()
            self.assertEqual(evaluate.call_args.args[1][0]["start_ms"], 120)
            self.feedback["revision"] = 2
            self.evaluation()
            self.feedback["reps"][0]["main_issue"] = "Review text updated"
            self.evaluation()
            with patch(
                "fencecoach.coaching_evidence_cache._implementation_fingerprint",
                return_value={"version": "changed"},
            ):
                self.evaluation()
            self.assertEqual(evaluate.call_count, 8)

    def test_reference_revision_result_profile_windows_and_removal_invalidate(self):
        self.write_result("reference", self.source)
        self.jobs["reference"] = {
            "job_id": "reference",
            "reviewed_windows": [],
            "capture_profile": {},
        }
        self.reviews = [{"job_id": "reference", "revision": 1, "status": "submitted", "reps": []}]
        with patch(
            "fencecoach.coaching_evidence_cache.evaluate_lunges", side_effect=self.fake_evaluation
        ) as evaluate:
            self.evaluation()
            self.reviews[0]["revision"] = 2
            self.evaluation()
            path = self.directory / "reference" / "result.json"
            stat = path.stat()
            self.write_result("reference", {**self.source, "source_marker": "change"})
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.evaluation()
            self.jobs["reference"]["capture_profile"]["weapon_arm"] = "left"
            self.evaluation()
            self.jobs["reference"]["reviewed_windows"] = [{"start_ms": 100, "end_ms": 200}]
            self.evaluation()
            self.reviews.clear()
            self.evaluation()
            self.assertEqual(evaluate.call_count, 6)

    def test_missing_result_never_reuses_cached_evidence(self):
        self.evaluation()
        (self.directory / "athlete" / "result.json").unlink()
        self.assertEqual(self.evaluation(), {})

    def test_corrupt_cache_recomputes_and_write_failure_does_not_block_coaching(self):
        with patch(
            "fencecoach.coaching_evidence_cache.evaluate_lunges", side_effect=self.fake_evaluation
        ) as evaluate:
            self.evaluation()
            path = self.directory / "athlete" / CACHE_FILENAME
            cached = json.loads(path.read_text())
            cached["evaluation"]["source_marker"] = "corrupt"
            path.write_text(json.dumps(cached))
            with (
                patch("fencecoach.coaching_evidence_cache.os.replace", side_effect=OSError),
                self.assertLogs("fencecoach.coaching_evidence_cache", level="WARNING"),
            ):
                self.assertEqual(self.evaluation()["source_marker"], "before")
            self.assertEqual(evaluate.call_count, 2)
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_quality_rejection_and_identity_abstention_survive_cache_hits(self):
        self.source["quality_gate"] = {
            "coaching_allowed": False,
            "issues": [{"code": "low_resolution", "severity": "reject", "tip": "Unsupported"}],
        }
        self.write_result("athlete", self.source)
        rejected = self.evaluation()
        self.assertEqual(rejected["status"], "unsupported")
        self.assertEqual(rejected["reps"], [])
        self.assertEqual(self.evaluation(), rejected)
        # Tracking-only fixture deliberately contains no measured geometry.
        self.source["quality_gate"] = {"coaching_allowed": True, "issues": []}
        self.source["frames"] = [
            {"time_ms": t, "track_epoch": epoch, "features": {"fixture": True}}
            for t, epoch in ((0, 1), (100, 2))
        ]
        self.write_result("athlete", self.source)
        abstained = self.evaluation()
        self.assertEqual(abstained["reps"][0]["status"], "unavailable")
        self.assertEqual(abstained["reps"][0]["measurements"], {})
        self.assertEqual(self.evaluation(), abstained)

    def test_reference_memory_cache_also_uses_result_content_hash(self):
        self.write_result("reference", self.source)
        self.jobs["reference"] = {"job_id": "reference", "capture_profile": {}}
        self.reviews = [{"job_id": "reference", "revision": 1, "reps": []}]
        repository = SimpleNamespace(list_reference_reviews=lambda: self.reviews)
        jobs = SimpleNamespace(get=lambda job_id: self.jobs.get(job_id))
        path = self.directory / "reference" / "result.json"
        with patch(
            "fencecoach.reference_comparison.evaluate_lunges", return_value={"reps": []}
        ) as evaluate:
            attach_reference_comparisons({}, self.job, self.directory, repository, jobs)
            attach_reference_comparisons({}, self.job, self.directory, repository, jobs)
            self.assertEqual(evaluate.call_count, 1)
            stat = path.stat()
            self.write_result("reference", {**self.source, "source_marker": "change"})
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            attach_reference_comparisons({}, self.job, self.directory, repository, jobs)
            self.assertEqual(evaluate.call_count, 2)


if __name__ == "__main__":
    unittest.main()

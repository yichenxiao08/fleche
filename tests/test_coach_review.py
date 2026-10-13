import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fencecoach.coach_review_api import coach_review_router
from fencecoach.video_jobs import Crop, VideoJobs


class CoachReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.jobs = VideoJobs(root / "review.sqlite3", root / "videos")
        job = self.jobs.create("Coach review test", "beginner", Crop())
        self.job_id = job["job_id"]
        folder = self.jobs.directory / self.job_id
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps(
                {
                    "duration_ms": 1000,
                    "candidates": [],
                    "preview": {"fps_hint": 30},
                    "model_sha256": "test-pose-model",
                }
            )
        )
        self.jobs.update(
            self.job_id,
            status="completed",
            reviewed_windows=[{"onset_ms": 100, "start_ms": 200, "end_ms": 900}],
        )
        app = FastAPI()
        app.include_router(coach_review_router(self.jobs))
        self.client = TestClient(app)
        self.url = f"/api/videos/{self.job_id}/coach-feedback"

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def draft(self):
        return self.client.get(self.url).json()["feedback"]

    def test_draft_persists_with_frame_and_attribution(self):
        draft = self.draft()
        draft["reps"][0].update(main_issue="Arm direction", evidence_ms=267)
        response = self.client.put(self.url, json=draft)
        self.assertEqual(response.status_code, 200)
        saved = self.draft()
        self.assertEqual(saved["reps"][0]["evidence_ms"], 267)
        self.assertEqual(saved["revision"], 1)
        self.assertIn("Not automatically", saved["attribution"])

    def test_stale_revision_cannot_overwrite_other_reviewer(self):
        first = self.draft()
        self.assertEqual(self.client.put(self.url, json=first).status_code, 200)
        first["reviewer"] = "Stale reviewer"
        self.assertEqual(self.client.put(self.url, json=first).status_code, 409)
        self.assertEqual(self.draft()["reviewer"], "")

    def test_timestamp_must_be_inside_video(self):
        draft = self.draft()
        draft["reps"][0]["evidence_ms"] = 1001
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 422)

    def test_submission_requires_author_and_assessments(self):
        draft = self.draft()
        draft["status"] = "submitted"
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 422)
        draft.update(reviewer="Test coach", intended_drill="Straight lunge")
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 422)
        draft["reps"][0]["rating"] = "reference"
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 200)

    def test_correction_requires_specific_evidence_and_cue(self):
        draft = self.draft()
        draft.update(status="submitted", reviewer="Test coach", intended_drill="Straight lunge")
        draft["reps"][0]["rating"] = "correction"
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 422)
        draft["reps"][0].update(
            main_issue="Arm drops",
            evidence_ms=267,
            evidence_description="Hand is below shoulder",
            cue="Reach toward target",
            improvement="Hand stays on intended target line",
        )
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 200)

    def test_each_rep_must_appear_exactly_once(self):
        draft = self.draft()
        draft["reps"].append(draft["reps"][0].copy())
        self.assertEqual(self.client.put(self.url, json=draft).status_code, 422)


if __name__ == "__main__":
    unittest.main()

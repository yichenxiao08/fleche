import unittest
from pathlib import Path
from uuid import uuid4

from fencecoach.repository import Repository
from fencecoach.video_jobs import AcceptReview, Crop, ReviewWindow, VideoJobs


class SavedVideoTimingEditTests(unittest.TestCase):
    def test_editing_saved_windows_recalculates_metrics_without_replacing_session(self):
        root = Path(__file__).resolve().parents[1] / "work" / f"saved-video-timing-{uuid4().hex}"
        root.mkdir(parents=True)
        Repository(root / "db.sqlite3").list_sessions()
        jobs = VideoJobs(root / "db.sqlite3", root / "videos")
        job = jobs.create("Lunge practice", "beginner", Crop())
        jobs.update(job["job_id"], status="review_ready")
        candidate = {
            "candidate_id": "rep-1",
            "onset_ms": 500,
            "start_ms": 1000,
            "end_ms": 1800,
            "quality": 0.9,
        }
        result = {
            "duration_ms": 3000,
            "candidates": [candidate],
            "frames": [],
            "clip_measurements": [],
            "initial_guard_measurements": [],
            "fleche_events": [],
            "model_sha256": "model-sha",
        }

        saved = jobs.accept(
            job["job_id"],
            AcceptReview(
                windows=[
                    ReviewWindow(
                        candidate_id="rep-1",
                        onset_ms=500,
                        start_ms=1000,
                        end_ms=1800,
                    )
                ],
                notes="Keep this note",
            ),
            result,
        )
        changed = jobs.accept(
            job["job_id"],
            AcceptReview(
                update_existing=True,
                windows=[
                    ReviewWindow(
                        candidate_id="rep-1",
                        onset_ms=650,
                        start_ms=1250,
                        end_ms=2050,
                    )
                ],
            ),
            result,
        )

        self.assertEqual(changed.session_id, saved.session_id)
        self.assertEqual(changed.notes, "Keep this note")
        recovery = next(m for m in changed.metrics if m.name == "recovery_time")
        self.assertEqual(recovery.value, 800)
        self.assertEqual(recovery.start_ms, 1250)
        self.assertEqual(recovery.end_ms, 2050)
        self.assertEqual(jobs.get(job["job_id"])["reviewed_windows"][0]["onset_ms"], 650)


if __name__ == "__main__":
    unittest.main()

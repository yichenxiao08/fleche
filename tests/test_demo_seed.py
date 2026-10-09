import tempfile
import unittest
from pathlib import Path

from fencecoach.demo_seed import seed_examples
from fencecoach.video_jobs import VideoJobs


class DemoSeedTests(unittest.TestCase):
    def test_attributed_examples_are_idempotent_and_unsupported(self):
        examples = Path(__file__).resolve().parents[1] / "examples/video"
        with tempfile.TemporaryDirectory() as temp:
            jobs = VideoJobs(Path(temp) / "db.sqlite3", Path(temp) / "videos")
            self.assertEqual(len(seed_examples(jobs, examples)), 3)
            self.assertEqual(seed_examples(jobs, examples), [])
            self.assertEqual(len(jobs.list()), 3)
            import json

            for job in jobs.list():
                result = json.loads((jobs.directory / job["job_id"] / "result.json").read_text())
                self.assertFalse(result["quality_gate"]["coaching_allowed"])
                self.assertEqual(result["job_id"], job["job_id"])


if __name__ == "__main__":
    unittest.main()

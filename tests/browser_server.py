"""UI fixture server: real HTTP/storage/jobs, synthetic analysis and model output.

Only launched by browser_smoke.py against a temporary database. Never imported by
the production application. This proves wiring, not pose or coaching accuracy.
"""

import json
import threading
import time

import uvicorn
from langchain_core.messages import AIMessage

import fencecoach.api as api
import fencecoach.coaching_jobs as coaching
from fencecoach.coach.graph import run_coach
from fencecoach.quality import assess_quality
from fencecoach.video_preview import build_preview


def fixture_result(job, directory):
    from fencecoach.video_pipeline import PROPOSAL_VERSION

    points = [[0.5, 0.5, 0, 0.95, 0.95] for _ in range(33)]
    for j in (0,):
        points[j][1] = 0.15
    for j in (27, 28, 31, 32):
        points[j][1] = 0.85
    frames = [
        {
            "time_ms": t,
            "quality": 0.95,
            "track_epoch": 0,
            "tracking": {"detected_poses": 1},
            "landmarks": points,
            "features": {
                "stance_ratio": 1,
                "left_knee_angle": 110,
                "right_knee_angle": 165,
                "torso_tilt": 10,
                "left_elbow_angle": 150,
                "right_elbow_angle": 175,
                "quality_by_feature": {},
            },
        }
        for t in range(0, 3001, 100)
    ]
    measurement = {
        "name": "right_elbow_angle_at_peak",
        "value": 175,
        "unit": "deg",
        "confidence": 0.95,
        "start_ms": 1500,
        "end_ms": 1500,
    }
    result = {
        "job_id": job["job_id"],
        "fixture": True,
        "pipeline_version": "TEST-FIXTURE-NOT-INFERENCE",
        "proposal_version": PROPOSAL_VERSION,
        "model_sha256": "fixture",
        "duration_ms": 3000,
        "width": 1280,
        "height": 720,
        "sampled_frames": len(frames),
        "tracked_frames": len(frames),
        "frames": frames,
        "capture_profile": job["capture_profile"],
        "camera_evidence": {"assessed": True, "moving": False},
        "candidates": [
            {
                "candidate_id": "recovery-01",
                "start_ms": 1500,
                "end_ms": 2500,
                "onset_ms": 1000,
                "quality": 0.95,
                "movement_label": "lunge",
                "rep_number": 1,
                "set_number": 1,
                "lunge_cue_count": 3,
                "measurements": [measurement],
            }
        ],
        "clip_measurements": [],
        "exercise_sets": [],
        "activity_segments": [],
        "warnings": ["Synthetic UI fixture. No athlete or real motion was analyzed."],
        "footwork_events": [],
        "source": "test_fixture",
    }
    result["preview"] = build_preview(directory / "source.video", directory)
    if "unsupported" in job["title"].lower():
        result["height"] = 240
    result["quality_gate"] = assess_quality(result)
    return result


class FixtureWorker:
    def __init__(self, jobs, model):
        self.jobs = jobs
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(3)

    def run(self):
        while not self.stop.wait(0.1):
            job = self.jobs.claim("browser-fixture")
            if not job:
                continue
            owned = type(self.jobs)(self.jobs.db_path, self.jobs.directory, "browser-fixture")
            try:
                owned.update(job["job_id"], stage="Processing synthetic UI fixture", progress=40)
                directory = self.jobs.directory / job["job_id"]
                time.sleep(0.5)
                result = fixture_result(job, directory)
                (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
                owned.update(
                    job["job_id"],
                    status="review_ready",
                    stage="Review synthetic fixture",
                    progress=100,
                )
            except Exception as exc:
                owned.update(job["job_id"], status="failed", error=str(exc), stage="Fixture error")


class FixtureModel:
    model = "TEST-FIXTURE-NOT-AN-LLM"

    def bind(self, **kwargs):
        return self

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(
            content="At 1.50s, the tracked weapon elbow is 175 degrees. Try a slow solo set with a full reset between attempts. Repeat the drill toward the same target; this helps compare the finish without assuming a timing fault.",
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )


if __name__ == "__main__":
    import fencecoach.video_api as videos

    # Inference is replaced here. CI doesn't need pretrained weights for UI wiring.
    videos.availability = lambda _: {"available": True}
    api.availability = videos.availability
    api.VideoWorker = FixtureWorker
    api.provider_status = lambda: {
        "provider": "local",
        "local_ready": True,
        "live_configured": True,
        "bedrock_ready": False,
        "model_id": FixtureModel.model,
    }
    coaching.warm_local_model = lambda: None
    coaching.run_coach = lambda request, mode, **kwargs: run_coach(
        request, mode, model=FixtureModel(), **kwargs
    )
    import sys

    uvicorn.run(api.app, host="127.0.0.1", port=int(sys.argv[1]))

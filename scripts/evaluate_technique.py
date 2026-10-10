"""Evaluate existing footage using geometry only, without human technique notes."""

import argparse
import json
from pathlib import Path

from fencecoach.settings import settings
from fencecoach.technique import evaluate_lunges
from fencecoach.video_jobs import VideoJobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/technique-evaluations"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = VideoJobs(settings.fencecoach_db_path, settings.fencecoach_video_dir)
    summary = []
    for job in jobs.list():
        path = jobs.directory / job["job_id"] / "result.json"
        if not path.is_file() or job["status"] not in {"completed", "review_ready"}:
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        evaluation = evaluate_lunges(
            result,
            job.get("reviewed_windows") or result.get("candidates", []),
            job.get("capture_profile", {}),
        )
        (args.output / f"{job['job_id']}.json").write_text(
            json.dumps(evaluation, indent=2), encoding="utf-8"
        )
        summary.append(
            {
                "job_id": job["job_id"],
                "title": job["title"],
                "status": evaluation["status"],
                "reps": len(evaluation["reps"]),
                "flags": len(evaluation["findings"]),
                "reason": evaluation.get("reason"),
                "human_technique_feedback_used": False,
            }
        )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

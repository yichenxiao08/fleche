"""Integrate existing submissions and export auditable technique-learning examples.

This updates session measurements from reviewed bookmarks, not gesture weights.
Do not fabricate dense gesture labels from sparse frame anchors.
"""

import argparse
import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fencecoach.feedback_learning import apply_submitted_feedback
from fencecoach.settings import settings
from fencecoach.video_jobs import VideoJobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id")
    parser.add_argument("--output", type=Path, default=Path("data/coach-learning"))
    args = parser.parse_args()
    jobs = VideoJobs(settings.fencecoach_db_path, settings.fencecoach_video_dir)
    with closing(jobs.connect()) as db:
        rows = db.execute("SELECT job_id,payload FROM coach_feedback").fetchall()
    records = []
    for job_id, raw in rows:
        if args.job_id and job_id != args.job_id:
            continue
        feedback = json.loads(raw)
        if feedback.get("status") != "submitted":
            continue
        job = jobs.get(job_id)
        result = json.loads((jobs.directory / job_id / "result.json").read_text(encoding="utf-8"))
        windows = job.get("reviewed_windows") or [
            {"onset_ms": c.get("onset_ms"), "start_ms": c["start_ms"], "end_ms": c["end_ms"]}
            for c in result.get("candidates", [])
        ]
        with closing(jobs.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            # Protect against a reviewer changing the submission while it is read.
            current = db.execute(
                "SELECT payload FROM coach_feedback WHERE job_id=?", (job_id,)
            ).fetchone()
            if json.loads(current[0]).get("revision") != feedback["revision"]:
                raise RuntimeError("Feedback changed during preparation; run again.")
            integration = apply_submitted_feedback(db, job, result, feedback, windows)
            feedback["integration"] = integration
            db.execute(
                "UPDATE coach_feedback SET payload=? WHERE job_id=?", (json.dumps(feedback), job_id)
            )
            corpus = json.loads(
                db.execute(
                    "SELECT payload FROM coach_training_examples WHERE job_id=?", (job_id,)
                ).fetchone()[0]
            )
        records.append(corpus)
    args.output.mkdir(parents=True, exist_ok=True)
    examples = [
        dict(job_id=c["job_id"], revision=c["revision"], source_group=c["source_group"], **r)
        for c in records
        for r in c["examples"]
    ]
    (args.output / "technique-examples.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in examples), encoding="utf-8"
    )
    (args.output / "review-snapshots.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    positives = [
        r
        for r in examples
        if r["rating"] in {"minor", "correction"} and r.get("main_issue", "").strip()
    ]
    negatives = [
        r for r in examples if r["rating"] == "reference" and not r.get("main_issue", "").strip()
    ]
    conflicts = [
        r["rep_number"]
        for r in examples
        if r["rating"] == "reference" and r.get("main_issue", "").strip()
    ]
    reasons = []
    if not positives or not negatives:
        reasons.append(
            "Need both explicit correction examples and reference examples without stated issues; reference-rated reps with corrections are mixed examples."
        )
    if len(records) < 2:
        reasons.append(
            "Only one recording: no independent recording to evaluate transfer. Frames and intentional variants from that recording do not create independent validation data."
        )
    reasons.append(
        "No structured per-issue presence/absence labels or verified athlete/source grouping yet. Free-text issues support retrieval; they are not automatically converted into classifier targets."
    )
    report = {
        "schema": "fencecoach-technique-readiness-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "submitted_reps": len(examples),
        "recordings": len(records),
        "explicit_correction_reps": len(positives),
        "clean_reference_reps": len(negatives),
        "reference_reps_with_issues": conflicts,
        "personalized_retrieval_ready": bool(examples),
        "classifier_training_ready": False,
        "classifier_fitted": False,
        "llm_fine_tuned": False,
        "blocked_reasons": reasons,
        "next_data": "Structured issue labels and independent reviewed recordings; do not mark absent issues from silence in free text.",
    }
    (args.output / "readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

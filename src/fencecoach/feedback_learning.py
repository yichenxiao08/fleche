"""Connect submitted technique reviews to session evidence and a versioned corpus.

Review text is human feedback, not an automatic technique verdict. Frame anchors
are not dense phase labels and related frames never count as independent reps.
"""

import json
from datetime import UTC, datetime

from fencecoach.motion import window_measurements
from fencecoach.schemas import MetricObservation, SessionRecord, VideoProvenance


def corrected_windows(feedback, windows):
    output = []
    for rep in sorted(feedback["reps"], key=lambda r: r["rep_number"]):
        original = windows[rep["rep_number"] - 1]
        output.append(
            {
                "onset_ms": rep.get("action_start_ms")
                if rep.get("action_start_ms") is not None
                else original.get("onset_ms")
                if original.get("onset_ms") is not None
                else original["start_ms"],
                "start_ms": rep.get("lunge_ms")
                if rep.get("lunge_ms") is not None
                else original["start_ms"],
                "end_ms": rep.get("guard_ms")
                if rep.get("guard_ms") is not None
                else original["end_ms"],
            }
        )
    return output


def apply_submitted_feedback(db, job, result, feedback, windows):
    """Apply measurements and corpus snapshot in the feedback-save transaction."""
    if feedback["status"] != "submitted":
        return None
    corrected = corrected_windows(feedback, windows)
    for i, window in enumerate(corrected, 1):
        if (
            not 0
            <= window["onset_ms"]
            <= window["start_ms"]
            < window["end_ms"]
            <= result["duration_ms"]
        ):
            raise ValueError(f"Rep {i}: bookmarks must be ordered within the video.")
    if any(a["end_ms"] > b["onset_ms"] for a, b in zip(corrected, corrected[1:])):
        raise ValueError("Rep bookmarks overlap. Finish each return before the next action starts.")
    frames = result.get("frames", [])
    metrics = []
    examples = []
    for rep, window in zip(sorted(feedback["reps"], key=lambda r: r["rep_number"]), corrected):
        onset = window["onset_ms"]
        nearest = (
            min(
                (f for f in frames if f.get("features")),
                key=lambda f: abs(f["time_ms"] - onset),
                default=None,
            )
            if onset is not None
            else None
        )
        onset_evidence = None
        if nearest and abs(nearest["time_ms"] - onset) <= 125:
            onset_evidence = {
                "onset_ms": onset,
                "onset_features": nearest["features"],
                "quality": nearest.get("quality", 0),
            }
        details = window_measurements(
            frames,
            window["start_ms"],
            window["end_ms"],
            onset_evidence,
            job.get("capture_profile", {}),
        )
        # Don't describe a distant tracked frame as the selected lunge finish.
        details = [
            m
            for m in details
            if not m["name"].endswith("_at_peak") or abs(m["start_ms"] - window["start_ms"]) <= 125
        ]
        # This includes any hold at the finish: do not present it as active recovery speed.
        measurements = [
            {
                "name": "lunge_finish_to_guard_time",
                "value": window["end_ms"] - window["start_ms"],
                "unit": "ms",
                "confidence": 0,
                "start_ms": window["start_ms"],
                "end_ms": window["end_ms"],
            },
            *details,
        ]
        for i, measurement in enumerate(measurements):
            if measurement["name"].startswith("recovery_"):
                measurement = {
                    **measurement,
                    "name": measurement["name"].replace("recovery_", "finish_to_guard_", 1),
                }
            metrics.append(
                MetricObservation(
                    metric_id=f"video-{job['job_id'][:10]}-rep-{rep['rep_number']:02}-review-{i:02}",
                    **measurement,
                    provenance=VideoProvenance(
                        job_id=job["job_id"],
                        method="coach-bookmark-remeasurement-v1",
                        model_sha256=result["model_sha256"],
                        annotation="manual_window" if i == 0 else "manual_geometry",
                        quality_note=f"Submitted review revision {feedback['revision']}. Sampled 2D pose geometry, not calibrated accuracy. Finish-to-guard includes any hold; no active recovery onset was labeled.",
                    ),
                )
            )
        examples.append(
            {
                **rep,
                "window": window,
                "measurements": [
                    m.model_dump(mode="json")
                    for m in metrics
                    if f"-rep-{rep['rep_number']:02}-" in m.metric_id
                ],
            }
        )
    session_id = job.get("session_id")
    if session_id:
        row = db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            session = SessionRecord.model_validate_json(row[0])
            prefix = f"video-{job['job_id'][:10]}-"
            keep = [
                m
                for m in session.metrics
                if not (
                    m.metric_id.startswith(prefix + "rep-")
                    or m.metric_id.startswith(prefix + "recovery-")
                )
            ]
            session.metrics = [*metrics, *keep]
            db.execute(
                "UPDATE sessions SET payload=? WHERE id=?", (session.model_dump_json(), session_id)
            )
    db.execute(
        "CREATE TABLE IF NOT EXISTS coach_training_examples (job_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)"
    )
    corpus = {
        "schema": "fencecoach-technique-examples-v1",
        "job_id": job["job_id"],
        "session_id": session_id,
        "revision": feedback["revision"],
        "created_at": datetime.now(UTC).isoformat(),
        "reviewer_role": feedback["reviewer_role"],
        "role_verified": False,
        "weapon": feedback["weapon"],
        "intended_drill": feedback["intended_drill"],
        "target_height": feedback["target_height"],
        "capture_profile": job.get("capture_profile", {}),
        "source_group": job["job_id"],
        "examples": examples,
        "limits": [
            "One recording is one independent source group.",
            "Reference ratings with stated issues are not flawless negative examples.",
            "Intentional variation does not mean correct technique.",
            "Bookmarks are sparse anchors, not reviewed frame-by-frame gesture labels.",
            "No classifier or LLM weights are updated by submission.",
        ],
    }
    db.execute(
        "INSERT INTO coach_training_examples VALUES (?,?,?) ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
        (job["job_id"], feedback["revision"], json.dumps(corpus)),
    )
    return {
        "feedback_revision": feedback["revision"],
        "remeasured_metrics": len(metrics),
        "training_examples": len(examples),
        "coach_connected": bool(session_id),
        "classifier_trained": False,
        "corrected_windows": corrected,
    }

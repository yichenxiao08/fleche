"""Human-authored technique feedback, kept separate from automatic training labels."""

import json
import re
from contextlib import closing
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class RepFeedback(BaseModel):
    rep_number: int = Field(ge=1, le=50)
    rating: Literal["", "reference", "minor", "correction", "unclear"] = ""
    done_well: str = Field(default="", max_length=2000)
    main_issue: str = Field(default="", max_length=2000)
    evidence_ms: int | None = Field(default=None, ge=0)
    evidence_description: str = Field(default="", max_length=2000)
    cue: str = Field(default="", max_length=2000)
    improvement: str = Field(default="", max_length=2000)
    intentional: Literal["unknown", "yes", "no"] = "unknown"


class CoachFeedback(BaseModel):
    revision: int = Field(default=0, ge=0)
    status: Literal["draft", "submitted"] = "draft"
    reviewer: str = Field(default="", max_length=100)
    reviewer_role: Literal["coach", "athlete", "other"] = "coach"
    weapon: Literal["foil", "epee", "sabre", "unspecified"] = "unspecified"
    intended_drill: str = Field(default="", max_length=2000)
    target_height: str = Field(default="", max_length=300)
    source_offset_ms: int = Field(default=0, ge=0, le=86400000)
    reps: list[RepFeedback] = Field(default_factory=list, max_length=50)


def coach_review_router(jobs):
    router = APIRouter(prefix="/api/videos", tags=["coach review"])
    with closing(jobs.connect()) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS coach_feedback "
            "(job_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)"
        )

    def context(job_id):
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise HTTPException(404, "Video review not found.")
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Video review not found.")
        if job["status"] not in {"completed", "review_ready"}:
            raise HTTPException(409, "Wait for video analysis to finish.")
        path = jobs.directory / job_id / "result.json"
        if not path.is_file():
            raise HTTPException(409, "Video analysis is unavailable.")
        result = json.loads(path.read_text(encoding="utf-8"))
        windows = job.get("reviewed_windows") or [
            {"onset_ms": c.get("onset_ms"), "start_ms": c["start_ms"], "end_ms": c["end_ms"]}
            for c in result.get("candidates", [])
        ]
        return job, result, windows

    @router.get("/{job_id}/coach-feedback")
    def get_feedback(job_id: str):
        job, result, windows = context(job_id)
        with closing(jobs.connect()) as db:
            row = db.execute(
                "SELECT payload FROM coach_feedback WHERE job_id=?", (job_id,)
            ).fetchone()
        feedback = (
            json.loads(row[0])
            if row
            else CoachFeedback(
                reps=[RepFeedback(rep_number=i + 1) for i in range(len(windows))]
            ).model_dump()
        )
        return {
            "job_id": job_id,
            "title": job["title"],
            "session_id": job.get("session_id"),
            "duration_ms": result["duration_ms"],
            "windows": windows,
            "intervals_reviewed": bool(job.get("reviewed_windows")),
            "fps": result.get("preview", {}).get("fps_hint", 30),
            "pose_sample_interval_ms": result.get("sample_interval_ms"),
            "feedback": feedback,
        }

    @router.put("/{job_id}/coach-feedback")
    def save_feedback(job_id: str, data: CoachFeedback):
        _, result, windows = context(job_id)
        numbers = [r.rep_number for r in data.reps]
        if sorted(numbers) != list(range(1, len(windows) + 1)):
            raise HTTPException(422, "Include feedback for each rep exactly once.")
        if any(
            r.evidence_ms is not None and r.evidence_ms > result["duration_ms"] for r in data.reps
        ):
            raise HTTPException(422, "An evidence timestamp is outside this video.")
        if data.status == "submitted":
            if not data.reviewer.strip() or not data.intended_drill.strip():
                raise HTTPException(
                    422, "Enter the reviewer's name and intended drill before submitting."
                )
            for rep in data.reps:
                if not rep.rating:
                    raise HTTPException(422, f"Choose an assessment for rep {rep.rep_number}.")
                if rep.rating in {"minor", "correction"} and (
                    not rep.main_issue.strip()
                    or not rep.cue.strip()
                    or rep.evidence_ms is None
                    or not rep.evidence_description.strip()
                    or not rep.improvement.strip()
                ):
                    raise HTTPException(
                        422,
                        f"Rep {rep.rep_number}: add the issue, evidence frame, visible reason, cue, and improvement check.",
                    )
        with closing(jobs.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision FROM coach_feedback WHERE job_id=?", (job_id,)
            ).fetchone()
            revision = row[0] if row else 0
            if revision != data.revision:
                raise HTTPException(
                    409,
                    "Another reviewer saved changes. Export your draft, then reload before saving.",
                )
            payload = data.model_dump()
            payload.update(
                revision=revision + 1,
                saved_at=datetime.now(UTC).isoformat(),
                attribution="Human-entered review; reviewer role is self-declared. Not automatically used as training ground truth.",
            )
            db.execute(
                "INSERT INTO coach_feedback VALUES (?,?,?) ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
                (job_id, revision + 1, json.dumps(payload)),
            )
        return payload

    return router

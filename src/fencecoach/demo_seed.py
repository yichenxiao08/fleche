"""Idempotently install attributed, preprocessed examples; never mark them supported."""

from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def seed_examples(jobs, source: Path) -> list[str]:
    manifest = source / "manifest.json"
    if not manifest.is_file():
        return []
    installed = []
    for item in json.loads(manifest.read_text(encoding="utf-8"))["clips"]:
        job_id = hashlib.sha256(("fencecoach-example-v1:" + item["id"]).encode()).hexdigest()[:32]
        if jobs.get(job_id):
            continue
        folder = source / item["id"]
        if hashlib.sha256((folder / "source.video").read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Packaged example source checksum differs from the manifest.")
        destination = jobs.directory / job_id
        destination.mkdir(parents=True, exist_ok=True)
        for filename in (
            "source.video",
            "preview.mp4",
            "poster.jpg",
            "contact-sheet.jpg",
            "source.json",
            "result.json",
            "evidence.json",
        ):
            if (folder / filename).is_file():
                shutil.copy2(folder / filename, destination / filename)
        result = json.loads((destination / "result.json").read_text(encoding="utf-8"))
        result["job_id"] = job_id
        (destination / "result.json").write_text(json.dumps(result), encoding="utf-8")
        job = {
            "job_id": job_id,
            "title": item["title"],
            "skill_level": "beginner",
            "crop": {"x": 0, "y": 0, "width": 1, "height": 1},
            "capture_profile": result.get("capture_profile", {}),
            "source": "mit_ocw",
            "status": "review_ready",
            "progress": 100,
            "stage": "Preprocessed archival example — inspect QA before coaching",
            "created_at": datetime.now(UTC).isoformat(),
            "error": None,
            "session_id": None,
            "packaged_example": True,
            "bytes": item["bytes"],
        }
        with closing(jobs.connect()) as db, db:
            db.execute(
                "INSERT INTO video_jobs VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (job_id, job["created_at"], job["status"], json.dumps(job)),
            )
        installed.append(job_id)
    return installed

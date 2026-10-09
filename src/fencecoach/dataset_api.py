"""Local dataset review, with separate footwork, blade and tactical label tracks."""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from fencecoach.data_policy import eligible_source, eligible_training_source
from fencecoach.dataset_labels import (
    EVENT_KINDS,
    EXCLUSION_FLAGS,
    ONTOLOGY,
    SCHEMA_VERSION,
    TRAINABLE_FOOTWORK_LABELS,
    DatasetAnnotations,
    usable_review,
)
from fencecoach.movement_timeline import build_movement_timeline
from fencecoach.training_data import CORE_CLASSES, collect_corpus, readiness

LOCK = threading.RLock()


def dataset_router(root: Path, automation=None):
    root = root.resolve()
    router = APIRouter(prefix="/api/datasets", tags=["training data"])

    @router.get("/automation")
    def automation_status():
        return automation.status() if automation else {"status": "disabled"}

    def folder(collection, clip_id):
        if collection not in {
            "mit-ocw",
            "commons",
            "footwork-clips",
            "youtube-cc",
        } or not re.fullmatch(r"[a-z0-9_-]{1,100}", clip_id):
            raise HTTPException(404, "Dataset clip not found.")
        path = (root / collection / clip_id).resolve()
        if not path.is_relative_to(root) or not (path / "source.json").is_file():
            raise HTTPException(404, "Dataset clip not found.")
        return path

    def annotations(path):
        file = path / "labels.json"
        return (
            DatasetAnnotations.model_validate_json(file.read_text(encoding="utf-8")).model_dump()
            if file.is_file()
            else DatasetAnnotations().model_dump()
        )

    @router.get("")
    def inventory(include_excluded: bool = False):
        clips, counts = [], Counter()
        excluded = 0
        reviewed_by_label = {
            label: {"intervals": 0, "groups": set(), "clips": set(), "athletes": set()}
            for label in TRAINABLE_FOOTWORK_LABELS
        }
        athletes = {}
        missing_athlete_intervals = 0
        reviewed_clip_ids = set()
        for file in sorted(root.glob("*/*/source.json")):
            source = json.loads(file.read_text(encoding="utf-8"))
            eligible = eligible_source(source)
            if not eligible:
                excluded += 1
                if not include_excluded:
                    continue
            marked = annotations(file.parent)
            validated = DatasetAnnotations.model_validate(marked)
            statuses = Counter(s["status"] for s in marked["segments"])
            counts.update(statuses)
            if eligible and marked.get("reviewer_role") in {"athlete", "coach"}:
                group = source.get("split_group") or source.get("sha256")
                clip_key = f"{file.parent.parent.name}/{source['clip_id']}"
                for segment in validated.segments:
                    if (
                        segment.layer != "footwork"
                        or not usable_review(segment)
                        or segment.label not in reviewed_by_label
                    ):
                        continue
                    progress = reviewed_by_label[segment.label]
                    progress["intervals"] += 1
                    progress["groups"].add(group)
                    progress["clips"].add(clip_key)
                    reviewed_clip_ids.add(clip_key)
                    athlete_id = validated.athlete_id.strip()
                    if athlete_id and segment.track_id == validated.primary_track_id:
                        progress["athletes"].add(athlete_id)
                        athlete = athletes.setdefault(
                            athlete_id,
                            {
                                "intervals": 0,
                                "clips": set(),
                                "groups": set(),
                                "sessions": set(),
                                "camera_setups": set(),
                            },
                        )
                        athlete["intervals"] += 1
                        athlete["clips"].add(clip_key)
                        athlete["groups"].add(group)
                        if validated.recording_session_id:
                            athlete["sessions"].add(validated.recording_session_id)
                        if validated.camera_setup_id:
                            athlete["camera_setups"].add(validated.camera_setup_id)
                    else:
                        missing_athlete_intervals += 1
            clips.append(
                {
                    **source,
                    "training_eligible": eligible,
                    "collection": file.parent.parent.name,
                    "annotation_counts": dict(statuses),
                    "prepared": (file.parent / "prepared/result.json").is_file(),
                    "athlete_id": validated.athlete_id,
                    "draft_classes": sorted(
                        {s.label for s in validated.segments if s.status == "provisional"}
                    ),
                    "disagreements": sum(
                        s.suggestion_disagreement
                        for s in validated.segments
                        if s.status == "provisional"
                    ),
                }
            )
        return dict(
            clips=clips,
            ontology=ONTOLOGY,
            label_schema_version=SCHEMA_VERSION,
            event_kinds=EVENT_KINDS,
            exclusion_flags=EXCLUSION_FLAGS,
            annotation_counts=dict(counts),
            excluded_sources=excluded,
            training_readiness={
                "reviewed_clips": len(reviewed_clip_ids),
                "eligible_clips": sum(clip["training_eligible"] for clip in clips),
                "minimum_windows_per_class": 20,
                "minimum_independent_groups_per_class": 3,
                "athletes": {
                    key: {
                        name: len(value) if isinstance(value, set) else value
                        for name, value in data.items()
                    }
                    for key, data in sorted(athletes.items())
                },
                "intervals_missing_athlete_id": missing_athlete_intervals,
                "collection_targets": {
                    "windows_per_class": 150,
                    "training_athletes": 6,
                    "held_out_athletes": 2,
                },
                "classes": {
                    label: {
                        "reviewed_intervals": progress["intervals"],
                        "independent_groups": len(progress["groups"]),
                        "clips": len(progress["clips"]),
                        "athletes": len(progress["athletes"]),
                    }
                    for label, progress in reviewed_by_label.items()
                },
            },
            note="Only inspected modern sport fencing sources are eligible. Provisional labels remain excluded from training; historical and unreviewed footage are blocked.",
        )

    @router.get("/readiness")
    def training_readiness(
        task: str = "gesture",
        classes: str | None = None,
        window_ms: int = 750,
    ):
        """Report strict, reviewed-data gates; this route never fits a model."""
        selected = (
            [label.strip() for label in classes.split(",") if label.strip()]
            if classes
            else list(CORE_CLASSES)
        )
        try:
            corpus = collect_corpus(root, task=task, classes=selected, window_ms=window_ms)
            report, _ = readiness(corpus)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return report

    @router.get("/{collection}/{clip_id}/labels")
    def read_labels(collection: str, clip_id: str):
        return annotations(folder(collection, clip_id))

    @router.put("/{collection}/{clip_id}/labels")
    def save_labels(collection: str, clip_id: str, data: DatasetAnnotations):
        path = folder(collection, clip_id)
        try:
            data.validate_no_overlapping_segments()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        source = json.loads((path / "source.json").read_text(encoding="utf-8"))
        ordered = sorted(data.segments, key=lambda s: (s.track_id, s.layer, s.start_ms))
        for segment in ordered:
            if segment.end_ms > source["duration_ms"]:
                raise HTTPException(422, "A label extends past the source video.")
        if any(event.time_ms > source["duration_ms"] for event in data.events):
            raise HTTPException(422, "An event extends past the source video.")
        with LOCK:
            previous = annotations(path)
            if previous["revision"] != data.revision:
                raise HTTPException(409, "Labels changed. Reload before saving.")
            payload = data.model_dump()
            for field in ("segments", "events"):
                old_items = {item["id"]: item for item in previous.get(field, [])}
                for item in payload[field]:
                    old = old_items.get(item["id"])
                    if old:
                        item["origin"] = old["origin"]
                        item["suggested_by"] = old["suggested_by"]
                    changed = not old or any(
                        value != old.get(key)
                        for key, value in item.items()
                        if key not in {"reviewed_by", "reviewed_at"}
                    )
                    if item["status"] == "reviewed" and changed:
                        item["reviewed_by"] = data.reviewer.strip()
                        item["reviewed_at"] = datetime.now(UTC).isoformat()
                    elif item["status"] == "reviewed" and old:
                        item["reviewed_by"] = old["reviewed_by"]
                        item["reviewed_at"] = old.get("reviewed_at")
                    else:
                        item["reviewed_by"] = ""
                        item["reviewed_at"] = None
            payload.update(
                schema_version=SCHEMA_VERSION,
                revision=data.revision + 1,
                source_sha256=source["sha256"],
                updated_at=datetime.now(UTC).isoformat(),
            )
            history = path / "label-history"
            history.mkdir(exist_ok=True)
            (history / f"{uuid4().hex}.json").write_text(
                json.dumps(dict(before=previous, after=payload), indent=2), encoding="utf-8"
            )
            temp = path / f"labels-{uuid4().hex}.tmp"
            temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp.replace(path / "labels.json")
        if automation:
            automation.wake.set()
        return payload

    @router.get("/{collection}/{clip_id}/suggestions")
    def suggestions(collection: str, clip_id: str):
        path = folder(collection, clip_id)
        file = path / "prepared/result.json"
        if not file.is_file():
            raise HTTPException(409, "Prepare pose analysis for this clip first.")
        result = json.loads(file.read_text(encoding="utf-8"))
        timeline = result.get("movement_timeline") or build_movement_timeline(result)
        track = annotations(path)["primary_track_id"]
        segments, events = [], []
        conflicts = [c for c in timeline["cycles"] if c["recognition_conflict"]]
        for movement in timeline["movements"]:
            if movement["label"] not in ONTOLOGY["footwork"]:
                continue
            segments.append(
                dict(
                    start_ms=movement["start_ms"],
                    end_ms=movement["end_ms"],
                    layer="footwork",
                    label=movement["label"],
                    track_id=track,
                    origin="model"
                    if movement["source"] == "trained_temporal_classifier"
                    else "heuristic",
                    suggested_by=movement["source"],
                    status="provisional",
                    suggestion_disagreement=any(
                        cycle["start_ms"] < movement["end_ms"]
                        and cycle["peak_ms"] > movement["start_ms"]
                        for cycle in conflicts
                    ),
                )
            )
        for phase in timeline["phases"]:
            kind = "stance_peak" if phase["label"] == "stance_expansion" else "recovery_complete"
            events.append(
                dict(
                    time_ms=phase["end_ms"],
                    kind=kind,
                    track_id=track,
                    origin="heuristic",
                    suggested_by="movement_timeline",
                    status="provisional",
                )
            )
        draft_file = path / "prepared/automatic-drafts.json"
        if draft_file.exists():
            draft = json.loads(draft_file.read_text(encoding="utf-8"))
            marked = annotations(path)
            source = json.loads((path / "source.json").read_text(encoding="utf-8"))
            if (
                eligible_training_source(source)
                and draft.get("annotation_revision") == marked["revision"]
                and draft.get("source_sha256") == source["sha256"]
            ):
                for item in draft.get("segments", []):
                    segments.append(
                        dict(
                            start_ms=item["start_ms"],
                            end_ms=item["end_ms"],
                            label=item["label"],
                            layer="footwork",
                            track_id=item["track_id"],
                            origin="model",
                            suggested_by="experimental_seed_classifier",
                            status="provisional",
                            certainty="unsure",
                            note="Automatic experimental prediction; not human ground truth and not used for training.",
                        )
                    )
        return DatasetAnnotations(segments=segments, events=events).model_dump()

    @router.get("/{collection}/{clip_id}/source")
    def source_video(collection: str, clip_id: str):
        path = folder(collection, clip_id)
        record = json.loads((path / "source.json").read_text(encoding="utf-8"))
        file = path / ("source.mp4" if (path / "source.mp4").exists() else "source.video")
        if not file.is_file():
            raise HTTPException(404, "Source download is unavailable.")
        extension = Path(record["filename"]).suffix
        mime = {".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg"}.get(extension)
        return FileResponse(file, media_type=mime)

    @router.get("/{collection}/{clip_id}/poses")
    def poses(collection: str, clip_id: str):
        path = folder(collection, clip_id) / "prepared/result.json"
        if not path.is_file():
            raise HTTPException(409, "Prepare the selected athlete crop first.")
        return FileResponse(path, media_type="application/json")

    return router

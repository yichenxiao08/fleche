"""One reviewed-data reader for the trainer and the dataset readiness screen."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from fencecoach.athlete_tracking import selection_hint
from fencecoach.data_policy import eligible_source, eligible_training_source
from fencecoach.dataset_labels import DatasetAnnotations, training_track, usable_review
from fencecoach.footwork import enrich_frames
from fencecoach.gestures import ACTIVITY_LABELS, LABELS, Annotations, temporal_features

POLICY = {
    "version": "phone-training-protocol-v1",
    "minimum_windows_per_class": 150,
    "rare_class_minimums": {"fleche": 50},
    "minimum_train_athletes": 6,
    "minimum_held_out_athletes": 2,
    "minimum_source_videos_per_athlete": 3,
    "minimum_recording_sessions_per_athlete": 2,
    "minimum_camera_setups": 3,
    "minimum_independent_groups_per_class": 3,
    "split_seed": 740,
}
CORE_CLASSES = ("en_garde", "advance", "retreat", "lunge", "recovery", "other")
ISSUES = {
    "excluded_scope": "Saved footage is outside the single-fencer / single-bout MVP training scope.",
    "excluded_domain": "Source is excluded or modern fencing provenance is unconfirmed.",
    "missing_labels": "Add and review labels for the selected athlete.",
    "needs_human_review": "Watch the clip and confirm the movement labels; current labels remain drafts or unsure.",
    "stale_export": "Refresh the prepared export after the latest label review.",
    "needs_preparation": "Prepare the selected athlete's pose crop.",
    "missing_metadata": "Record the athlete, recording-session and camera-setup IDs.",
    "unknown_capture": "Confirm facing and camera motion in the review context.",
    "no_usable_windows": "No selected-class windows pass duration, visibility and track checks.",
    "invalid_source": "Source bytes or annotation data failed validation; inspect before using.",
    "ready": "Reviewed windows are available; dataset-wide gates still apply.",
}


def connected_groups(sources):
    """Keep shared athletes, identical bytes, recordings and source cohorts together."""
    parents = {}

    def root(key):
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    keys = []
    for source in sources:
        related = [("source", source["hash"]), ("cohort", source["split_group"])]
        if source.get("original_source_sha256"):
            related.append(("original", source["original_source_sha256"]))
        for field in ("athlete_id", "recording_session_id"):
            if source.get(field):
                related.append((field, source[field]))
        for key in related[1:]:
            parents[root(key)] = root(related[0])
        keys.append(related[0])
    return ["/".join(root(key)) for key in keys]


def _read_export(annotation, task, classes, window_ms, development=False):
    directory = annotation.parent
    marked = json.loads(annotation.read_text(encoding="utf-8"))
    key = "labels" if task == "gesture" else "activity_labels"
    source = {}
    if marked.get("source_collection"):
        source = json.loads((directory.parent / "source.json").read_text(encoding="utf-8"))
        if not eligible_training_source(source):
            return ("excluded_scope" if eligible_source(source) else "excluded_domain"), None
        latest_path = directory.parent / "labels.json"
        if not latest_path.is_file():
            return "needs_human_review", None
        latest = DatasetAnnotations.model_validate_json(latest_path.read_text(encoding="utf-8"))
        approved = {
            s.id: s
            for s in latest.segments
            if usable_review(s)
            and s.track_id == training_track(latest)
            and s.layer == ("footwork" if task == "gesture" else "activity")
        }
        if marked.get("annotation_revision") != latest.revision:
            return "stale_export", None
        for label in marked.get(key, []):
            original = approved.get(label.get("annotation_id"))
            if not original or any(
                label.get(field) != getattr(original, field)
                for field in (
                    "label",
                    "start_ms",
                    "end_ms",
                    "track_id",
                    "certainty",
                    "reviewed_by",
                    "exclusion_flags",
                )
            ):
                return "stale_export", None
        if approved and any(
            marked.get(field)
            != (training_track(latest) if field == "primary_track_id" else getattr(latest, field))
            for field in (
                "athlete_id",
                "recording_session_id",
                "camera_setup_id",
                "primary_track_id",
            )
        ):
            # Old draft exports still receive the more useful review message below.
            return "stale_export", None
    elif not marked.get("domain_verified"):
        return "excluded_domain", None
    if marked.get("review_status") != "human_reviewed" or marked.get("reviewer_role") not in {
        "athlete",
        "coach",
    }:
        return "needs_human_review", None
    if marked.get("label_schema_version") != "label_schema_v1" or not marked.get(key):
        return "needs_human_review", None
    Annotations.model_validate(marked)
    if any(
        label.get("certainty") != "confident"
        or label.get("exclusion_flags")
        or not label.get("reviewed_by", "").strip()
        for label in marked.get(key, [])
    ):
        return "needs_human_review", None
    if not development and not all(
        marked.get(field, "").strip().lower() not in {"", "unknown", "unreviewed", "n/a"}
        for field in ("athlete_id", "recording_session_id", "camera_setup_id")
    ):
        return "missing_metadata", None
    if not (directory / "result.json").is_file() or not (directory / "source.video").is_file():
        return "needs_preparation", None
    with (directory / "source.video").open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if marked.get("source_sha256") != digest or (source and source["sha256"] != digest):
        return "invalid_source", None
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    profile = result.get("capture_profile", {})
    if marked.get("source_collection"):
        preparation = json.loads((directory / "preparation.json").read_text(encoding="utf-8"))
        if (
            preparation.get("source_sha256") != digest
            or preparation.get("crop") != latest.crop.model_dump()
            or preparation.get("athlete_selection_hint") != selection_hint(latest.track_description)
        ):
            return "stale_export", None
        if any(
            profile.get(field) != getattr(latest, field)
            for field in ("weapon", "facing", "camera_motion")
        ):
            return "stale_export", None
    if not development and (
        profile.get("facing") not in {"left", "right"}
        or profile.get("camera_motion")
        not in {
            "fixed",
            "moving",
        }
    ):
        return "unknown_capture", None
    enrich_frames(result["frames"], result["width"], result["height"], profile)
    rows = []
    for label in marked[key]:
        if label["label"] not in classes:
            continue
        if label.get("track_id") != marked.get("primary_track_id"):
            continue
        for start in range(label["start_ms"], label["end_ms"] - window_ms + 1, window_ms // 2):
            vector = temporal_features(result["frames"], start, start + window_ms)
            if vector is not None:
                rows.append(
                    dict(
                        features=vector,
                        label=label["label"],
                        start_ms=start,
                        end_ms=start + window_ms,
                        annotation_id=label.get("annotation_id"),
                    )
                )
    if not rows:
        return "no_usable_windows", None
    metadata = dict(
        hash=digest,
        clip_id=source.get("clip_id", directory.name),
        collection=marked.get("source_collection", "uploads"),
        split_group=marked.get("split_group") or digest,
        reviewer=marked["reviewer"],
        license=marked.get("license", "unspecified"),
        annotation_revision=marked.get("annotation_revision"),
        annotation_sha256=hashlib.sha256(annotation.read_bytes()).hexdigest(),
        original_source_sha256=source.get("original_source_sha256") or digest,
        source_start_ms=source.get("source_start_ms", 0),
        capture_profile=profile,
        development_only=development,
        pose_crop=json.dumps(latest.crop.model_dump(), sort_keys=True)
        if source
        else json.dumps(result.get("crop", {}), sort_keys=True),
        **{
            field: marked[field].strip()
            for field in ("athlete_id", "recording_session_id", "camera_setup_id")
        },
    )
    return "ready", (metadata, rows)


def collect_corpus(directory: Path, task="gesture", classes=None, window_ms=750, development=False):
    if task not in {"gesture", "activity"} or window_ms not in {500, 750, 1000, 1500}:
        raise ValueError("Choose a supported task and window length.")
    classes = list(
        dict.fromkeys(classes or (CORE_CLASSES if task == "gesture" else ACTIVITY_LABELS))
    )
    allowed = LABELS if task == "gesture" else ACTIVITY_LABELS
    if len(classes) < 2 or any(label not in allowed for label in classes):
        raise ValueError("Choose at least two supported movement or activity classes.")
    records, sources, rows, seen = [], [], [], {}
    annotations = sorted(directory.rglob("annotations.json"))
    prepared_folders = {
        path.parent.parent for path in annotations if path.parent.name == "prepared"
    }
    for source_file in sorted(directory.rglob("source.json")):
        try:
            source = json.loads(source_file.read_text(encoding="utf-8"))
            if "clip_id" not in source or source_file.parent in prepared_folders:
                continue
            status = "excluded_domain" if not eligible_source(source) else "needs_preparation"
            if status != "excluded_domain" and not eligible_training_source(source):
                status = "excluded_scope"
            if status != "excluded_domain" and not (source_file.parent / "labels.json").exists():
                status = "missing_labels"
            records.append(
                dict(
                    clip_id=source["clip_id"],
                    collection=source_file.parent.parent.name,
                    status=status,
                    reason=ISSUES[status],
                    usable_windows=0,
                )
            )
        except (OSError, ValueError):
            records.append(
                dict(
                    clip_id=source_file.parent.name,
                    collection=source_file.parent.parent.name,
                    status="invalid_source",
                    reason=ISSUES["invalid_source"],
                    usable_windows=0,
                )
            )
    for annotation in annotations:
        record = dict(
            clip_id=annotation.parent.parent.name
            if annotation.parent.name == "prepared"
            else annotation.parent.name,
            collection=annotation.parent.parent.parent.name
            if annotation.parent.name == "prepared"
            else "uploads",
            usable_windows=0,
        )
        try:
            status, payload = _read_export(annotation, task, classes, window_ms, development)
        except (OSError, ValueError, KeyError, TypeError):
            status, payload = "invalid_source", None
        if payload:
            source, examples = payload
            source_index = len(sources)
            sources.append(source)
            for row in examples:
                identity = (
                    source["original_source_sha256"],
                    source["pose_crop"],
                    source["source_start_ms"] + row["start_ms"],
                    source["source_start_ms"] + row["end_ms"],
                )
                if identity in seen:
                    if seen[identity] != row["label"]:
                        status = "invalid_source"
                    continue
                seen[identity] = row["label"]
                rows.append({**row, "source_index": source_index})
                record["usable_windows"] += 1
            record.update(
                athlete_id=source["athlete_id"],
                recording_session_id=source["recording_session_id"],
                camera_setup_id=source["camera_setup_id"],
            )
        record.update(status=status, reason=ISSUES[status])
        records.append(record)
    group_ids = connected_groups(sources)
    for row in rows:
        row["group"] = group_ids[row["source_index"]]
    return dict(
        task=task, classes=classes, window_ms=window_ms, rows=rows, sources=sources, clips=records
    )


def readiness(corpus, policy=None):
    policy = policy or POLICY
    rows, sources, classes = corpus["rows"], corpus["sources"], corpus["classes"]
    counts = Counter(row["label"] for row in rows)
    athletes = defaultdict(lambda: dict(videos=set(), sessions=set(), cameras=set()))
    class_groups = defaultdict(set)
    used_sources = {row["source_index"] for row in rows}
    for index in used_sources:
        source = sources[index]
        person = athletes[source["athlete_id"]]
        person["videos"].add(source.get("original_source_sha256") or source["hash"])
        person["sessions"].add(source["recording_session_id"])
        person["cameras"].add(source["camera_setup_id"])
    for row in rows:
        class_groups[row["label"]].add(row["group"])
    checks = []

    def check(key, label, actual, required):
        checks.append(
            dict(key=key, label=label, actual=actual, required=required, passed=actual >= required)
        )

    for label in classes:
        minimum = policy["rare_class_minimums"].get(label, policy["minimum_windows_per_class"])
        check(
            f"windows:{label}",
            f"Usable reviewed {label.replace('_', ' ')} windows",
            counts[label],
            minimum,
        )
        check(
            f"groups:{label}",
            f"Independent groups with {label.replace('_', ' ')}",
            len(class_groups[label]),
            policy["minimum_independent_groups_per_class"],
        )
    check(
        "athletes",
        "Distinct athletes",
        len(athletes),
        policy["minimum_train_athletes"] + policy["minimum_held_out_athletes"],
    )
    check(
        "cameras",
        "Camera setups",
        len({camera for a in athletes.values() for camera in a["cameras"]}),
        policy["minimum_camera_setups"],
    )
    for athlete, values in sorted(athletes.items()):
        check(
            f"videos:{athlete}",
            f"Original source videos for {athlete}",
            len(values["videos"]),
            policy["minimum_source_videos_per_athlete"],
        )
        check(
            f"sessions:{athlete}",
            f"Recording sessions for {athlete}",
            len(values["sessions"]),
            policy["minimum_recording_sessions_per_athlete"],
        )
    # Invalid source records remain a blocking data-integrity problem.
    invalid = sum(c["status"] == "invalid_source" for c in corpus["clips"])
    checks.append(
        dict(
            key="integrity",
            label="Source and annotation integrity issues",
            actual=invalid,
            required=0,
            passed=invalid == 0,
        )
    )
    split = None
    if rows and all(c["passed"] for c in checks):
        labels = np.asarray([row["label"] for row in rows])
        groups = [row["group"] for row in rows]
        for train, held in GroupShuffleSplit(
            n_splits=100, test_size=0.25, random_state=policy["split_seed"]
        ).split(rows, labels, groups):
            train_people = {sources[rows[i]["source_index"]]["athlete_id"] for i in train}
            held_people = {sources[rows[i]["source_index"]]["athlete_id"] for i in held}
            if (
                set(labels[train]) == set(labels[held]) == set(classes)
                and len(train_people) >= policy["minimum_train_athletes"]
                and len(held_people) >= policy["minimum_held_out_athletes"]
                and not train_people & held_people
            ):
                split = (train.tolist(), held.tolist())
                break
    checks.append(
        dict(
            key="split",
            label="Split with separate athletes, source footage and all selected classes",
            actual=int(split is not None),
            required=1,
            passed=split is not None,
        )
    )
    report = dict(
        schema="fencecoach-training-readiness-v1",
        generated_at=datetime.now(UTC).isoformat(),
        task=corpus["task"],
        selected_classes=classes,
        window_ms=corpus["window_ms"],
        policy=policy,
        training_ready=all(c["passed"] for c in checks),
        checks=checks,
        usable_windows={label: counts[label] for label in classes},
        clip_statuses=dict(Counter(c["status"] for c in corpus["clips"])),
        clips=corpus["clips"],
        athletes={
            key: {k: len(v) for k, v in values.items()} for key, values in sorted(athletes.items())
        },
        note=(
            "Passing these project-specific collection gates permits candidate training; "
            "the targets are not fencing standards and do not establish recognition accuracy "
            "or qualify a model for deployment."
        ),
    )
    return report, split

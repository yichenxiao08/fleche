"""Extract poses for selected athlete crops and export reviewed labels for the trainer.

Provisional labels are retained for review, but are never copied into training annotations.
This offline corpus does not create athlete sessions or training minutes in the app.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from fencecoach.athlete_tracking import selection_hint
from fencecoach.data_policy import eligible_source
from fencecoach.dataset_api import DatasetAnnotations
from fencecoach.dataset_labels import SCHEMA_VERSION, training_track, usable_review
from fencecoach.footwork import enrich_frames, movement_summary
from fencecoach.gestures import LABELS
from fencecoach.settings import settings
from fencecoach.video_pipeline import PIPELINE_VERSION, analyze


class OfflineJob:
    def __init__(self, folder, crop, profile, hint=None, foreground=False):
        self.directory = folder
        self.payload = dict(source="training_corpus", crop=crop, capture_profile=profile)
        self.payload["athlete_selection_hint"] = hint
        self.payload["athlete_foreground"] = foreground
        self.progress = -1

    def get(self, _):
        return self.payload

    def update(self, _, **fields):
        self.payload.update(fields)
        progress = fields.get("progress", self.progress)
        if progress // 20 > self.progress // 20:
            print(f"  {fields.get('stage', 'Extracting poses')}: {progress}%", flush=True)
        self.progress = progress


def prepare(folder, refresh=False):
    source = json.loads((folder / "source.json").read_text(encoding="utf-8"))
    labels_path = folder / "labels.json"
    marked = json.loads(labels_path.read_text(encoding="utf-8"))
    if marked.get("source_sha256", source["sha256"]) != source["sha256"]:
        raise ValueError("Label source checksum no longer matches the selected footage.")
    annotations = DatasetAnnotations.model_validate(marked)
    target = folder / "prepared"
    target.mkdir(exist_ok=True)
    source_path = folder / ("source.mp4" if source["filename"].endswith(".mp4") else "source.video")
    with source_path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != source["sha256"]:
        raise ValueError("Source bytes no longer match the curated checksum.")
    cached_source = target / "source.video"
    with cached_source.open("rb") if cached_source.exists() else source_path.open("rb") as handle:
        cached_digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if not cached_source.exists() or cached_digest != digest:
        shutil.copyfile(source_path, target / "source.video")
    hint = selection_hint(annotations.track_description)
    fingerprint = dict(source_sha256=source["sha256"], crop=annotations.crop.model_dump())
    if hint:
        fingerprint["athlete_selection_hint"] = hint
    provenance_file = target / "preparation.json"
    previous = (
        json.loads(provenance_file.read_text(encoding="utf-8"))
        if provenance_file.exists()
        else None
    )
    profile = dict(
        facing=annotations.facing,
        weapon=annotations.weapon,
        camera_motion=annotations.camera_motion,
        initial_guard_confirmed=False,
    )
    cached_result = (
        json.loads((target / "result.json").read_text(encoding="utf-8"))
        if (target / "result.json").exists()
        else {}
    )
    outdated_pipeline = cached_result.get("pipeline_version") not in {None, PIPELINE_VERSION}
    if refresh or not cached_result or previous != fingerprint or outdated_pipeline:
        analyze(
            OfflineJob(
                folder,
                fingerprint["crop"],
                profile,
                hint,
                "foreground" in annotations.track_description.lower(),
            ),
            "prepared",
            settings.fencecoach_pose_model,
        )
        provenance_file.write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
    result_path = target / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    enrich_frames(result["frames"], result["width"], result["height"], profile)
    result.update(capture_profile=profile, footwork_summary=movement_summary(result["frames"]))
    result.update(
        source_credit=source["attribution"],
        license=source["license"],
        source_sha256=source["sha256"],
        split_group=source["split_group"],
    )
    result_path.write_text(json.dumps(result), encoding="utf-8")
    reviewed = [
        s
        for s in annotations.segments
        if usable_review(s)
        and s.layer == "footwork"
        and s.track_id == training_track(annotations)
        and s.label in LABELS
        and eligible_source(source)
    ]
    training = dict(
        label_schema_version=SCHEMA_VERSION,
        reviewer=annotations.reviewer,
        review_status="human_reviewed"
        if any(
            usable_review(s)
            and s.track_id == training_track(annotations)
            and s.layer in {"footwork", "activity"}
            for s in annotations.segments
        )
        and eligible_source(source)
        else "provisional",
        reviewer_role=annotations.reviewer_role,
        license=source["license"],
        source_credit=source["attribution"],
        source_sha256=source["sha256"],
        split_group=source["split_group"],
        athlete_id=annotations.athlete_id,
        primary_track_id=training_track(annotations),
        original_primary_track_id=annotations.primary_track_id,
        recording_session_id=annotations.recording_session_id,
        camera_setup_id=annotations.camera_setup_id,
        original_source_id=source["clip_id"],
        labels=[
            dict(
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                label=s.label,
                note=s.note,
                annotation_id=s.id,
                reviewed_by=s.reviewed_by,
                certainty=s.certainty,
                exclusion_flags=s.exclusion_flags,
                track_id=s.track_id,
            )
            for s in reviewed
        ],
        activity_labels=[
            dict(
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                label=s.label,
                note=s.note,
                annotation_id=s.id,
                reviewed_by=s.reviewed_by,
                certainty=s.certainty,
                exclusion_flags=s.exclusion_flags,
                track_id=s.track_id,
            )
            for s in annotations.segments
            if s.layer == "activity"
            and usable_review(s)
            and s.track_id == training_track(annotations)
            and eligible_source(source)
        ],
        event_markers=[
            e.model_dump()
            for e in annotations.events
            if usable_review(e)
            and e.track_id == training_track(annotations)
            and eligible_source(source)
        ],
        annotation_revision=annotations.revision,
        source_collection=folder.parent.name,
        training_domain=source.get("training_domain", "unreviewed"),
        training_eligible=eligible_source(source),
        curation_sha256=source.get("curation_sha256"),
    )
    (target / "annotations.json").write_text(json.dumps(training, indent=2), encoding="utf-8")
    (target / "draft-labels.json").write_text(json.dumps(marked, indent=2), encoding="utf-8")
    print(
        json.dumps(
            dict(
                clip=source["clip_id"],
                tracked=result["tracked_frames"],
                sampled=result["sampled_frames"],
                reviewed_training_intervals=len(reviewed),
                provisional_intervals=sum(s.status == "provisional" for s in annotations.segments),
            )
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/training/mit-ocw"))
    parser.add_argument("--clips", nargs="+", required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    for clip in args.clips:
        folder = (args.data / clip).resolve()
        if not folder.is_relative_to(args.data.resolve()):
            raise ValueError("Choose a clip inside the dataset.")
        print(f"Preparing {clip}", flush=True)
        prepare(folder, args.refresh)


if __name__ == "__main__":
    main()

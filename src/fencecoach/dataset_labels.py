"""Versioned annotation records; proposed observations never imply human review."""

from __future__ import annotations

import json
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, model_validator

from fencecoach.video_jobs import Crop

SCHEMA_VERSION = "label_schema_v1"
ONTOLOGY = {
    "footwork": (
        "en_garde",
        "advance",
        "retreat",
        "lunge",
        "recovery",
        "fleche",
        "jump_forward",
        "jump_back",
        "bounce",
        "shuffle",
        "other",
        "unknown",
    ),
    "activity": ("setup", "exercise", "between_reps", "rest", "exit"),
    "bladework": ("extension", "thrust", "parry", "other", "unknown"),
    "tactics": ("attack", "counterattack", "riposte", "remise", "other", "unknown"),
}
TRAINABLE_FOOTWORK_LABELS = tuple(label for label in ONTOLOGY["footwork"] if label != "unknown")
EVENT_KINDS = ("arm_motion_onset", "foot_launch", "landing", "stance_peak", "recovery_complete")
EXCLUSION_FLAGS = (
    "occluded",
    "out_of_frame",
    "ambiguous_athlete",
    "camera_moving",
    "non_modern",
    "unusable",
)
Exclusion = Literal[
    "occluded", "out_of_frame", "ambiguous_athlete", "camera_moving", "non_modern", "unusable"
]


class Reviewable(BaseModel):
    id: str = Field(default="", max_length=100)
    track_id: str = Field(min_length=1, max_length=60)
    status: Literal["provisional", "reviewed", "rejected"] = "provisional"
    origin: Literal["assistant_visual", "human", "published_dataset", "heuristic", "model"] = (
        "human"
    )
    suggested_by: str = Field(default="", max_length=100)
    reviewed_by: str = Field(default="", max_length=100)
    reviewed_at: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    certainty: Literal["confident", "unsure"] = "unsure"
    exclusion_flags: list[Exclusion] = Field(default_factory=list, max_length=6)
    boundary_uncertainty_ms: int = Field(default=250, ge=0, le=5000)
    suggestion_disagreement: bool = False
    note: str = Field(default="", max_length=500)


class DatasetSegment(Reviewable):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    layer: Literal["footwork", "activity", "bladework", "tactics"]
    label: str

    @model_validator(mode="after")
    def validate_label(self):
        if self.end_ms <= self.start_ms or self.label not in ONTOLOGY[self.layer]:
            raise ValueError("Choose a supported label and an ordered interval.")
        return self


class DatasetEvent(Reviewable):
    time_ms: int = Field(ge=0)
    kind: Literal["arm_motion_onset", "foot_launch", "landing", "stance_peak", "recovery_complete"]


class DatasetAnnotations(BaseModel):
    schema_version: Literal["legacy_v0", "label_schema_v1"] = "legacy_v0"
    revision: int = Field(default=0, ge=0)
    reviewer: str = Field(default="unreviewed", min_length=1, max_length=100)
    reviewer_role: Literal["assistant", "athlete", "coach"] = "athlete"
    primary_track_id: str = Field(default="primary", min_length=1, max_length=60)
    athlete_id: str = Field(default="", max_length=100)
    recording_session_id: str = Field(default="", max_length=100)
    camera_setup_id: str = Field(default="", max_length=100)
    track_description: str = Field(default="", max_length=500)
    weapon: Literal["unknown", "foil", "epee", "sabre"] = "unknown"
    facing: Literal["unknown", "left", "right"] = "unknown"
    camera_motion: Literal["unknown", "fixed", "moving"] = "unknown"
    opponent_visible: bool = False
    crop: Crop = Field(default_factory=Crop)
    segments: list[DatasetSegment] = Field(default_factory=list, max_length=1000)
    events: list[DatasetEvent] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def legacy_records(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        legacy = value.get("schema_version", "legacy_v0") == "legacy_v0"
        for field in ("segments", "events"):
            converted = []
            for index, original in enumerate(value.get(field, [])):
                if not isinstance(original, dict):
                    converted.append(original)
                    continue
                item = dict(original)
                if not item.get("id"):
                    identity = json.dumps(item, sort_keys=True)
                    item["id"] = uuid5(NAMESPACE_URL, f"fencecoach:{field}:{index}:{identity}").hex
                if not item.get("suggested_by") and item.get("origin", "human") != "human":
                    item["suggested_by"] = item["origin"]
                # Preserve historical attribution, but leave confidence unconfirmed.
                if legacy and item.get("status") == "reviewed" and not item.get("reviewed_by"):
                    item["reviewed_by"] = value.get("reviewer", "unreviewed")
                converted.append(item)
            value[field] = converted
        return value

    @model_validator(mode="after")
    def validate_review(self):
        all_records = [*self.segments, *self.events]
        if len({r.id for r in all_records}) != len(all_records):
            raise ValueError("Every interval and event must have a unique ID.")
        for item in all_records:
            if item.status == "reviewed" and (
                self.reviewer_role == "assistant"
                or self.reviewer.strip().lower() in {"", "unreviewed"}
                or item.reviewed_by.strip().lower() in {"", "unreviewed"}
            ):
                raise ValueError("Reviewed labels require an identified human reviewer per record.")
        ordered = sorted(
            (s for s in self.segments if s.status != "rejected"),
            key=lambda s: (s.track_id, s.layer, s.start_ms),
        )
        for segment in ordered:
            if (
                segment.layer == "tactics"
                and segment.status == "reviewed"
                and (self.reviewer_role != "coach" or not self.opponent_visible)
            ):
                raise ValueError(
                    "Tactical ground truth requires a coach and visible opponent context."
                )
        return self

    def validate_no_overlapping_segments(self):
        ordered = sorted(
            (segment for segment in self.segments if segment.status != "rejected"),
            key=lambda segment: (segment.track_id, segment.layer, segment.start_ms),
        )
        for first, second in zip(ordered, ordered[1:]):
            if (
                first.track_id == second.track_id
                and first.layer == second.layer
                and first.end_ms > second.start_ms
            ):
                raise ValueError("Labels overlap within the same athlete and layer.")


def usable_review(item):
    """Label eligibility only; pose quality and independent-data gates still apply."""
    return (
        item.status == "reviewed"
        and bool(item.reviewed_by.strip())
        and item.reviewed_by.strip().lower() != "unreviewed"
        and item.certainty == "confident"
        and not item.exclusion_flags
    )


def training_track(annotations):
    """Resolve a legacy default track only for a uniquely named, cropped athlete.

    This is an export alias, not an athlete identity claim or label edit.
    Multiple tracks and full-frame footage always require explicit selection.
    """
    tracks = {s.track_id for s in annotations.segments if s.status != "rejected"}
    cropped = annotations.crop.model_dump() != {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    if (
        annotations.primary_track_id == "primary"
        and "primary" not in tracks
        and len(tracks) == 1
        and cropped
    ):
        return next(iter(tracks))
    return annotations.primary_track_id

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fencecoach.dataset_api import dataset_router
from fencecoach.dataset_labels import DatasetAnnotations, usable_review


def draft(**fields):
    return (
        dict(start_ms=0, end_ms=1000, layer="footwork", label="lunge", track_id="primary") | fields
    )


class DatasetReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / "footwork-clips" / "sample"
        self.clip.mkdir(parents=True)
        digest = hashlib.sha256(b"example source").hexdigest()
        self.source = dict(
            clip_id="sample",
            duration_ms=5000,
            sha256=digest,
            training_eligible=True,
            training_domain="modern_fencing_footwork_drill",
            curation_sha256=digest,
            split_group="recording-1",
            filename="source.mp4",
            license="test fixture",
            attribution="test fixture",
        )
        (self.clip / "source.json").write_text(json.dumps(self.source), encoding="utf-8")
        app = FastAPI()
        app.include_router(dataset_router(self.root))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = "/api/datasets/footwork-clips/sample"

    def test_legacy_drafts_have_stable_ids_without_becoming_ground_truth(self):
        old = dict(
            reviewer="assistant",
            reviewer_role="assistant",
            segments=[draft(origin="assistant_visual")],
        )
        a, b = DatasetAnnotations.model_validate(old), DatasetAnnotations.model_validate(old)
        self.assertEqual(a.segments[0].id, b.segments[0].id)
        self.assertEqual(a.segments[0].suggested_by, "assistant_visual")
        self.assertFalse(usable_review(a.segments[0]))
        with self.assertRaises(ValidationError):
            DatasetAnnotations.model_validate(
                {**old, "segments": [draft(status="reviewed", reviewed_by="coach")]}
            )

    def test_human_attribution_and_suggestion_survive_later_reviewer_save(self):
        seed = DatasetAnnotations(segments=[draft(origin="heuristic")]).model_dump()
        first = self.client.put(self.url + "/labels", json=seed).json()
        first.update(
            schema_version="label_schema_v1", reviewer="Reviewer A", athlete_id="athlete-01"
        )
        first["segments"][0].update(
            status="reviewed", certainty="confident", reviewed_by="Reviewer A"
        )
        accepted = self.client.put(self.url + "/labels", json=first)
        self.assertEqual(accepted.status_code, 200)
        payload = accepted.json()
        stamp = payload["segments"][0]["reviewed_at"]
        self.assertTrue(stamp)
        payload["reviewer"] = "Reviewer B"
        payload["segments"][0].update(origin="human", suggested_by="", reviewed_by="Reviewer B")
        saved = self.client.put(self.url + "/labels", json=payload).json()
        item = saved["segments"][0]
        self.assertEqual((item["origin"], item["suggested_by"]), ("heuristic", "heuristic"))
        self.assertEqual((item["reviewed_by"], item["reviewed_at"]), ("Reviewer A", stamp))
        self.assertEqual(self.client.put(self.url + "/labels", json=payload).status_code, 409)

    def test_uncertain_and_excluded_reviews_do_not_count_as_usable(self):
        intervals = []
        for i, extra in enumerate(({}, {"certainty": "unsure"}, {"exclusion_flags": ["occluded"]})):
            item = draft(status="reviewed", reviewed_by="Reviewer", certainty="confident")
            item.update(start_ms=i * 1000, end_ms=(i + 1) * 1000, **extra)
            intervals.append(item)
        payload = DatasetAnnotations(
            schema_version="label_schema_v1",
            reviewer="Reviewer",
            athlete_id="athlete-01",
            recording_session_id="day-1",
            camera_setup_id="side-1",
            segments=intervals,
        ).model_dump()
        self.assertEqual(self.client.put(self.url + "/labels", json=payload).status_code, 200)
        readiness = self.client.get("/api/datasets").json()["training_readiness"]
        self.assertEqual(readiness["classes"]["lunge"]["reviewed_intervals"], 1)
        self.assertEqual(readiness["athletes"]["athlete-01"]["sessions"], 1)

    def test_events_are_separate_and_bounded_by_the_video(self):
        payload = DatasetAnnotations(
            segments=[draft()], events=[dict(time_ms=6000, kind="landing", track_id="primary")]
        ).model_dump()
        self.assertEqual(self.client.put(self.url + "/labels", json=payload).status_code, 422)
        payload["events"][0]["time_ms"] = 500
        self.assertEqual(self.client.put(self.url + "/labels", json=payload).status_code, 200)
        stored = self.client.get(self.url + "/labels").json()
        self.assertEqual(len(stored["segments"]), 1)
        self.assertEqual(stored["events"][0]["kind"], "landing")

    def test_movement_overlap_rejected_but_activity_layer_may_overlap(self):
        annotations = DatasetAnnotations(segments=[draft(), draft(label="advance")])
        with self.assertRaises(ValueError):
            annotations.validate_no_overlapping_segments()
        DatasetAnnotations(
            segments=[
                draft(),
                dict(
                    start_ms=0, end_ms=1000, layer="activity", label="exercise", track_id="primary"
                ),
            ]
        )

    def test_export_filters_unsure_excluded_and_wrong_track_labels(self):
        path = Path(__file__).parents[1] / "scripts" / "prepare_fencing_data.py"
        spec = importlib.util.spec_from_file_location("prepare_fencing_data", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        good = draft(status="reviewed", reviewed_by="Reviewer", certainty="confident")
        items = [
            good,
            {**good, "start_ms": 1000, "end_ms": 2000, "certainty": "unsure"},
            {**good, "start_ms": 2000, "end_ms": 3000, "exclusion_flags": ["camera_moving"]},
            {**good, "track_id": "opponent"},
        ]
        annotations = DatasetAnnotations(
            schema_version="label_schema_v1", reviewer="Reviewer", athlete_id="a01", segments=items
        )
        (self.clip / "labels.json").write_text(annotations.model_dump_json(), encoding="utf-8")
        (self.clip / "source.mp4").write_bytes(b"example source")
        prepared = self.clip / "prepared"
        prepared.mkdir()
        (prepared / "preparation.json").write_text(
            json.dumps(
                dict(source_sha256=self.source["sha256"], crop=annotations.crop.model_dump())
            ),
            encoding="utf-8",
        )
        (prepared / "result.json").write_text(
            json.dumps(dict(frames=[], width=640, height=480, tracked_frames=0, sampled_frames=0)),
            encoding="utf-8",
        )
        module.prepare(self.clip)
        exported = json.loads((prepared / "annotations.json").read_text())
        self.assertEqual(len(exported["labels"]), 1)
        self.assertEqual(exported["labels"][0]["reviewed_by"], "Reviewer")
        self.assertEqual(exported["athlete_id"], "a01")

    def test_stale_export_cannot_train_after_label_review_changes(self):
        path = Path(__file__).parents[1] / "scripts" / "train_gestures.py"
        spec = importlib.util.spec_from_file_location("train_gestures", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        annotations = DatasetAnnotations(
            revision=2,
            schema_version="label_schema_v1",
            reviewer="Reviewer",
            athlete_id="a01",
            segments=[draft(status="reviewed", reviewed_by="Reviewer", certainty="confident")],
        )
        (self.clip / "labels.json").write_text(annotations.model_dump_json(), encoding="utf-8")
        prepared = self.clip / "prepared"
        prepared.mkdir()
        (prepared / "source.video").write_bytes(b"example source")
        (prepared / "result.json").write_text("{}", encoding="utf-8")
        (prepared / "annotations.json").write_text(
            json.dumps(
                dict(
                    source_collection="footwork-clips",
                    annotation_revision=1,
                    labels=[
                        dict(
                            annotation_id=annotations.segments[0].id,
                            start_ms=0,
                            end_ms=1000,
                            label="lunge",
                        )
                    ],
                )
            ),
            encoding="utf-8",
        )
        destination = self.root / "should-not-exist.json"
        with (
            patch("sys.argv", [str(path), "--data", str(self.root), "--output", str(destination)]),
            self.assertRaisesRegex(SystemExit, "Training stopped before model fitting"),
        ):
            module.main()
        self.assertFalse(destination.exists())
        report = json.loads((self.root / "readiness-gesture.json").read_text())
        self.assertEqual(report["clip_statuses"].get("stale_export"), 1)


if __name__ == "__main__":
    unittest.main()

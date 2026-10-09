"""Automatic offline preparation, candidate fitting and isolated draft predictions.

Accepted annotations are never overwritten. Experimental predictions are kept
in separate sidecars and never recycled as human ground truth.
"""

import hashlib
import json
import logging
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fencecoach.data_policy import eligible_training_source
from fencecoach.dataset_labels import DatasetAnnotations, training_track, usable_review
from fencecoach.gestures import classify_windows
from fencecoach.movement_timeline import decode_gestures
from fencecoach.training_data import collect_corpus, readiness
from fencecoach.video_pipeline import PIPELINE_VERSION

logger = logging.getLogger(__name__)


class AutomaticTraining:
    def __init__(self, root, project=None):
        self.root = Path(root).resolve()
        self.project = Path(project or Path(__file__).resolve().parents[2])
        self.directory = self.root / "automation"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def status(self):
        try:
            return json.loads((self.directory / "status.json").read_text())
        except (OSError, ValueError):
            return {"status": "waiting", "stage": "Automatic training starts with the server."}

    def write(self, **fields):
        payload = {**self.status(), **fields, "updated_at": datetime.now(UTC).isoformat()}
        target = self.directory / f"status-{uuid4().hex}.tmp"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        target.replace(self.directory / "status.json")

    def fingerprint(self):
        digest = hashlib.sha256(("automatic-training-v3:" + PIPELINE_VERSION).encode())
        for path in sorted(self.root.glob("*/*/*.json")):
            if path.name in {"labels.json", "source.json"}:
                digest.update(str(path.relative_to(self.root)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def command(self, script, *args):
        result = subprocess.run(
            [sys.executable, str(self.project / "scripts" / script), *map(str, args)],
            cwd=self.project,
            capture_output=True,
            text=True,
            timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-2000:])
        return result.stdout

    def run_once(self):
        # One process holds the lease through the complete run. SQLite releases it
        # even if the server dies; saved inputs trigger a fresh run on restart.
        with closing(sqlite3.connect(self.directory / "worker.sqlite", timeout=0)) as lease, lease:
            lease.execute("CREATE TABLE IF NOT EXISTS lease (id INTEGER)")
            lease.execute("BEGIN IMMEDIATE")
            fingerprint = self.fingerprint()
            if self.status().get("completed_fingerprint") == fingerprint:
                return
            self.write(status="running", stage="Refreshing pose exports", errors=[], promoted=False)
            prepared, errors = [], []
            for source_path in sorted(self.root.glob("*/*/source.json")):
                if self.stop.is_set():
                    return
                folder = source_path.parent
                try:
                    source = json.loads(source_path.read_text())
                    labels_path = folder / "labels.json"
                    if not eligible_training_source(source) or not labels_path.exists():
                        continue
                    labels = DatasetAnnotations.model_validate_json(labels_path.read_text())
                    if not any(usable_review(s) for s in labels.segments):
                        continue
                    self.write(stage=f"Preparing {folder.name}")
                    self.command(
                        "prepare_fencing_data.py", "--data", folder.parent, "--clips", folder.name
                    )
                    prepared.append(str(folder.relative_to(self.root)))
                except Exception as exc:
                    errors.append({"clip": folder.name, "reason": str(exc)})
            self.write(stage="Training experimental gesture model", errors=errors)
            candidate = self.project / "models" / "gestures-seed-candidate.json"
            # Reject failed preparation rather than fit against inconsistent inputs.
            if errors:
                raise RuntimeError("Preparation failed for one or more clips; see errors.")
            self.command("train_seed_gestures.py", "--data", self.root, "--output", candidate)
            model = json.loads(candidate.read_text())
            self.write(stage="Evaluating production readiness")
            report, _ = readiness(collect_corpus(self.root))
            (self.directory / "readiness.json").write_text(json.dumps(report, indent=2))
            promoted = False
            if report["training_ready"]:
                # The strict trainer makes the separate performance decision and
                # preserves the previous active model if promotion is refused.
                outcome = subprocess.run(
                    [
                        sys.executable,
                        str(self.project / "scripts/train_gestures.py"),
                        "--data",
                        str(self.root),
                        "--promote",
                    ],
                    cwd=self.project,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                promoted = outcome.returncode == 0
            self.write(stage="Generating isolated automatic movement drafts")
            suggestions = 0
            for result_path in sorted(self.root.glob("*/*/prepared/result.json")):
                try:
                    folder = result_path.parent.parent
                    source = json.loads((folder / "source.json").read_text())
                    if not eligible_training_source(source):
                        continue
                    labels = DatasetAnnotations.model_validate_json(
                        (folder / "labels.json").read_text()
                    )
                    preparation = json.loads((result_path.parent / "preparation.json").read_text())
                    if preparation.get("crop") != labels.crop.model_dump():
                        continue
                    result = json.loads(result_path.read_text())
                    windows, _ = classify_windows(
                        result["frames"], candidate, allow_development=True
                    )
                    # Very conservative score filter; scores are not calibrated.
                    windows = [
                        {**w, "label": w["label"] if w["model_score"] >= 0.90 else "uncertain"}
                        for w in windows
                    ]
                    intervals = decode_gestures(windows, source["duration_ms"])
                    track = training_track(labels)
                    proposals = []
                    for item in intervals:
                        if any(
                            s.status != "rejected"
                            and s.layer == "footwork"
                            and s.track_id == track
                            and s.start_ms < item["end_ms"]
                            and s.end_ms > item["start_ms"]
                            for s in labels.segments
                        ):
                            continue
                        proposals.append({**item, "track_id": track, "status": "provisional"})
                    sidecar = {
                        "model_version": model["version"],
                        "source_sha256": source["sha256"],
                        "annotation_revision": labels.revision,
                        "development_only": True,
                        "used_for_training": False,
                        "segments": proposals,
                    }
                    (result_path.parent / "automatic-drafts.json").write_text(
                        json.dumps(sidecar, indent=2)
                    )
                    suggestions += len(proposals)
                except (OSError, ValueError, KeyError) as exc:
                    errors.append({"clip": result_path.parent.parent.name, "reason": str(exc)})
            self.write(
                status="completed",
                stage="Automatic training complete",
                completed_fingerprint=fingerprint,
                prepared_clips=prepared,
                usable_windows=sum(model["class_windows"].values()),
                class_windows=model["class_windows"],
                evaluation=model["evaluation"],
                automatic_drafts=suggestions,
                promoted=promoted,
                errors=errors,
                note="Experimental drafts stay separate. No human review is required to run this pipeline.",
            )
            lease.commit()

    def loop(self):
        while not self.stop.is_set():
            try:
                self.run_once()
            except sqlite3.OperationalError:
                pass  # Another server process owns the run.
            except Exception as exc:
                logger.exception("Automatic training failed")
                self.write(status="failed", stage="Automatic training stopped", error=str(exc))
            self.wake.wait(30)
            self.wake.clear()

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True, name="automatic-training")
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

"""Durable, source-versioned per-video evidence reused before provider calls.

The cache contains evaluator output, including abstentions. It never adds evidence
to a rejected rep. Source fingerprints cover both the athlete clip and every
candidate reference so reviewed edits cannot revive stale measurements.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from fencecoach.feedback_learning import corrected_windows
from fencecoach.reference_comparison import attach_reference_comparisons
from fencecoach.technique import evaluate_lunges

logger = logging.getLogger(__name__)
CACHE_VERSION = "coaching-evidence-v1"
CACHE_FILENAME = "coaching-evidence-cache.json"
_SOURCE_FILES = (
    "technique.py",
    "phase_metrics.py",
    "lunge_benchmarks.py",
    "lunge_benchmarks.json",
    "feedback_learning.py",
    "quality.py",
    "reference_comparison.py",
)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _file_fingerprint(path: Path, content: bytes | None = None):
    if not path.is_file():
        return {"available": False}
    stat = path.stat()
    return {
        "available": True,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": _digest(path.read_bytes() if content is None else content),
    }


def _implementation_fingerprint():
    root = Path(__file__).parent
    # Include helpers without their own VERSION constant. A deployed evaluator
    # change must invalidate old values even when result.json did not change.
    return {name: _file_fingerprint(root / name) for name in _SOURCE_FILES}


def _reference_dependencies(reviews, directory, jobs):
    dependencies = []
    for review in reviews:
        job_id = review["job_id"]
        job = jobs.get(job_id)
        dependencies.append(
            {
                "review": review,
                "job_available": bool(job),
                "capture_profile": (job or {}).get("capture_profile", {}),
                "reviewed_windows": (job or {}).get("reviewed_windows", []),
                "result": _file_fingerprint(directory / job_id / "result.json"),
            }
        )
    return dependencies


class _ReferenceSnapshot:
    """Keep comparison selection consistent with the review order in the key."""

    def __init__(self, reviews):
        self.reviews = reviews

    def list_reference_reviews(self):
        return self.reviews


def _read_cache(path, key):
    try:
        cached = json.loads(path.read_bytes())
        evaluation = cached["evaluation"]
        if (
            cached["version"] == CACHE_VERSION
            and cached["key"] == key
            and isinstance(evaluation, dict)
            and cached["evaluation_sha256"] == _digest(_json_bytes(evaluation))
        ):
            return evaluation
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _write_cache(path, key, evaluation):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(
            _json_bytes(
                {
                    "version": CACHE_VERSION,
                    "key": key,
                    "evaluation_sha256": _digest(_json_bytes(evaluation)),
                    "evaluation": evaluation,
                }
            )
        )
        os.replace(temporary, path)
    except OSError:
        # Read-only restored artifacts still permit coaching; caching is optional.
        logger.warning("Could not persist coaching evidence cache at %s", path, exc_info=True)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def coaching_evaluation(job_id, capture_profile, reviewed_feedback, directory, repository, jobs):
    """Reuse measured evidence across requests and process restarts.

    Raw content hashes deliberately supplement mtimes, including on references.
    The review payload includes revision/status as well as corrected bookmarks;
    profile changes and removed/added reference sets also invalidate the cache.
    """
    path = directory / job_id / "result.json"
    if not path.is_file():
        return {}
    content = path.read_bytes()
    result = json.loads(content)
    job = jobs.get(job_id) or {}
    windows = job.get("reviewed_windows") or result.get("candidates", [])
    if reviewed_feedback:
        windows = corrected_windows(reviewed_feedback, windows)
    reviews = repository.list_reference_reviews()
    key = _digest(
        _json_bytes(
            {
                "version": CACHE_VERSION,
                "implementation": _implementation_fingerprint(),
                "job_id": job_id,
                "result": _file_fingerprint(path, content),
                "capture_profile": capture_profile,
                "windows": windows,
                "reviewed_feedback": reviewed_feedback,
                "references": _reference_dependencies(reviews, directory, jobs),
            }
        )
    )
    cache_path = path.with_name(CACHE_FILENAME)
    cached = _read_cache(cache_path, key)
    if cached is not None:
        return cached
    evaluation = evaluate_lunges(result, windows, capture_profile)
    evaluation = attach_reference_comparisons(
        evaluation,
        {**job, "job_id": job_id, "capture_profile": capture_profile},
        directory,
        _ReferenceSnapshot(reviews),
        jobs,
    )
    _write_cache(cache_path, key, evaluation)
    return evaluation

"""Measured regression results; unavailable evidence stays null, never a fabricated score."""

import hashlib
import json

from fencecoach.dataset_labels import DatasetAnnotations, training_track, usable_review
from fencecoach.quality import assess_quality


def rep_scores(result, labels):
    target = training_track(labels)
    reviewed = [
        s
        for s in labels.segments
        if usable_review(s) and s.layer == "footwork" and s.track_id == target
    ]
    truth = [s for s in reviewed if s.label == "lunge"]
    predictions = []
    for c in result.get("candidates", []):
        if c.get("movement_label") != "lunge":
            continue
        start, end = c.get("onset_ms", c["start_ms"]), c["start_ms"]
        if end <= start:
            continue
        coverage = sum(max(0, min(end, s.end_ms) - max(start, s.start_ms)) for s in reviewed) / (
            end - start
        )
        if coverage >= 0.8:
            predictions.append(c)
    used, hits, errors = set(), 0, []
    for c in predictions:
        matches = [
            (i, s)
            for i, s in enumerate(truth)
            if i not in used
            and s.start_ms - s.boundary_uncertainty_ms
            <= c["start_ms"]
            <= s.end_ms + s.boundary_uncertainty_ms
        ]
        if matches:
            i, s = min(matches, key=lambda pair: abs(c["start_ms"] - pair[1].end_ms))
            used.add(i)
            hits += 1
            errors.append(abs(c.get("onset_ms", c["start_ms"]) - s.start_ms))
    return {
        "reviewed_lunges": len(truth),
        "scored_predictions": len(predictions),
        "matched": hits,
        "precision": hits / len(predictions) if predictions else None,
        "recall": hits / len(truth) if truth else None,
        "onset_error_ms": errors,
        "method": "Peak in reviewed lunge interval with boundary uncertainty; predictions scored only in >=80% reviewed spans.",
    }


def video_regression(project, manifest, reprocess=False, sheets=True):
    from fencecoach.contact_sheets import generate_contact_sheet

    if reprocess:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "prepare", project / "scripts/prepare_fencing_data.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    results = []
    for item in manifest["clips"]:
        folder = project / "data/training" / item["path"]
        try:
            source = json.loads((folder / "source.json").read_text())
            if source["sha256"] != item["source_sha256"]:
                raise ValueError("Golden source checksum changed.")
            source_file = next((p for p in folder.glob("source.*") if p.suffix != ".json"), None)
            if source_file is None:
                raise ValueError("Golden source video is missing.")
            with source_file.open("rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual_hash != item["source_sha256"]:
                raise ValueError("Golden video bytes differ from the pinned checksum.")
            if reprocess:
                module.prepare(folder)
            result = json.loads((folder / "prepared/result.json").read_text())
            labels = DatasetAnnotations.model_validate_json((folder / "labels.json").read_text())
            if labels.revision != item["label_revision"]:
                raise ValueError(
                    "Golden labels changed; explicitly version the manifest before comparing results."
                )
            quality = assess_quality(result)
            sheet = generate_contact_sheet(result, folder / "prepared") if sheets else None
            results.append(
                {
                    "clip": item["path"],
                    "quality": quality,
                    "pipeline_version": result.get("pipeline_version"),
                    "sampled": result["sampled_frames"],
                    "tracked": result["tracked_frames"],
                    "rep_scores": rep_scores(result, labels),
                    "self_consistency": draft_agreement(result),
                    "contact_sheet": str(sheet.relative_to(project)) if sheet else None,
                }
            )
        except Exception as exc:
            results.append({"clip": item["path"], "error": str(exc)})
    return results


def draft_agreement(result):
    """A disagreement queue, never pseudo ground truth."""
    drafts = result.get("gestures", [])
    uncertain = []
    compared = 0
    for candidate in result.get("candidates", []):
        peak = candidate["start_ms"]
        matching = [
            d for d in drafts if d.get("start_ms", peak + 1) <= peak <= d.get("end_ms", peak - 1)
        ]
        if not matching:
            continue
        compared += 1
        if any(d.get("label") != candidate.get("movement_label") for d in matching):
            uncertain.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "peak_ms": peak,
                    "rules": candidate.get("movement_label"),
                    "classifier_drafts": [d.get("label") for d in matching],
                }
            )
    return {
        "compared": compared,
        "disagreements": uncertain,
        "note": "Agreement is correlated model evidence, not a reviewed label; never auto-accepted.",
    }


def render_report(data):
    lines = [
        "# FenceCoach Benchmarks",
        "",
        "Generated from recorded results. Missing results are not success claims.",
        "",
        "## Video regression",
        "",
        "| Clip | QA | Tracking coverage | Lunge precision | Lunge recall |",
        "|---|---|---:|---:|---:|",
    ]

    def percent(value):
        return "not measured" if value is None else f"{100 * value:.1f}%"

    for clip in data.get("video", []):
        if "error" in clip:
            lines.append(f"| {clip['clip']} | error: {clip['error']} | — | — | — |")
            continue
        scores = clip["rep_scores"]
        lines.append(
            f"| {clip['clip']} | {clip['quality']['verdict']} | {percent(clip['quality']['measurements']['tracking_coverage'])} | {percent(scores['precision'])} | {percent(scores['recall'])} |"
        )
    lines += [
        "",
        "Coverage is landmark usability, not correct-athlete accuracy. Rep scores use partially reviewed intervals and permissive boundary matching; they are not general action-recognition accuracy.",
        "Regression baseline is explicit; a passing engineering regression is not proof that a clip is supported or correctly coached.",
        "",
        "## Coach model comparison",
        "",
        "| Model | Answers | Evidence traceability | Unsupported-claim flags | p50 / p95 ms | Cost USD |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in data.get("coach_models", []):
        if row.get("unavailable"):
            lines.append(f"| {row['model']} | unavailable: {row['unavailable']} | — | — | — | — |")
        else:
            lines.append(
                f"| {row['model']} | {row['answers']} | {percent(row['traceability_rate'])} | {percent(row['unsupported_claim_flag_rate'])} | {row['p50_ms']:.0f} / {row['p95_ms']:.0f} | {row.get('cost_usd') if row.get('cost_usd') is not None else 'unknown'} |"
            )
    lines += [
        "",
        "Unsupported-claim flags are automated heuristics, not expert ratings. Local provider cost is zero API fees; hardware/energy cost is not included.",
        "Traceability checks reference IDs and explicit measurement numbers; citation presence alone is not semantic grounding. Topic and answer-shape checks below are keyword proxies, not human usefulness ratings.",
        "",
        "```json",
        json.dumps(
            [
                {
                    k: row.get(k)
                    for k in (
                        "model",
                        "evidence_citation_coverage",
                        "question_topic_rate",
                        "assessment_shape_proxy_rate",
                        "grounding_replacement_rate",
                        "failures",
                        "first_text_samples",
                        "first_text_p50_ms",
                        "first_text_p95_ms",
                    )
                }
                for row in data.get("coach_models", [])
                if not row.get("unavailable")
            ],
            indent=2,
        ),
        "```",
        "",
        "First-text latency measures the first checked text callback; it excludes browser polling/render time and missing callbacks. Full-answer latency is reported in the model table.",
        "",
        "## VLM versus pose evidence",
        "",
        "```json",
        json.dumps(
            {
                k: v
                for k, v in data.get(
                    "vlm",
                    {
                        "status": "not_run",
                        "reason": "Requires configured vision models and independently answered technique questions.",
                    },
                ).items()
                if k not in {"pose_baseline", "models"}
            },
            indent=2,
        ),
        "```",
        "",
        "Full question-level pose proxies and any executed vision answers are saved in `data/evals/vision.json`. No technique accuracy is available without independent references.",
        "",
        "## Flèche beta",
        "",
        "Precision and recall are not measured until reviewed flèche examples and negatives exist. Lean, foot crossing, travel, and timing are image-plane proxies; end-of-action balance is not directly measured.",
        "",
        "## UI, MCP, and tracing",
        "",
        "```json",
        json.dumps(data.get("integration", {}), indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)

"""Bedrock VLM comparison harness. Never use pose-derived answers as independent truth."""

import argparse
import io
import json
import time
from pathlib import Path

from fencecoach.dataset_labels import DatasetAnnotations, training_track, usable_review


def cases(project):
    manifest = json.loads((project / "evals/golden.json").read_text())
    items = []
    for clip in manifest["clips"]:
        folder = project / "data/training" / clip["path"]
        labels = DatasetAnnotations.model_validate_json((folder / "labels.json").read_text())
        reviewed = [
            s
            for s in labels.segments
            if usable_review(s) and s.layer == "footwork" and s.track_id == training_track(labels)
        ]
        for s in reviewed[:2]:
            items.append(
                {
                    "id": f"{clip['path']}:{s.start_ms}-{s.end_ms}",
                    "clip": clip["path"],
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "track_id": s.track_id,
                    "question": f"Which movement is performed by the selected fencer ({s.track_id}) in this interval? Use the saved footwork taxonomy; reply with one label or unknown. Taxonomy: advance, retreat, lunge, recovery, bounce, fleche, en_garde, jump_forward, jump_backward, other.",
                    "reference": s.label,
                    "reference_type": "saved_human_footwork_label",
                    "label_revision": labels.revision,
                }
            )
    # Technique questions remain ungraded until independent answers exist.
    for clip in manifest["clips"]:
        for question in (
            "Does the front knee pass the front toe at the lunge peak?",
            "Which complete repetition has the slowest recovery?",
            "Does weapon-arm extension begin before the front foot moves?",
        ):
            if len(items) >= 30:
                return items[:30]
            items.append(
                {
                    "id": f"{clip['path']}:technique-{len(items)}",
                    "clip": clip["path"],
                    "question": question,
                    "start_ms": 0,
                    "end_ms": None,
                    "reference": None,
                    "reference_type": "independent_review_required",
                }
            )
    return items[:30]


def frames(folder, start, end):
    import av
    import numpy as np
    from PIL import Image

    result = json.loads((folder / "prepared/result.json").read_text())
    targets = np.linspace(start, end or result["duration_ms"], 8)
    images, first, index = [], None, 0
    with av.open(
        str(
            folder / "source.mp4"
            if (folder / "source.mp4").exists()
            else next(p for p in folder.glob("source.*") if p.suffix != ".json")
        )
    ) as video:
        for frame in video.decode(video=0):
            first = frame.time if first is None else first
            t = (frame.time - first) * 1000
            if index < len(targets) and t >= targets[index]:
                picture = Image.fromarray(frame.to_ndarray(format="rgb24"))
                picture.thumbnail((768, 768))
                buffer = io.BytesIO()
                picture.save(buffer, format="JPEG", quality=85)
                images.append(buffer.getvalue())
                index += 1
                if index >= len(targets):
                    break
    return images


def pose_baseline(project, case):
    """Record pipeline evidence, without grading it against its own geometry."""
    from fencecoach.quality import assess_quality

    result = json.loads(
        (project / "data/training" / case["clip"] / "prepared/result.json").read_text()
    )
    qa = result.get("quality_gate") or assess_quality(result)
    candidates = result.get("candidates", [])
    if case["reference"] is not None:
        movements = result.get("movement_timeline", {}).get("movements", [])
        overlapping = [
            m
            for m in movements
            if m["start_ms"] < case["end_ms"] and m["end_ms"] > case["start_ms"]
        ]
        answer = ", ".join(sorted({m["label"] for m in overlapping})) or "unknown"
        reason = "No verified mapping between pipeline athlete identity and the reviewed selected track; action accuracy is not scored."
    elif "slowest recovery" in case["question"]:
        slowest = max(candidates, key=lambda c: c["end_ms"] - c["start_ms"], default=None)
        answer = (
            {
                "candidate": slowest.get("candidate_id"),
                "start_ms": slowest["start_ms"],
                "end_ms": slowest["end_ms"],
            }
            if slowest
            else "unknown"
        )
        reason = "Longest proposed return interval; neither a reviewed complete repetition nor a quality verdict."
    else:
        answer = "unknown"
        reason = "This pipeline does not establish knee-to-toe alignment or continuous arm-versus-foot initiation from peak angles."
    return {
        "case_id": case["id"],
        "answer": answer,
        "quality_verdict": qa["verdict"],
        "coaching_allowed": qa["coaching_allowed"],
        "accuracy": None,
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    questions = cases(project)
    (project / "evals/vision-cases.json").write_text(
        json.dumps(questions, indent=2), encoding="utf-8"
    )
    report = {
        "status": "not_run",
        "questions": len(questions),
        "independent_action_labels": sum(c["reference"] is not None for c in questions),
        "technique_accuracy": None,
        "reason": "No authenticated frontier vision models configured. Joint geometry and recovery calculations are pipeline proxies, not independently reviewed technique truth.",
        "pose_baseline": [pose_baseline(project, c) for c in questions],
        "models": [],
    }
    if args.execute:
        if not args.models:
            parser.error("Supply authenticated Bedrock vision model IDs with --models.")
        import boto3
        from botocore.config import Config

        from fencecoach.settings import settings

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 1}),
        )
        report["status"] = "executed"
        report["reason"] = (
            "Action-label exact match is reported separately. Unreviewed technique questions have no accuracy score."
        )
        for model in args.models:
            answers = []
            for case in questions:
                start = time.perf_counter()
                content = [
                    {
                        "text": case["question"]
                        + " These are sampled raw frames, not a complete video; answer unknown if insufficient. Track IDs alone do not identify an athlete in pixels; abstain if target identity is unclear."
                    }
                ]
                content.extend(
                    {"image": {"format": "jpeg", "source": {"bytes": image}}}
                    for image in frames(
                        project / "data/training" / case["clip"], case["start_ms"], case["end_ms"]
                    )
                )
                try:
                    reply = client.converse(
                        modelId=model,
                        messages=[{"role": "user", "content": content}],
                        inferenceConfig={"maxTokens": 120, "temperature": 0},
                    )
                    text = " ".join(
                        c.get("text", "") for c in reply["output"]["message"]["content"]
                    ).strip()
                    answers.append(
                        {
                            "case_id": case["id"],
                            "answer": text,
                            "exact_label_match": text.lower().strip(". ") == case["reference"]
                            if case["reference"] is not None
                            else None,
                            "latency_ms": (time.perf_counter() - start) * 1000,
                            "usage": reply.get("usage"),
                            "cost_usd": None,
                        }
                    )
                except Exception as exc:
                    answers.append({"case_id": case["id"], "error": type(exc).__name__})
            scored = [a for a in answers if a.get("exact_label_match") is not None]
            report["models"].append(
                {
                    "model": model,
                    "action_label_accuracy": sum(a["exact_label_match"] for a in scored)
                    / len(scored)
                    if scored
                    else None,
                    "scored": len(scored),
                    "answers": answers,
                }
            )
    (project / "data/evals/vision.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    path = project / "data/evals/benchmark.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["vlm"] = report
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "models"}))


if __name__ == "__main__":
    main()

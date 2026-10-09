"""Offline coach comparison on fixed reviewed-video measurement cases.

Automated checks are diagnostic proxies. Unsupported video fixtures remain QA
failures; this evaluation does not authorize coaching those clips in the app.
"""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np

from fencecoach.benchmarks import render_report
from fencecoach.coach.graph import run_coach
from fencecoach.coach.grounding import unsupported_claims
from fencecoach.schemas import CoachRequest, MetricObservation

QUESTIONS = [
    "What can you tell me about my lunge from this evidence?",
    "Which measurements can help me understand my arm extension?",
    "How consistent are the measured recovery intervals?",
    "Give me one supported observation, one practice cue, and one drill. Explain why.",
    "What does this video not establish about my technique?",
]


def build_cases(project):
    manifest = json.loads((project / "evals/golden.json").read_text())
    cases = []
    for clip in manifest["clips"]:
        result = json.loads(
            (project / "data/training" / clip["path"] / "prepared/result.json").read_text()
        )
        metrics = []
        for i, candidate in enumerate(result.get("candidates", []), 1):
            for j, m in enumerate(candidate.get("measurements", []), 1):
                metrics.append(MetricObservation(metric_id=f"golden-rep-{i:02}-detail-{j:02}", **m))
            metrics.append(
                MetricObservation(
                    metric_id=f"golden-recovery-{i:02}",
                    name="recovery_time",
                    value=candidate["end_ms"] - candidate["start_ms"],
                    unit="ms",
                    confidence=candidate["quality"],
                    start_ms=candidate["start_ms"],
                    end_ms=candidate["end_ms"],
                )
            )
        if not metrics:
            for j, m in enumerate(result.get("clip_measurements", []), 1):
                metrics.append(
                    MetricObservation(
                        metric_id=f"golden-clip-{j:02}",
                        **{k: v for k, v in m.items() if k != "coverage"},
                    )
                )
        if not metrics:
            continue
        for question in QUESTIONS:
            cases.append(
                {
                    "case_id": f"{clip['path']}:{len(cases)}",
                    "clip": clip["path"],
                    "question": question,
                    "request": CoachRequest(
                        session_id="offline-golden",
                        question=question,
                        metrics=metrics[:24],
                        capture_profile=result.get("capture_profile", {}),
                    ).model_dump(mode="json"),
                }
            )
        if len(cases) >= 25:
            break
    return cases[:25]


def number_flags(text, metrics):
    values = {float(m.value) for m in metrics}
    values.update(float(m.confidence) * 100 for m in metrics)
    values.update(float(t) / 1000 for m in metrics for t in (m.start_ms, m.end_ms) if t is not None)
    values.update(float(m.value) / 1000 for m in metrics if m.unit == "ms")
    # Only explicit measurement-unit claims, not proposed drill doses or 2D terminology.
    observed = re.findall(
        r"(?<![\w-])(\d+(?:\.\d+)?)\s*(?:degrees|°|milliseconds|ms\b|seconds|s\b|%)", text
    )
    return [
        v
        for v in observed
        if not any(abs(float(v) - x) <= max(0.05, abs(x) * 0.01) for x in values)
    ]


def evaluate(project, models, cases, judge_model=None):
    from langchain_ollama import ChatOllama

    results, summaries = [], []
    code_hash = hashlib.sha256(
        b"".join(
            (project / "src/fencecoach/coach" / n).read_bytes()
            for n in ("conversation.py", "grounding.py")
        )
    ).hexdigest()
    for name in models:
        print("Evaluating", name, flush=True)
        model = ChatOllama(
            model=name,
            reasoning=False,
            num_ctx=4096,
            num_predict=240,
            keep_alive="1h",
            temperature=0,
            client_kwargs={"timeout": 90},
        )
        rows = []
        for case in cases:
            request = CoachRequest.model_validate(case["request"])
            first = []
            start = time.perf_counter()
            try:
                run = run_coach(
                    request,
                    mode="local",
                    model=model,
                    on_text=lambda text: (
                        first.append((time.perf_counter() - start) * 1000)
                        if text and not first
                        else None
                    ),
                )
                text = run.report.summary
                run.model_id = name
                known = {m.metric_id for m in request.metrics} | {s.source_id for s in run.sources}
                references = [r.source_id for o in run.report.observations for r in o.evidence]
                flags = unsupported_claims(text, request.metrics)
                numeric = number_flags(text, request.metrics)
                row = {
                    "coach_code_sha256": code_hash,
                    "model": name,
                    "case_id": case["case_id"],
                    "clip": case["clip"],
                    "question": case["question"],
                    "answer": text,
                    "latency_ms": run.latency_ms,
                    "first_text_ms": first[0] if first else None,
                    "citation_ids_valid": all(r in known for r in references),
                    "has_evidence": bool(references),
                    "unsupported_claim_flags": flags,
                    "unsupported_number_flags": numeric,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "cost_usd": 0,
                    "relevance_judge": None,
                    "grounding_replacement": any(t.step == "grounding" for t in run.trace),
                    "question_topic_present": topic_present(case["question"], text),
                    "assessment_shape_present": all(
                        re.search(pattern, text, re.I)
                        for pattern in (
                            r"\b(cue|try|practice|focus|keep)\b",
                            r"\b(drill|repeat|reps|attempts|slow)\b",
                            r"\b(why|because|helps|so that|to help)\b",
                        )
                    ),
                    "run": run.model_dump(mode="json"),
                }
                if judge_model:
                    judge = ChatOllama(
                        model=judge_model, reasoning=False, num_predict=100, temperature=0
                    )
                    judgement = judge.invoke(
                        'Score relevance 1-5 as a secondary signal only. Return JSON {"relevance":1,"reason":"..."}. Question: '
                        + case["question"]
                        + " Answer: "
                        + text
                    )
                    try:
                        row["relevance_judge"] = json.loads(str(judgement.content))
                    except ValueError:
                        row["relevance_judge"] = {"parse_error": True}
            except Exception as exc:
                row = {
                    "model": name,
                    "case_id": case["case_id"],
                    "error": str(exc),
                    "latency_ms": (time.perf_counter() - start) * 1000,
                }
            rows.append(row)
            results.append(row)
            (project / "data/evals/coach-answers.json").write_text(
                json.dumps(results, indent=2), encoding="utf-8"
            )
            print(
                name, len(rows), "error" if "error" in row else round(row["latency_ms"]), flush=True
            )
        success = [r for r in rows if "error" not in r]
        if not success:
            summaries.append(
                {"model": name, "unavailable": rows[0]["error"] if rows else "No cases."}
            )
        else:
            summaries.append(
                {
                    "model": name,
                    "answers": len(success),
                    "failures": len(rows) - len(success),
                    "traceability_rate": sum(
                        r["citation_ids_valid"] and not r["unsupported_number_flags"]
                        for r in success
                    )
                    / len(success),
                    "evidence_citation_coverage": sum(r["has_evidence"] for r in success)
                    / len(success),
                    "unsupported_claim_flag_rate": sum(
                        bool(r["unsupported_claim_flags"]) for r in success
                    )
                    / len(success),
                    "question_topic_rate": sum(r["question_topic_present"] for r in success)
                    / len(success),
                    "grounding_replacement_rate": sum(r["grounding_replacement"] for r in success)
                    / len(success),
                    "assessment_shape_proxy_rate": sum(
                        r["assessment_shape_present"] for r in success
                    )
                    / len(success),
                    "p50_ms": float(np.percentile([r["latency_ms"] for r in success], 50)),
                    "p95_ms": float(np.percentile([r["latency_ms"] for r in success], 95)),
                    "first_text_samples": sum(r["first_text_ms"] is not None for r in success),
                    "first_text_p50_ms": float(
                        np.percentile(
                            [r["first_text_ms"] for r in success if r["first_text_ms"] is not None],
                            50,
                        )
                    )
                    if any(r["first_text_ms"] is not None for r in success)
                    else None,
                    "first_text_p95_ms": float(
                        np.percentile(
                            [r["first_text_ms"] for r in success if r["first_text_ms"] is not None],
                            95,
                        )
                    )
                    if any(r["first_text_ms"] is not None for r in success)
                    else None,
                    "cost_usd": 0,
                }
            )
    return summaries


def topic_present(question, answer):
    """Keyword diagnostic only, not a human usefulness rating."""
    topics = {
        "arm": r"\b(arm|hand|extension|sequence)\b",
        "recovery": r"\b(recovery|return|reset|interval)\b",
        "lunge": r"\b(lunge|knee|leg|foot|stance)\b",
    }
    for key, pattern in topics.items():
        if key in question.lower():
            return bool(re.search(pattern, answer, re.I))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["qwen2.5:3b", "fencecoach-qwen3:4b"])
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--judge-model")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    (project / "data/evals").mkdir(parents=True, exist_ok=True)
    cases = build_cases(project)[: args.limit]
    (project / "evals/coach-cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    path = project / "data/evals/benchmark.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["coach_models"] = evaluate(project, args.models, cases, args.judge_model)
    data["coach_models"].append(
        {
            "model": "AWS Bedrock Claude",
            "unavailable": "Not executed: authenticated model access and cost configuration are required.",
        }
    )
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    (project / "BENCHMARKS.md").write_text(render_report(data), encoding="utf-8")


if __name__ == "__main__":
    main()

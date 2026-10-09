"""Compare before/after reply latency on the same offline diagnostic questions."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from fencecoach.coach.graph import run_coach
from fencecoach.coach.grounding import unsupported_claims
from fencecoach.coach.providers import warm_local_model
from fencecoach.schemas import CoachRequest, ConversationMessage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after", "after-full"], required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    source = json.loads((project / "evals/coach-cases.json").read_text())
    cases = list(source) if args.phase == "after-full" else [source[i] for i in (0, 1, 2, 3, 5, 6)]
    simple = CoachRequest.model_validate(source[0]["request"])
    for question in ("What is recovery in fencing?", "Why?"):
        data = simple.model_copy(
            update={
                "question": question,
                "conversation_history": [
                    ConversationMessage(role="user", content="What does a deliberate reset mean?"),
                    ConversationMessage(
                        role="assistant",
                        content="Pause in en garde between attempts so the starting position is repeatable.",
                    ),
                ],
            }
        )
        cases.append({"case_id": "followup:" + question, "request": data.model_dump(mode="json")})
    warm_local_model()
    rows = []
    for case in cases:
        first = []
        start = time.perf_counter()
        request = CoachRequest.model_validate(case["request"])
        run = run_coach(
            request,
            "local",
            on_text=lambda text: (
                first.append((time.perf_counter() - start) * 1000) if text and not first else None
            ),
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "question": request.question,
                "latency_ms": run.latency_ms,
                "first_text_ms": first[0] if first else None,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "model_calls": sum(s.step == "conversation" for s in run.trace),
                "grounding_replacement": any(s.step == "grounding" for s in run.trace),
                "unsupported_claim_flags": unsupported_claims(run.report.summary, request.metrics),
                "answer": run.report.summary,
            }
        )
        print(args.phase, case["case_id"], round(run.latency_ms), flush=True)
    report = {
        "phase": args.phase,
        "model": run.model_id,
        "cases": len(rows),
        "p50_ms": float(np.percentile([r["latency_ms"] for r in rows], 50)),
        "p95_ms": float(np.percentile([r["latency_ms"] for r in rows], 95)),
        "first_text_p50_ms": float(
            np.percentile([r["first_text_ms"] for r in rows if r["first_text_ms"] is not None], 50)
        ),
        "coach_code_sha256": hashlib.sha256(
            (project / "src/fencecoach/coach/conversation.py").read_bytes()
        ).hexdigest(),
        "scope": "Same-machine warmed local model; offline diagnostic footage, not proof of coaching correctness; browser/queue overhead excluded.",
        "answers": rows,
    }
    path = project / f"data/evals/reply-latency-{args.phase}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "answers"}), flush=True)


if __name__ == "__main__":
    main()

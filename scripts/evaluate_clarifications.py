"""Replay known clarification failures through the warmed local coach."""

import argparse
import json
from pathlib import Path

from fencecoach.coach.graph import run_coach
from fencecoach.coach.providers import warm_local_model
from fencecoach.coach.turns import conversation_issues
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings

BAD = "For a lunge, extend your arm to the side, about shoulder-width apart from the body. This position helps in maintaining balance and allows for a smooth transition into the next stroke."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=settings.ollama_chat_model)
    args = parser.parse_args()
    settings.ollama_chat_model = args.model
    warm_local_model()
    history = [
        ConversationMessage(role="user", content="Explain the arm in a lunge"),
        ConversationMessage(role="assistant", content=BAD),
    ]
    rows = []
    for question in (
        "can you describe better",
        "which arm",
        "which arm, sword arm or non-sword arm",
        "What should the non-sword arm do in a simple lunge?",
        "What is recovery in fencing?",
    ):
        request = CoachRequest(
            session_id="offline-clarification-eval", question=question, conversation_history=history
        )
        published = []
        run = run_coach(request, "local", on_text=published.append)
        row = {
            "question": question,
            "answer": run.report.summary,
            "latency_ms": run.latency_ms,
            "quality_flags": conversation_issues(request, run.report.summary),
            "reference_sources": [source.source for source in run.sources],
            "grounding_replacement": any(step.step == "grounding" for step in run.trace),
            "repeated_bad_answer_streamed": BAD in published,
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {
        "model": args.model,
        "scope": "Five fixed diagnostic questions with the same known wrong prior answer. Actual warmed local model; heuristic checks are not expert coaching accuracy.",
        "cases": len(rows),
        "answers": rows,
    }
    sequential_history = list(history)
    sequential = []
    for question in (
        "can you describe better",
        "which arm",
        "which arm, sword arm or non-sword arm",
    ):
        request = CoachRequest(
            session_id="offline-sequential-clarifications",
            question=question,
            conversation_history=sequential_history,
        )
        run = run_coach(request, "local", on_text=lambda _: None)
        row = {
            "question": question,
            "answer": run.report.summary,
            "latency_ms": run.latency_ms,
            "quality_flags": conversation_issues(request, run.report.summary),
        }
        sequential.append(row)
        sequential_history.extend(
            [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=run.report.summary),
            ]
        )
        print(json.dumps(row), flush=True)
    report["sequential_answers"] = sequential
    path = Path("data/evals/clarifications-" + args.model.replace(":", "-") + ".json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if any(row["quality_flags"] or row["repeated_bad_answer_streamed"] for row in rows):
        raise SystemExit("Clarification regression failed")
    if any(row["quality_flags"] for row in sequential):
        raise SystemExit("Sequential clarification regression failed")


if __name__ == "__main__":
    main()

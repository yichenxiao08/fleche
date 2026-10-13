"""Live dialogue diagnostics against saved session evidence; not expert technique scoring."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from fencecoach.api import coaching_request, repository
from fencecoach.coach.answer_style import style_issues
from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.providers import chat_model
from fencecoach.schemas import ConversationMessage, ReportRequest
from fencecoach.settings import settings

PROJECT = Path(__file__).resolve().parents[1]

SCENARIOS = [
    ("arm-followups", [
        ("what about my arm", [r"arm|elbow|hand|extension"], []),
        ("Which arm do you mean?", [r"sword|weapon"], []),
        ("Was I extending it before my foot landed?", [r"arm|hand|extension", r"not|cannot|can't|doesn't|does not|unavailable"], []),
    ]),
    ("torso-followups", [
        ("How was my torso?", [r"torso|trunk|upright|upper body"], []),
        ("And on the last one?", [r"torso|trunk|upright|upper body"], []),
        ("Should I lean forward more?", [r"lean|torso|upright|upper body"], []),
    ]),
    ("rear-leg-power", [
        ("How straight was my back leg at the finish of rep 3?", [r"rear|back leg|back knee", r"rep\s*3"], []),
        ("Does that mean it was explosive?", [r"power|explos|force|speed|drive", r"not|cannot|can't|doesn't|does not|alone|rather than"], []),
    ]),
    ("multi-part", [
        ("Compare my arm and torso at the lunge finish in reps 2 and 7.", [r"arm|elbow|hand", r"torso|upright|upper body", r"rep\s*2|reps\s*2", r"rep\s*7|\band 7\b|,\s*7"], []),
    ]),
    ("duration-comparison", [
        ("Which rep had the shortest action-to-lunge interval?", [r"rep\s*\d+", r"interval|duration|time"], [r"hip movement speed"]),
        ("And which one took the longest?", [r"rep\s*\d+", r"interval|duration|time|longest"], []),
    ]),
    ("vague", [
        ("Something feels off. What should I work on first?", [r"try|focus|practice|finish|knee|leg|arm|recovery"], []),
        ("Why that?", [r"reference|rep|finish|knee|leg|arm|recovery|because|so that"], []),
    ]),
    ("misleading-premise", [
        ("You said I only had two reps. Can you review the whole set?", [], []),
    ]),
    ("precise-number", [
        ("Give me the rear knee angle at the lunge finish in rep 3, in degrees.", [r"rear|back", r"\d+(?:\.\d+)?\s*(?:degrees|deg)"], []),
    ]),
]


def checks(question, answer, request, required, forbidden):
    issues = []
    issues.extend(style_issues(question, answer, personal=True))
    for pattern in required:
        if not re.search(pattern, answer, re.I):
            issues.append("Missing requested aspect: " + pattern)
    for pattern in forbidden:
        if re.search(pattern, answer, re.I):
            issues.append("Wrong evidence basis: " + pattern)
    if re.search(r"\d+\.\d{2,}\s*(?:seconds|s\b)|\d+\s*(?:milliseconds|ms\b)", answer, re.I):
        issues.append("Times are not rounded seconds.")
    if re.search(r"evidence_id|session_evidence_ids|projected_torso_tilt|front_knee_angle", answer):
        issues.append("Internal field names leaked into the answer.")
    reps = request.technique_evaluation.get("reps", [])
    if question.lower() == "what about my arm" and not re.search(r"this session|your session|your (?:right )?(?:sword|weapon) arm.{0,40}(?:was|stayed|reached)|your reps|across|rep\s*\d+|measured|tracked", answer, re.I):
        issues.append("Generic arm advice omitted available current-session observations.")
    if "only had two" in question and len(reps) > 2:
        count = str(len(reps))
        words = {5: "five", 8: "eight"}
        if not re.search(rf"\b(?:{count}|{words.get(len(reps), count)})\s+(?:reps|repetitions|lunges|attempts)\b", answer, re.I):
            issues.append("Did not correct the stale repetition count.")
    if "rear knee angle" in question:
        rep = next((item for item in reps if item["rep_number"] == 3), {})
        expected = rep.get("measurements", {}).get("rear_knee_angle", {}).get("value")
        reported = re.findall(r"(-?\d+(?:\.\d+)?)\s*(?:degrees|deg)", answer, re.I)
        if expected is not None and not any(abs(float(value) - expected) <= 0.15 for value in reported):
            issues.append("Rear-knee angle does not match rep 3's finish measurement.")
    if "shortest action-to-lunge" in question:
        durations = [
            (item["measurements"]["action_to_lunge_time"]["value"], item["rep_number"])
            for item in reps if "action_to_lunge_time" in item.get("measurements", {})
        ]
        if durations:
            minimum = min(value for value, _ in durations)
            winners = [number for value, number in durations if value == minimum]
            if not any(re.search(rf"\brep\s*{number}\b", answer, re.I) for number in winners):
                issues.append("Winner does not match the measured action duration.")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id")
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--mode", choices=["gemini", "local"], default="gemini")
    parser.add_argument("--spacing-seconds", type=float, default=18)
    parser.add_argument("--allow-fallback", action="store_true", help="Exercise app failover instead of isolating the selected provider")
    parser.add_argument("--output", type=Path, default=PROJECT / "evals/results/coach-dialogue-latest.json")
    args = parser.parse_args()
    session = repository.get_session(args.session_id) if args.session_id else repository.list_sessions()[0]
    if session is None:
        raise SystemExit("Session not found.")
    rows = []
    for scenario, turns in SCENARIOS:
        history = []
        for question, required, forbidden in turns:
            if len(rows) >= args.max_turns:
                break
            started = time.perf_counter()
            row = {"scenario": scenario, "question": question, "session_id": session.session_id}
            try:
                request = coaching_request(session, ReportRequest(question=question, mode=args.mode))
                # Isolate each scenario while preserving its actual dialogue.
                request.conversation_history = history.copy()
                run = run_conversation(request, args.mode, model=None if args.allow_fallback else chat_model(args.mode))
                issues = checks(question, run.report.summary, request, required, forbidden)
                row.update(
                    answer=run.report.summary, issues=issues, status="passed" if not issues else "failed",
                    latency_ms=run.latency_ms,
                    pipeline_ms=round((time.perf_counter() - started) * 1000, 2),
                    model_calls=sum(event.step == "conversation" for event in run.trace)
                    + int(any(event.step == "semantic_review" for event in run.trace))
                    + sum(event.step == "semantic_repair" for event in run.trace),
                    review_corrections=[event.detail for event in run.trace if event.step == "semantic_review"],
                    actual_model=run.model_id, actual_mode=run.mode,
                )
                history.extend([
                    ConversationMessage(role="user", content=question),
                    ConversationMessage(role="assistant", content=run.report.summary),
                ])
            except Exception as exc:
                history.append(ConversationMessage(role="user", content=question))
                row.update(
                    status="error", error_type=type(exc).__name__,
                    details=str(exc).replace(settings.gemini_api_key.get_secret_value(), "[redacted]")[:500],
                    validation_issues=getattr(exc, "validation_issues", []),
                )
            rows.append(row)
            report = {
                "scope": "Live answer relevance, follow-up continuity, repetition coverage, selected numeric facts and presentation. Automated checks are not expert validation of fencing advice.",
                "model": settings.gemini_chat_model,
                "passed": sum(item["status"] == "passed" for item in rows),
                "total": len(rows), "results": rows,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)
            if row.get("error_type") in {"ModelRateLimitError", "GoogleRateLimitError"}:
                return 2
            time.sleep(max(0, args.spacing_seconds - (time.perf_counter() - started)))
    return 0 if all(item["status"] == "passed" for item in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

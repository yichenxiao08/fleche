"""Check coach intent and rep-evidence coverage without making model/API calls.

This is an evidence-routing contract check, not a validation of fencing advice.
When the local database is available, it uses the newest completed saved
reference-comparison request. Only aggregate pass/fail counts are written.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from fencecoach.coach.conversation import run_conversation  # noqa: E402
from fencecoach.coach.intent import classify_coach_question, mentioned_rep_numbers  # noqa: E402
from fencecoach.coach.technique_evidence import (  # noqa: E402
    all_reps_fallback,
    coaching_evaluation_context,
    current_session_context,
    rep_comparison_fallback,
    rep_comparison_result,
    selected_evaluation,
)
from fencecoach.schemas import CoachRequest  # noqa: E402


def load_latest_reference_request(database: Path) -> CoachRequest | None:
    if not database.exists():
        return None
    uri = f"file:{quote(database.resolve().as_posix(), safe='/:')}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT payload FROM coaching_jobs WHERE status='completed' "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    for (payload,) in rows:
        try:
            job = json.loads(payload)
            request = CoachRequest.model_validate(job["request"])
        except (KeyError, TypeError, ValueError):
            continue
        evaluation = request.technique_evaluation
        if (
            evaluation.get("coaching_mode") == "reference_comparison"
            and len(evaluation.get("reps", [])) >= 2
        ):
            return request
    return None


def independent_reference_ranking(request):
    scored = []
    for rep in request.technique_evaluation.get("reps", []):
        row = next(
            (
                item
                for item in rep.get("reference_comparison", {}).get("rows", [])
                if item.get("metric") == "front_knee_angle"
                and item.get("phase") == "finish"
                and isinstance(item.get("current"), (int, float))
                and isinstance(item.get("reference_median"), (int, float))
                and isinstance(item.get("reference_range"), list)
                and len(item["reference_range"]) == 2
            ),
            None,
        )
        if not row:
            continue
        low, high = map(float, row["reference_range"])
        value = float(row["current"])
        score = (max(low - value, 0.0, value - high), abs(value - float(row["reference_median"])))
        scored.append((score, rep["rep_number"]))
    if len(scored) < 2:
        return None
    best = min(scored)[1]
    worst = max(scored)[1]
    if best == worst:
        return None
    return best, worst


def check_intents(cases):
    failures = []
    for case in cases:
        intent = classify_coach_question(case["question"])
        actual = {
            "intent": intent.kind,
            "needs_video_metrics": intent.needs_video_metrics,
            "needs_technique_evaluation": intent.needs_technique_evaluation,
        }
        expected = {
            key: case[key]
            for key in (
                "intent",
                "needs_video_metrics",
                "needs_technique_evaluation",
            )
        }
        if actual != expected:
            failures.append(case["id"])
    return failures


def check_local_evidence(request, cases):
    reps = request.technique_evaluation.get("reps", [])
    all_numbers = [rep["rep_number"] for rep in reps]
    checks = 0
    topic_checks = 0
    topic_evidence_passed = 0
    session_first_checks = 0
    failures = []

    for case in cases:
        tailored = request.model_copy(update={"question": case["question"]})
        snapshot = json.loads(current_session_context(tailored))
        session_first_checks += 1
        if (
            snapshot.get("current_clip_reps_detected") != len(all_numbers)
            or "measured_features_available" not in snapshot
            or "instruction" not in snapshot
        ):
            failures.append(case["id"] + "-missing-session-first-snapshot")
        expected_finding_reps = [
            rep["rep_number"]
            for rep in reps
            if rep.get("reference_comparison", {}).get("coaching_priorities")
        ]
        actual_finding_reps = [row["rep"] for row in snapshot.get("per_rep_reference_findings", [])]
        if actual_finding_reps != expected_finding_reps:
            failures.append(case["id"] + "-incomplete-per-rep-session-evidence")
        intent = classify_coach_question(case["question"])
        if (
            intent.topic
            and case["needs_technique_evaluation"]
            and not snapshot.get("per_rep_measurements")
        ):
            failures.append(case["id"] + "-missing-question-relevant-session-evidence")

        if not case["needs_technique_evaluation"]:
            continue
        checks += 1
        selected = selected_evaluation(tailored)["rep_measurements"]
        selected_numbers = [rep["rep_number"] for rep in selected]
        selection = case["selection"]
        if (
            (selection == "all" and selected_numbers != all_numbers)
            or (selection == "first" and selected_numbers != all_numbers[:1])
            or (selection == "last" and selected_numbers != all_numbers[-1:])
            or (selection == "number" and selected_numbers != [case["rep_number"]])
        ):
            failures.append(case["id"])
        if case["id"] in {"arm-extension-timing", "rear-foot-movement", "personal-lunge-speed"}:
            topic_checks += 1
            context = json.loads(coaching_evaluation_context(tailored))
            if "requested_topic_evidence" in context:
                topic_reps = [row["rep"] for row in context["requested_topic_evidence"]["reps"]]
            else:
                topic_reps = [row["rep"] for row in context.get("within_clip_motion", [])]
            if topic_reps == all_numbers:
                topic_evidence_passed += 1
            else:
                failures.append(case["id"] + "-topic-evidence")

    comparison_case = next((case for case in cases if case["intent"] == "rep_comparison"), None)
    comparison_ok = False
    if comparison_case:
        tailored = request.model_copy(update={"question": comparison_case["question"]})
        expected_ranking = independent_reference_ranking(tailored)
        actual_ranking = rep_comparison_result(tailored)
        response = rep_comparison_fallback(tailored) or ""
        comparison_ok = bool(
            expected_ranking
            and actual_ranking
            and (actual_ranking["best"]["rep"], actual_ranking["worst"]["rep"]) == expected_ranking
            and all(re.search(rf"\brep\s*{rep}\b", response, re.I) for rep in expected_ranking)
            and len(
                re.findall(
                    r"\b\d+\.\d+ seconds\b|\b\d+\.\d+-second mark\b",
                    response,
                    re.I,
                )
            )
            >= 2
        )
        if not comparison_ok:
            failures.append("rep-comparison-evidence-contract")

    integrated_passed = 0
    integrated_total = 0
    for case in cases:
        if case["intent"] not in {"rep_comparison", "all_reps"}:
            continue
        if case["intent"] == "rep_comparison" and case["id"] != "best-worst-explicit":
            continue
        integrated_total += 1
        tailored = request.model_copy(update={"question": case["question"]})
        try:
            run = run_conversation(tailored, mode="demo", model=None)
            answer_reps = mentioned_rep_numbers(run.report.summary)
            if case["intent"] == "all_reps":
                route_ok = answer_reps.issuperset(all_numbers) and any(
                    event.step == "summarize_reps" for event in run.trace
                )
            else:
                expected = independent_reference_ranking(tailored)
                route_ok = bool(
                    expected
                    and set(expected).issubset(answer_reps)
                    and any(event.step == "rank_reps" for event in run.trace)
                )
            route_ok = route_ok and run.input_tokens == 0 and run.output_tokens == 0
            route_ok = route_ok and any(
                event.step == "assess_current_session" for event in run.trace
            )
        except Exception:
            route_ok = False
        if route_ok:
            integrated_passed += 1
        else:
            failures.append(case["id"] + "-integrated-route")

    all_reps_case = next((case for case in cases if case["intent"] == "all_reps"), None)
    all_reps_covered = 0
    if all_reps_case:
        tailored = request.model_copy(update={"question": all_reps_case["question"]})
        response = all_reps_fallback(tailored) or ""
        covered_numbers = mentioned_rep_numbers(response)
        all_reps_covered = sum(number in covered_numbers for number in all_numbers)
        if all_reps_covered != len(all_numbers):
            failures.append("all-reps-response-coverage")

    return {
        "status": "passed" if not failures else "failed",
        "rep_count": len(all_numbers),
        "session_first_cases_checked": session_first_checks,
        "selection_cases_checked": checks,
        "topic_evidence_cases_passed": topic_evidence_passed,
        "topic_evidence_cases_total": topic_checks,
        "comparison_contract_passed": comparison_ok,
        "all_reps_covered_count": all_reps_covered,
        "integrated_routes_passed": integrated_passed,
        "integrated_routes_total": integrated_total,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="Local FenceCoach SQLite database")
    parser.add_argument(
        "--output", type=Path, help="Aggregate report path (defaults to ignored data/evals)"
    )
    args = parser.parse_args()

    project = PROJECT
    try:
        cases = json.loads((project / "evals/coach-intent-cases.json").read_text(encoding="utf-8"))[
            "cases"
        ]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Could not load coach intent cases: {exc}", file=sys.stderr)
        return 2

    intent_failures = check_intents(cases)
    request = load_latest_reference_request(args.database or project / "data/fencecoach.sqlite3")
    evidence = check_local_evidence(request, cases) if request else {"status": "skipped"}
    passed = not intent_failures and evidence["status"] in {"passed", "skipped"}
    report = {
        "schema": "coach-evidence-contract-report-v1",
        "status": "passed" if passed else "failed",
        "intent_cases_passed": len(cases) - len(intent_failures),
        "intent_cases_total": len(cases),
        "intent_failures": intent_failures,
        "local_evidence": evidence,
        "scope": "Current-session-first routing and answer coverage only; not expert validation of fencing technique.",
    }
    output = args.output or project / "data/evals/coach-contract-latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

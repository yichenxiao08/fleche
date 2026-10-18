"""Bounded, resumable evaluation against saved session evidence.

The oracle reads raw fixture records and library files, never renderer templates.
Offline runs do not measure provider quality/latency. Before calls the legacy
runner directly, regardless of the production feature flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import AIMessageChunk

from fencecoach.coach.conversation import _run_conversation, run_conversation
from fencecoach.coach.providers import chat_model
from fencecoach.coach.verified_dialogue import run_verified_conversation
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState

try:
    from scripts.coach_eval_oracle import check_answer, scenarios, scope_scenarios
except ModuleNotFoundError:
    from coach_eval_oracle import check_answer, scenarios, scope_scenarios

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals/coach_audit"
SCHEMA_VERSION = 3


class OfflineSelector:
    """Exercises the new selector protocol; never a provider benchmark."""

    def stream(self, messages):
        for unit in json.loads(messages[-1].content)["units"]:
            yield AIMessageChunk(content=unit["id"] + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprints(cases=None):
    return {
        "fixture_sha256": {
            p.name: digest(p)
            for p in FIXTURES.glob("*.json")
            if p.stem in {"current", "unsupported", "low_confidence"}
        },
        "code_sha256": {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted(
                list((ROOT / "src/fencecoach/coach").glob("*.py"))
                + [
                    Path(__file__),
                    ROOT / "scripts/coach_eval_oracle.py",
                    ROOT / "src/fencecoach/schemas.py",
                ]
                + list((ROOT / "knowledge").rglob("*.md"))
            )
        },
        "expectation_sha256": hashlib.sha256(
            json.dumps(scenarios() if cases is None else cases, sort_keys=True).encode()
        ).hexdigest(),
    }


def percentile(values, fraction):
    ordered = sorted(v for v in values if v is not None)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def summarize(rows):
    done = [r for r in rows if r["status"] == "completed"]
    offline = bool(done) and all(r.get("offline") for r in done)
    followups = [r for r in done if r.get("expected", {}).get("followup")]
    bait = [r for r in done if r.get("category") == "bait"]
    scope = [r for r in done if isinstance(r.get("scope_correct"), bool)]
    repetition = [r for r in done if isinstance(r.get("unrequested_repetition"), bool)]
    coverage = [r["answer_rep_coverage"] for r in scope if r.get("answer_rep_coverage") is not None]

    def rate(items, field):
        values = [r[field] for r in items if isinstance(r.get(field), bool)]
        return sum(values) / len(values) if values else None

    def median(field):
        if offline:
            return None
        values = [r[field] for r in done if r.get(field) is not None]
        return statistics.median(values) if values else None

    counts = [r["cited_data_points"] for r in done if r.get("cited_data_points") is not None]
    return {
        "attempts": len(rows),
        "completed": len(done),
        "errors": sum(r["status"] == "error" for r in rows),
        "timeouts": sum(r["status"] == "timeout" for r in rows),
        "skipped": sum(r["status"] == "skipped" for r in rows),
        "followup_turns_scored": len(followups),
        "followup_resolution_accuracy": rate(followups, "topic_correct"),
        "scope_turns_scored": len(scope),
        "scope_turns_needing_semantic_review": sum(
            bool(r.get("scope_review_needed")) for r in done
        ),
        "scope_preservation_accuracy": rate(scope, "scope_correct"),
        "mean_requested_rep_coverage": statistics.mean(coverage) if coverage else None,
        "complete_requested_rep_coverage_rate": sum(value == 1 for value in coverage)
        / len(coverage)
        if coverage
        else None,
        "repetition_turns_scored": len(repetition),
        "unrequested_repetition_rate": rate(repetition, "unrequested_repetition"),
        "unsupported_claim_rate": rate(done, "unsupported_claims_flagged"),
        "semantic_review_needed_rate": rate(done, "semantic_review_needed"),
        "bait_turns_scored": len(bait),
        "fabrication_rate_bait": rate(bait, "unsupported_claims_flagged"),
        "content_fallback_correctness": rate(done, "fallback_correct"),
        "evidence_minimality_mean_data_points": statistics.mean(counts) if counts else None,
        "median_ms": median("latency_ms"),
        "p95_ms": None if offline else percentile([r.get("latency_ms") for r in done], 0.95),
        "median_first_visible_ms": median("first_visible_ms"),
        "p95_first_visible_ms": None
        if offline
        else percentile([r.get("first_visible_ms") for r in done], 0.95),
        "median_model_first_token_ms": median("model_first_token_ms"),
        "p95_model_first_token_ms": None
        if offline
        else percentile([r.get("model_first_token_ms") for r in done], 0.95),
        "median_provider_model_ms": median("provider_model_ms"),
        "median_retrieval_ms": median("retrieval_ms"),
        "median_verification_ms": median("verification_ms"),
        "offline_protocol_median_ms": statistics.median(r["latency_ms"] for r in done)
        if offline
        else None,
        "evaluation_signal": "offline evidence/protocol checks only; provider quality not measured"
        if offline
        else "live provider",
        "flagged_answer_rate": sum(bool(r.get("issues")) for r in done) / len(done)
        if done
        else None,
        "limits": (
            "Deterministic diagnostics verify raw record attribution, verbatim guidance and one "
            "independently specified simple-lunge sword-arm-to-target paraphrase relation. Other "
            "paraphrases remain semantic-review-needed, separate from unsupported claims. Zero flags is not proof "
            "of no fabrication. Errors/skips have no quality score; offline latency is not model latency."
            " Scope coverage counts repetitions with matching reliable raw fixture records; "
            "disclosures about unavailable repetitions are not scored."
            " Natural prose outside numeric parser coverage requires semantic review. "
            "Topic keywords and lexical repetition diagnostics do not measure directness or overall coaching quality."
        ),
    }


def _run_turn(payload):
    base = CoachRequest.model_validate(payload["request"])
    started = time.perf_counter()
    first = []

    def publish(text):
        if text and not first:
            first.append((time.perf_counter() - started) * 1000)

    engine = payload.get("engine", "natural")
    if payload["offline"] and engine != "verified":
        raise ValueError("Offline selectors only exercise the verified engine")
    model = OfflineSelector() if payload["offline"] else chat_model(payload["provider"])
    model_setup_ms = (time.perf_counter() - started) * 1000
    if payload["phase"] == "before":
        run = _run_conversation(base, payload["provider"], model=model, on_text=publish)
        engine = "legacy-natural"
    elif engine == "verified":
        run = run_verified_conversation(base, payload["provider"], model=model, on_text=publish)
    else:
        with patch("fencecoach.coach.conversation.settings.fencecoach_verified_dialogue", False):
            run = run_conversation(base, payload["provider"], model=model, on_text=publish)
    return {
        "status": "completed",
        "run": run.model_dump(mode="json"),
        "latency_ms": (time.perf_counter() - started) * 1000,
        "first_visible_ms": first[0] if first else None,
        "offline": payload["offline"],
        "engine_actual": engine,
        "model_setup_ms": model_setup_ms,
    }


def _worker(request_path, output_path):
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        result = _run_turn(payload)
    except Exception as exc:
        from fencecoach.coach.router import failure_reason

        # SDK exception messages can contain URLs or credentials; do not record them.
        result = {
            "status": "error",
            "error_type": type(exc).__name__,
            "validation_issues": getattr(exc, "validation_issues", []),
            "provider_failure": failure_reason(exc),
        }
    output_path.write_text(json.dumps(result), encoding="utf-8")


def bounded_turn(payload, timeout_seconds, *, worker_command=None):
    """Terminate and join hung SDKs so no model call remains running in a worker."""
    token = uuid4().hex
    request_path = ROOT / "tmp" / f"coach-eval-request-{token}.json"
    output_path = ROOT / "tmp" / f"coach-eval-result-{token}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    command = worker_command or [
        sys.executable,
        str(Path(__file__)),
        "--worker-request",
        str(request_path),
        "--worker-output",
        str(output_path),
    ]
    started = time.perf_counter()
    worker = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        try:
            worker.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            result = {
                "status": "timeout",
                "error_type": "EvaluationDeadline",
                "latency_ms": timeout_seconds * 1000,
            }
        else:
            result = (
                json.loads(output_path.read_text(encoding="utf-8"))
                if output_path.exists()
                else {"status": "error", "error_type": "WorkerExited"}
            )
        result["wall_clock_ms"] = (time.perf_counter() - started) * 1000
        return result
    finally:
        if worker.poll() is None:
            worker.terminate()
        try:
            worker.wait(timeout=3)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=3)
        request_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def score_result(row, result, request):
    row.update({key: value for key, value in result.items() if key != "run"})
    if result["status"] != "completed":
        row["root_causes"] = [
            "provider/model limitation"
            if not result.get("validation_issues")
            else "grounding enforcement"
        ]
        row["issues"] = result.get("validation_issues", [])
        return None
    run = result["run"]
    row.update(
        answer=run["report"]["summary"],
        provider_actual=run["mode"],
        fallback_reason=run.get("fallback_reason"),
        model_first_token_ms=(run["first_token_ms"] + result.get("model_setup_ms", 0))
        if run.get("first_token_ms") is not None
        else None,
        trace=run["trace"],
        dialogue_state=run.get("dialogue_state"),
        answer_contract=run.get("answer_contract", {}),
        resolved_question=run.get("answer_contract", {}).get("resolved_question"),
    )
    for field, steps in (
        (
            "provider_model_ms",
            {"model", "agent", "answer", "write_answer", "semantic_review", "answer_repair"},
        ),
        (
            "retrieval_ms",
            {
                "retrieve",
                "assess_current_session",
                "get_technique_evaluation",
                "get_reviewed_feedback",
            },
        ),
        ("verification_ms", {"verify", "grounding"}),
    ):
        matching = [t.get("elapsed_ms", 0) for t in run["trace"] if t["step"] in steps]
        row[field] = sum(matching) if matching else None
    row.update(check_answer(row["answer"], request, row["expected"], run, ROOT / "knowledge"))
    return run.get("dialogue_state")


def save_artifact(output, artifact):
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".pending.json")
    pending.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    pending.replace(output)


def load_or_create(output, metadata, resume=False):
    if output.exists():
        if not resume:
            raise ValueError(
                f"{output.name} already exists; choose --run-id or explicitly --resume"
            )
        artifact = json.loads(output.read_text(encoding="utf-8"))
        for field in (
            "schema_version",
            "phase",
            "suite",
            "engine",
            "provider_requested",
            "execution",
            "fixture_sha256",
            "code_sha256",
            "expectation_sha256",
        ):
            if artifact.get(field) != metadata.get(field):
                raise ValueError(f"Cannot resume: {field} changed; choose a new --run-id")
        return artifact
    return {**metadata, "created_at": datetime.now(UTC).isoformat(), "rows": []}


def forced_switch_scenario():
    """Route five conversational turns, injecting an HTTP 429 at turn 3."""
    import httpx

    from fencecoach.coach.router import CircuitBreaker, route
    from fencecoach.settings import settings

    clock = [1.0]
    breaker = CircuitBreaker(lambda: clock[0])
    state, history, rows, calls = None, [], [], []
    case = next(c for c in scenarios() if c["id"] == "switch")
    turns = case["turns"] + ["What should I change?"]
    expected = case["expected"] + [dict(case["expected"][-1])]
    with (
        patch.object(settings, "fencecoach_local_fallback", True),
        patch(
            "fencecoach.coach.verified_dialogue.route",
            side_effect=lambda operation, mode: route(operation, mode, breaker=breaker),
        ),
    ):
        for index, question in enumerate(turns):
            if index == 4:
                clock[0] = breaker.until + 1

            def factory(provider, index=index):
                calls.append({"turn": index + 1, "provider": provider})
                if index == 2 and provider == "gemini":
                    response = httpx.Response(
                        429,
                        headers={"Retry-After": "120"},
                        request=httpx.Request("POST", "https://example.invalid"),
                    )
                    raise httpx.HTTPStatusError(
                        "Forced 429", request=response.request, response=response
                    )
                return OfflineSelector()

            request = CoachRequest.model_validate_json((FIXTURES / "current.json").read_text())
            request.question, request.conversation_history, request.dialogue_state = (
                question,
                history[-12:],
                state,
            )
            with patch("fencecoach.coach.verified_dialogue.chat_model", side_effect=factory):
                run = run_verified_conversation(request, "gemini")
            state = run.dialogue_state
            row = {
                "case": "forced-429",
                "turn": index + 1,
                "question": question,
                "category": "provider_switch",
                "expected": expected[index],
            }
            score_result(
                row,
                {
                    "status": "completed",
                    "run": run.model_dump(mode="json"),
                    "latency_ms": run.latency_ms,
                    "first_visible_ms": run.first_visible_ms,
                },
                request,
            )
            row["circuit_until"] = breaker.until
            rows.append(row)
            history.extend(
                [
                    ConversationMessage(role="user", content=question),
                    ConversationMessage(role="assistant", content=run.report.summary),
                ]
            )
    checks = {
        "turn3_rate_limit": rows[2]["provider_actual"] == "local"
        and rows[2]["fallback_reason"] == "rate_limit",
        "turn4_cooldown": rows[3]["provider_actual"] == "local"
        and rows[3]["fallback_reason"] == "cooldown:rate_limit",
        "retry_after_respected": rows[2]["circuit_until"] >= 121,
        "gemini_not_retried_during_cooldown": {"turn": 4, "provider": "gemini"} not in calls,
        "turn5_probe_and_exit": rows[4]["provider_actual"] == "gemini"
        and rows[4]["circuit_until"] == 0,
        "context_preserved": all(r["topic_correct"] for r in rows[1:]),
        "fallback_trace": all(
            any(
                t["step"] == "provider_fallback" and r["fallback_reason"] in t["detail"]
                for t in r["trace"]
            )
            for r in rows[2:4]
        ),
    }
    return {
        "execution": "offline injected HTTP 429 through real router and conversational runner",
        "rows": rows,
        "calls": calls,
        "checks": checks,
        "passed": all(checks.values()),
    }


def before_after_table(before, after):
    if before and after:
        before_mode = before.get("execution") or (
            "live provider" if before.get("phase") == "before" else None
        )
        after_mode = after.get("execution")
        if before_mode and after_mode and before_mode != after_mode:
            raise ValueError("Live and offline results cannot form a before/after comparison")
        names = {"current.json", "unsupported.json", "low_confidence.json"}
        before_hashes = {
            key: value for key, value in before.get("fixture_sha256", {}).items() if key in names
        }
        after_hashes = {
            key: value for key, value in after.get("fixture_sha256", {}).items() if key in names
        }
        if before_hashes != after_hashes:
            raise ValueError("Before/after fixtures differ; the results are not comparable")
        if before.get("provider_requested") != after.get("provider_requested"):
            raise ValueError("Before/after provider requests differ")
        if (
            before.get("expectation_sha256")
            and after.get("expectation_sha256")
            and before["expectation_sha256"] != after["expectation_sha256"]
        ):
            raise ValueError("Before/after expectations differ; the results are not comparable")
    metrics = (
        "completed",
        "errors",
        "timeouts",
        "skipped",
        "followup_resolution_accuracy",
        "scope_preservation_accuracy",
        "mean_requested_rep_coverage",
        "complete_requested_rep_coverage_rate",
        "unrequested_repetition_rate",
        "unsupported_claim_rate",
        "semantic_review_needed_rate",
        "fabrication_rate_bait",
        "content_fallback_correctness",
        "evidence_minimality_mean_data_points",
        "median_ms",
        "p95_ms",
        "median_model_first_token_ms",
        "median_first_visible_ms",
    )
    lines = ["| Metric | Before | After |", "| --- | ---: | ---: |"]
    for metric in metrics:
        values = [
            artifact.get("summary", {}).get(metric) if artifact else None
            for artifact in (before, after)
        ]
        formatted = [
            "not measured"
            if value is None
            else f"{value:.3f}"
            if isinstance(value, float)
            else str(value)
            for value in values
        ]
        lines.append(f"| {metric} | {formatted[0]} | {formatted[1]} |")
    if before and before.get("baseline_kind") != "retained legacy path at recorded revision":
        lines.extend(
            [
                "",
                "The older baseline predates independent expectations; missing metrics are not retrospectively inferred.",
            ]
        )
    if before and after and before.get("code_sha256") != after.get("code_sha256"):
        lines.extend(
            [
                "",
                "Code revisions differ as recorded by hashes. New --phase before runs use the retained legacy path at the current revision, not a recovered audit-start snapshot.",
            ]
        )
    if (
        before
        and after
        and {(r.get("case"), r.get("turn")) for r in before.get("rows", [])}
        != {(r.get("case"), r.get("turn")) for r in after.get("rows", [])}
    ):
        lines.extend(
            [
                "",
                "Case/turn coverage differs. These are unpaired observed totals; no provider improvement is inferred from unequal coverage.",
            ]
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after"])
    parser.add_argument(
        "--engine",
        choices=["natural", "verified"],
        default="natural",
        help="Evaluate the conversational tool writer, or explicit selector protocol diagnostics.",
    )
    parser.add_argument(
        "--suite",
        choices=["standard", "scope"],
        default="standard",
        help="Scope checks retain subject/phase/role and cover available requested repetitions.",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=["gemini", "local", "bedrock"],
        default=["gemini", "local"],
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Maximum attempted turns per provider; zero means all"
    )
    parser.add_argument("--forced-switch", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--turn-timeout-seconds", type=float, default=60)
    parser.add_argument("--max-provider-failures", type=int, default=2)
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"))
    parser.add_argument("--worker-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_request and args.worker_output:
        _worker(args.worker_request, args.worker_output)
        return
    if args.compare:
        artifacts = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.compare]
        modes = [artifact.get("execution") for artifact in artifacts]
        if all(modes) and modes[0] != modes[1]:
            parser.error("Live and offline results cannot form a before/after comparison")
        try:
            print(before_after_table(*artifacts))
        except ValueError as exc:
            parser.error(str(exc))
        return
    if not args.phase:
        parser.error("--phase is required except with --compare")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        parser.error("--run-id must contain only letters, digits, underscore or hyphen")
    if args.turn_timeout_seconds <= 0 or args.max_provider_failures <= 0:
        parser.error("Timeout and maximum failures must be positive")
    if args.offline and args.phase != "after":
        parser.error("--offline requires --phase after; selector cannot exercise the legacy writer")
    if args.offline and args.engine != "verified":
        parser.error(
            "--offline requires --engine verified; natural writer quality needs live calls"
        )
    if args.forced_switch:
        output = FIXTURES / f"forced-switch-{args.run_id}.json"
        if output.exists():
            parser.error("Forced-switch output already exists; choose a different --run-id")
        result = {"schema_version": SCHEMA_VERSION, **fingerprints(), **forced_switch_scenario()}
        save_artifact(output, result)
        print(json.dumps({"output": str(output), "checks": result["checks"]}))
        raise SystemExit(0 if result["passed"] else 1)
    cases = scope_scenarios() if args.suite == "scope" else scenarios()
    dataset = FIXTURES / (
        "conversations-scope-v1.json" if args.suite == "scope" else "conversations-v2.json"
    )
    serialized = json.dumps(cases, indent=2)
    if not dataset.exists():
        dataset.write_text(serialized, encoding="utf-8")
    elif json.loads(dataset.read_text(encoding="utf-8")) != cases:
        parser.error(f"{dataset.name} differs from expectations; review/update it explicitly")
    for provider in args.providers:
        output = FIXTURES / (
            f"{'scope-' if args.suite == 'scope' else ''}{args.phase}-{provider}"
            f"-{args.engine}{'-offline' if args.offline else ''}-{args.run_id}.json"
        )
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "phase": args.phase,
            "suite": args.suite,
            "engine": args.engine,
            "provider_requested": provider,
            "execution": "offline protocol fixture" if args.offline else "live provider",
            "turn_timeout_seconds": args.turn_timeout_seconds,
            "timing_scope": "Latency and TTFT include model-client setup, retrieval and rendering; process bootstrap is separate wall_clock_ms. Baseline unstreamed paths may have no model TTFT.",
            **fingerprints(cases),
        }
        if args.phase == "before":
            metadata["baseline_kind"] = "retained legacy path at recorded revision"
        try:
            artifact = load_or_create(output, metadata, args.resume)
        except ValueError as exc:
            parser.error(str(exc))
        rows = artifact["rows"]
        existing = {(r["case"], r["turn"]): r for r in rows}
        consecutive_errors, unavailable = 0, False
        for case in cases:
            base = CoachRequest.model_validate_json(
                (FIXTURES / f"{case['fixture']}.json").read_text()
            )
            history, state = [], None
            for index, question in enumerate(case["turns"]):
                prior = existing.get((case["id"], index + 1))
                if prior is not None:
                    if prior["status"] == "completed":
                        state = (
                            DialogueState.model_validate(prior["dialogue_state"])
                            if prior.get("dialogue_state")
                            else None
                        )
                        history.extend(
                            [
                                ConversationMessage(role="user", content=question),
                                ConversationMessage(role="assistant", content=prior["answer"]),
                            ]
                        )
                    else:
                        history.append(ConversationMessage(role="user", content=question))
                    continue
                if args.limit and len(rows) >= args.limit:
                    break
                request = base.model_copy(
                    update={
                        "question": question,
                        "conversation_history": history[-12:],
                        "dialogue_state": state,
                    }
                )
                row = {
                    "case": case["id"],
                    "category": case["category"],
                    "turn": index + 1,
                    "question": question,
                    "fixture": case["fixture"],
                    "expected": case["expected"][index],
                }
                if unavailable:
                    result = {"status": "skipped", "error_type": "ProviderUnreachableAfterFailures"}
                elif args.offline:
                    result = _run_turn(
                        {
                            "request": request.model_dump(mode="json"),
                            "provider": provider,
                            "phase": args.phase,
                            "engine": args.engine,
                            "offline": True,
                        }
                    )
                else:
                    result = bounded_turn(
                        {
                            "request": request.model_dump(mode="json"),
                            "provider": provider,
                            "phase": args.phase,
                            "engine": args.engine,
                            "offline": False,
                        },
                        args.turn_timeout_seconds,
                    )
                next_state = score_result(row, result, request)
                if row["status"] == "completed":
                    consecutive_errors = 0
                    state = DialogueState.model_validate(next_state) if next_state else None
                    history.extend(
                        [
                            ConversationMessage(role="user", content=question),
                            ConversationMessage(role="assistant", content=row["answer"]),
                        ]
                    )
                else:
                    history.append(ConversationMessage(role="user", content=question))
                    if row.get("provider_failure") or row.get("error_type") in {
                        "RuntimeError",
                        "ConnectionError",
                        "ModelConnectionError",
                        "EvaluationDeadline",
                        "ModelRateLimitError",
                        "ModelTimeoutError",
                        "ConnectError",
                        "ModelAPIError",
                    }:
                        consecutive_errors += 1
                    unavailable = consecutive_errors >= args.max_provider_failures
                rows.append(row)
                artifact["summary"] = summarize(rows)
                save_artifact(output, artifact)
                print(
                    provider,
                    row["case"],
                    row["turn"],
                    row["status"],
                    row.get("error_type", ""),
                    flush=True,
                )
            if args.limit and len(rows) >= args.limit:
                break
        artifact["summary"] = summarize(rows)
        artifact["finished_at"] = datetime.now(UTC).isoformat()
        artifact["latency_target"] = (
            "Gemini ordinary cached questions: 2000-3000 ms"
            if provider == "gemini"
            else "Local budget requires live hardware measurements; offline timing is excluded"
        )
        save_artifact(output, artifact)
        print(json.dumps({"output": str(output), "summary": artifact["summary"]}), flush=True)


if __name__ == "__main__":
    main()

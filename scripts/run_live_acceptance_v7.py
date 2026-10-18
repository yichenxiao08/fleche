"""Isolated HTTP acceptance runs. Replies are saved verbatim for manual assessment."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import run_fewshot_v7_ship_review as shipping

from fencecoach.coach.core_packet import PROMPT_REVISION

review = shipping.review
ROOT = review.ROOT
WORK = ROOT / "work/live_acceptance_v7"
LEDGER = review.LEGACY / "live-acceptance-v7"
MANIFESTS = review.LEGACY / "fewshot-v7.6"
CASES = WORK / "cases.json"
CRITERIA = [
    "No KB/reference/coaching-guidance naming",
    "No invented targets, cutoffs, drills or measurements",
    "Plain first-sentence verdict when a cue and readings exist",
    "Follow-ups retain the right topic and rep",
    "State survives the forced Groq-to-Gemini fallback",
    "No unanswered question sent as pending history",
    "Rejected/unsupported tracking withheld; athlete-selection abstention works",
    "Typical replies have two to four sentences and at most two numbers",
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_sources():
    for provider in shipping.ORDERS:
        manifest = read(MANIFESTS / review.SLUGS[provider] / "manifest.json")
        changed = [
            name
            for name, digest in manifest["sha256"].items()
            if hashlib.sha256(
                json.dumps(review.CHAINS).encode()
                if name == "questions"
                else (ROOT / name).read_bytes()
            ).hexdigest()
            != digest
        ]
        if changed:
            raise RuntimeError(
                "Frozen source mismatch; stop without repairs: " + ", ".join(changed)
            )


def cooldown(provider):
    statuses = [
        review.LEGACY / review.SLUGS[provider] / "status.json",
        *review.LEGACY.glob(f"*/{review.SLUGS[provider]}/status.json"),
    ]
    return max(
        [
            review.ledger_resume_after(provider),
            *(review.saved_resume_after(provider, path) for path in statuses),
        ]
    )


def stopped_in_run(provider, execution_id):
    return any(
        record.get("execution_id") == execution_id
        and record.get("error")
        and record.get("reached_provider")
        and not record.get("forced")
        for record in (
            read(path) for path in (LEDGER / review.SLUGS[provider] / "requests").glob("*.json")
        )
    )


class RecordingClient:
    def __init__(self, provider, client):
        self.provider, self.client = provider, client

    def invoke(self, messages):
        control = read(WORK / "control.json")
        forced = self.provider in control.get("force_failure", [])
        started = time.time()
        record = {
            **control,
            "provider": self.provider,
            "model": review.MODELS[self.provider],
            "prompt_revision": PROMPT_REVISION,
            "started_at": started,
            "forced": forced,
            "reached_provider": not forced,
            "request": [{"role": message.type, "content": message.content} for message in messages],
        }
        target = (
            LEDGER
            / review.SLUGS[self.provider]
            / "requests"
            / (f"{control['case']}-T{control['turn']}-{uuid4().hex}.json")
        )
        save(target, record)
        if forced:
            # Only these synthetic failures exercise the unchanged production router.
            from fencecoach.coach.hosted_fallback import HostedError

            error = HostedError(503, "Owner-authorized forced acceptance failure", retry_after=60)
            record.update(error=str(error), http_status=503, elapsed_ms=0)
            save(target, record)
            raise error
        try:
            response = self.client.invoke(messages)
        except Exception as exc:
            record.update(
                error=review.redact(str(exc)),
                error_type=type(exc).__name__,
                reason=review.failure_reason(exc),
                retry_after_seconds=review.provider_retry_delay(exc),
                resume_after=review.error_resume_after(self.provider, exc),
                http_status=getattr(exc, "status_code", None),
                elapsed_ms=(time.time() - started) * 1000,
            )
            save(target, record)
            save(WORK / "provider_stop.json", record)
            if self.provider == "groq" and getattr(exc, "status_code", None) in {429, 503}:
                from fencecoach.coach.core_packet import gemini_circuit

                gemini_circuit.failure("owner_stop_after_groq_error", 3600)
            # Preserve the original exception so the unchanged router can fall back.
            raise
        record.update(
            response=response.model_dump(mode="json"),
            http_status=200,
            elapsed_ms=(time.time() - started) * 1000,
        )
        save(target, record)
        return response


def serve(port):
    # These substitutions only record input/output or inject the two requested faults.
    from fencecoach.coach import core_packet
    from fencecoach.settings import settings

    if (
        settings.coach_core != "new"
        or settings.fencecoach_db_path.resolve() != (WORK / "acceptance.sqlite3").resolve()
    ):
        raise RuntimeError("Acceptance server requires its own storage and process-only new core.")
    original_groq, original_gemini = core_packet.HostedFallback, core_packet.chat_model
    core_packet.HostedFallback = lambda: RecordingClient("groq", original_groq())
    core_packet.chat_model = lambda *args, **kwargs: RecordingClient(
        "gemini", original_gemini(*args, **kwargs)
    )
    control = read(WORK / "control.json") if (WORK / "control.json").exists() else {}
    for provider, breaker in (
        ("groq", core_packet.groq_circuit),
        ("gemini", core_packet.gemini_circuit),
    ):
        if provider in control.get("force_failure", []):
            continue  # Synthetic faults make no generation call, even during quota cooldowns.
        if (
            control.get("chain_provider")
            and provider != control["chain_provider"]
            and not (control["chain_provider"] == "groq" and provider == "gemini")
        ):
            breaker.failure("chain_provider_pinned", 3600)
            continue
        remaining = cooldown(provider) - time.time()
        held = (
            stopped_in_run(provider, control.get("execution_id"))
            if control.get("execution_id")
            else False
        )
        if remaining > 0 or held:
            breaker.failure(
                "saved_cooldown" if remaining > 0 else "stopped_this_run",
                max(remaining, 3600 if held else 0),
            )
    # An interrupted test process must not restart its old queue item on boot.
    from fencecoach import api

    active = read(WORK / "active_job.json") if (WORK / "active_job.json").exists() else {}
    if active.get("job_id"):
        api.coaching_jobs.cancel(active["job_id"])
    import uvicorn

    uvicorn.run("fencecoach.api:app", host="127.0.0.1", port=port, log_level="warning")


def test_environment():
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONIOENCODING": "utf-8",
            "COACH_CORE": "new",
            "FENCECOACH_DB_PATH": str(WORK / "acceptance.sqlite3"),
            "FENCECOACH_VIDEO_DIR": str(WORK / "videos"),
            "FENCECOACH_DATABASE_URL": "",
            "FENCECOACH_S3_BUCKET": "",
            "FENCECOACH_VIDEO_WORKER": "false",
            "FENCECOACH_AUTOMATIC_TRAINING": "false",
            "FENCECOACH_SEED_EXAMPLES": "false",
            "FENCECOACH_LOCAL_FALLBACK": "false",
            "FENCECOACH_PHOENIX_ENDPOINT": "",
        }
    )
    return env


def fetch(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def ordered_cases(cases):
    """Finish a started chain in the owner's v7.2 acceptance order."""
    order = ["L01", "L06", "L05", "L07", "L04", "L10", "L02", "L03", "L09", "L08"]
    active = [c["id"] for c in cases if 0 < len(c["turns"]) < len(c["questions"])]
    return sorted(cases, key=lambda c: (c["id"] not in active, order.index(c["id"])))


def candidates_for(case, forced):
    if forced == ["groq"]:
        return ["gemini"]
    if case["id"] == "L10":
        return ["gemini"] if len(case["turns"]) >= 2 else ["groq"]
    if case["id"] != "L10" and case["turns"]:
        return [case["turns"][-1]["run"]["mode"]]
    return ["groq"]


def reconcile(client, cases, path=None):
    """Recover replies committed by the app before a harness interruption."""
    for case in cases:
        reports = sorted(
            fetch(client, "GET", f"/api/sessions/{case['session_id']}/reports"),
            key=lambda row: row["created_at"],
        )
        if not case.get("expected_no_model"):
            reports = [
                run for run in reports if run.get("answer_contract", {}).get("model_authored", True)
            ]
        if len(reports) < len(case["turns"]) or len(reports) > len(case["questions"]):
            raise RuntimeError("Isolated stored reports do not match the acceptance record; stop.")
        for number, run in enumerate(reports, 1):
            if run["question"] != case["questions"][number - 1]:
                raise RuntimeError(
                    "Stored question sequence differs; do not regenerate or skip it."
                )
            if number <= len(case["turns"]):
                if case["turns"][number - 1]["run"]["run_id"] != run["run_id"]:
                    raise RuntimeError("Stored run identity differs; stop without overwriting.")
            else:
                case["turns"].append(
                    {
                        "turn": number,
                        "question": run["question"],
                        "run": run,
                        "wall_latency_ms": None,
                        "recovered_from_app": True,
                    }
                )
    save(path or CASES, cases)


def conversations(client, execution_id, probe=False):
    path = WORK / "both_failed.json" if probe else CASES
    cases = read(path)
    reconcile(client, cases, path)
    for case in ordered_cases(cases) if not probe else cases:
        for number, question in enumerate(case["questions"], 1):
            if number <= len(case["turns"]):
                continue
            if len(case["turns"]) != number - 1:
                raise RuntimeError("An earlier stored reply is missing; stop this chain.")
            control = read(WORK / "control.json")
            if (control["case"], control["turn"]) != (case["id"], number):
                save(
                    WORK / "status.json",
                    {
                        "status": "reconciled_reply_prefix",
                        "detail": "Recovered a stored reply; restart the child for the next turn, without regenerating.",
                    },
                )
                render()
                return
            if case["id"] == "L05" and number == 2 and not case.get("option_selected_from_reply"):
                save(
                    WORK / "status.json",
                    {
                        "status": "awaiting_topic_selection",
                        "detail": "Read L05-T1, choose one of its offered topics, then save that choice in cases.json.",
                    },
                )
                return
            forced = ["groq"] if case["id"] == "L10" and number == 3 else []
            if probe:
                forced = ["groq", "gemini"]
            candidates = candidates_for(case, forced)
            eligible = [
                provider
                for provider in candidates
                if time.time() >= cooldown(provider) and not stopped_in_run(provider, execution_id)
            ]
            if len(forced) < 2 and not eligible:
                save(
                    WORK / "status.json",
                    {
                        "status": "waiting",
                        "providers": candidates,
                        "resume_after": min(cooldown(provider) for provider in candidates),
                        "detail": f"{case['id']}-T{number} unrun",
                    },
                )
                return
            save(
                WORK / "control.json",
                {
                    "case": case["id"],
                    "turn": number,
                    "question": question,
                    "force_failure": forced,
                    "execution_id": execution_id,
                },
            )
            before = time.time()
            save(WORK / "status.json", {"status": "running", "detail": f"{case['id']}-T{number}"})
            job = fetch(
                client,
                "POST",
                f"/api/sessions/{case['session_id']}/coaching-jobs",
                json={"question": question, "mode": "gemini"},
            )
            save(
                WORK / "active_job.json",
                {"job_id": job["job_id"], "case": case["id"], "turn": number},
            )
            while job["status"] in {"queued", "running"}:
                # Polling this queue never submits another generation request.
                if time.time() - before > 65:
                    fetch(client, "POST", f"/api/coaching-jobs/{job['job_id']}/cancel")
                    raise RuntimeError("Queued chat timed out; no generation retry.")
                time.sleep(0.3)
                job = fetch(client, "GET", f"/api/coaching-jobs/{job['job_id']}")
            if job["status"] != "completed":
                case["errors"].append({"turn": number, "job": job})
                save(path, cases)
                save(WORK / "status.json", {"status": "blocked", "detail": job})
                return
            run = fetch(client, "GET", f"/api/reports/{job['run_id']}")
            if not run.get("answer_contract", {}).get("model_authored") and not probe:
                case["errors"].append(
                    {"turn": number, "run": run, "status": "PENDING — no provider reply"}
                )
                save(path, cases)
                save(WORK / "active_job.json", {})
                save(
                    WORK / "status.json",
                    {
                        "status": "waiting",
                        "detail": f"{case['id']}-T{number}",
                        "resume_after": min(cooldown(provider) for provider in ("groq", "gemini")),
                    },
                )
                render()
                return
            case["turns"].append(
                {
                    "turn": number,
                    "question": question,
                    "run": run,
                    "wall_latency_ms": (time.time() - before) * 1000,
                }
            )
            save(path, cases)
            save(WORK / "active_job.json", {})
            render()
            print(f"{case['id']}-T{number} saved verbatim", flush=True)
            # Return for manual reading after each turn; never retry within this invocation.
            save(
                WORK / "status.json",
                {"status": "awaiting_manual_reading", "detail": f"{case['id']}-T{number}"},
            )
            return
    save(WORK / "status.json", {"status": "awaiting_manual_assessment"})


def render():
    cases = read(CASES)
    count = sum(len(case["turns"]) for case in cases)
    assessment = read(WORK / "assessment.json") if (WORK / "assessment.json").exists() else {}
    lines = [
        "# Frozen v7.6 live acceptance (earlier accepted chains retained)",
        "",
        f"**Pending shipping gate: {count} live replies saved. Default remains `old`.**",
        "No live criterion is marked PASS without transcript or protocol evidence. "
        "An unrun criterion is pending, not a model-quality failure.",
        "",
        "## Isolation and execution",
        "",
        "`COACH_CORE=new` is set only in the isolated child process. Ten saved-session "
        "copies use `work/live_acceptance_v7/acceptance.sqlite3` and their own video-result "
        "directory. The real database was opened read-only; result-copy hashes match. "
        "`input_preflight.json` records the real app's evidence/packet with zero generation calls.",
        "",
        "The normal browser chat endpoints are used: POST coaching-jobs, poll that job, "
        "GET the stored report. The unchanged router tries Groq and then Gemini. A real "
        "Groq rate limit can fall back normally; this is not an acceptance failure. Saved "
        "provider cooldowns and stops within the same execution are restored into its circuits. "
        "Raw request/response records live outside the report, under the uncommitted provider ledger.",
        "",
        "Owner-approved v7.6 order: fresh L04, L10, L02, L03 only. "
        "Other accepted chains remain at their recorded versions. Finish each started chain before switching. "
        "Keep each chain on its first successful provider, except L10's required real "
        "Groq-to-Gemini switch. Old v7 evidence is preserved in live_acceptance_v7_archive.md. "
        "No reading prerequisite; BF01 remains a completed separate no-generation probe.",
        "",
        "## Acceptance decisions",
        "",
    ]
    for number, criterion in enumerate(CRITERIA, 1):
        result = assessment.get(str(number), {})
        lines += [
            f"{number}. **{result.get('status', 'PENDING')}** — {criterion}. "
            + result.get("evidence", "No completed live evidence yet.")
        ]
    lines += ["", "## Ten conversations", ""]
    for case in cases:
        lines += [f"### {case['id']} — {case['title']}", ""]
        by_turn = {turn["turn"]: turn for turn in case["turns"]}
        for number, question in enumerate(case["questions"], 1):
            lines += [f"#### Turn {number}", "", "Athlete: " + question, ""]
            if number not in by_turn:
                attempted = [error for error in case["errors"] if error.get("turn") == number]
                lines += [
                    "**PENDING — provider unavailable; no model reply.** See the saved attempt below."
                    if attempted
                    else "**UNRUN.** No reply, provider latency or fallback result.",
                    "",
                ]
                continue
            turn = by_turn[number]
            run = turn["run"]
            wall_time = (
                f"{turn['wall_latency_ms'] / 1000:.3f}s"
                if turn["wall_latency_ms"] is not None
                else "unknown (recovered stored reply)"
            )
            provider = (
                run["mode"] if run.get("answer_contract", {}).get("model_authored") else "none"
            )
            lines += [
                f"Provider/model: {provider} / {run['model_id'] if provider != 'none' else 'none'}; prompt: {run.get('answer_contract', {}).get('prompt_revision', 'fewshot-v7')}; "
                f"core latency {run['latency_ms'] / 1000:.3f}s; "
                f"HTTP/queue latency {wall_time}; "
                f"fallback reason: {run.get('fallback_reason') or 'none'}.",
                "",
                "Coach: " + run["report"]["summary"],
                "",
            ]
        if case["errors"]:
            lines += ["Saved pending provider attempts (not acceptance failures):", ""]
            for error in case["errors"]:
                if error.get("run"):
                    run = error["run"]
                    lines += [
                        f"{case['id']}-T{error['turn']}; provider: none; prompt: {run.get('answer_contract', {}).get('prompt_revision', 'fewshot-v7')}; "
                        f"core latency {run['latency_ms'] / 1000:.3f}s; queue latency unknown; "
                        f"fallback reason: {run.get('fallback_reason')}.",
                        "",
                        "Stored plain connection reply: " + run["report"]["summary"],
                        "",
                        "Provider attempts: "
                        + json.dumps(run["answer_contract"]["provider_attempts"]),
                        "",
                        f"Raw app report retained in the isolated database as {run['run_id']}. "
                        "Full provider request/error records remain in the raw ledger. No turn was advanced.",
                        "",
                    ]
                else:
                    lines += ["```json", json.dumps(error, ensure_ascii=False, indent=2), "```", ""]
    probe_path = WORK / "both_failed.json"
    if probe_path.exists():
        lines += ["## Both providers failed — separate no-generation probe", ""]
        for row in read(probe_path):
            for turn in row["turns"]:
                run = turn["run"]
                lines += [
                    f"{row['id']}-T{turn['turn']}; provider: none; "
                    f"fallback reason: {run.get('fallback_reason')}; "
                    f"core latency {run['latency_ms'] / 1000:.3f}s.",
                    "",
                    "Athlete: " + turn["question"],
                    "",
                    "Coach: " + run["report"]["summary"],
                    "",
                ]
        lines += [
            "This synthetic provider-failure probe makes zero generation requests. "
            "It does not establish state carry-over to real Gemini; L10-T3 remains required.",
            "",
        ]
    lines += ["## Provider latency", ""]
    measured = {}
    for folder in LEDGER.glob("*/requests"):
        for path in folder.glob("*.json"):
            attempt = read(path)
            if not attempt.get("forced") and (attempt.get("response") or attempt.get("error")):
                measured.setdefault(attempt["provider"], []).append(attempt)
    for provider in ("groq", "gemini"):
        attempts = measured.get(provider, [])
        lines += [
            f"- {provider}: "
            + (
                "no live response yet; latency unknown."
                if not attempts
                else "; ".join(
                    f"{row['case']}-T{row['turn']} {row['elapsed_ms'] / 1000:.3f}s "
                    f"(HTTP {row.get('http_status', 'unknown')})"
                    for row in attempts
                )
            )
        ]
    lines += [
        "",
        "## Unresolved issues",
        "",
        "Shipping remains pending until all eight live acceptance criteria pass. "
        "The separate both-failed result is recorded above; real Gemini state carry-over "
        "still requires L10-T3. "
        "Reference ranges remain unapproved and unloaded. Only the approved persona/reminder "
        "clarification and connection-exchange history exclusion changed for v7.1. "
        "Authored KB, map, examples, packet/resolver and default remain unchanged; no commit/push. "
        "The v7 L01-T3 criterion2 FAIL remains archived; v7.1 does not erase that result.",
        "",
    ]
    for provider in ("groq", "gemini"):
        resume = cooldown(provider)
        if resume:
            utc = datetime.fromtimestamp(resume, UTC)
            lines += [
                f"Saved {provider} resume_after: {utc.isoformat()} UTC / "
                f"{utc.astimezone(ZoneInfo('America/Toronto')).isoformat()} Toronto.",
                "",
            ]
    (ROOT / "docs/live_acceptance.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "run", "report", "serve", "both-failed"])
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.action == "serve":
        serve(args.port)
        return
    if args.action == "run":
        for path in [*review.LEGACY.rglob("status.json"), WORK / "status.json"]:
            if (
                path.exists()
                and read(path).get("status") == "running"
                and time.time() - path.stat().st_mtime < 180
            ):
                print("Recently running live/eval process; no duplicate started.")
                return
    verify_sources()
    render()
    if args.action == "report":
        return
    execution_id = args.run_id or datetime.now(UTC).isoformat()
    if args.action in {"run", "both-failed"}:
        probe = args.action == "both-failed"
        cases = read(WORK / "both_failed.json" if probe else CASES)
        if not probe:
            cases = ordered_cases(cases)
        pending = [
            (case, number, question)
            for case in cases
            for number, question in enumerate(case["questions"], 1)
            if number > len(case["turns"])
        ]
        if not pending:
            print("All requested replies already stored; no duplicate attempt.")
            return
        case, number, question = pending[0]
        forced = (
            ["groq", "gemini"] if probe else ["groq"] if case["id"] == "L10" and number == 3 else []
        )
        candidates = candidates_for(case, forced)
        eligible = [
            provider
            for provider in candidates
            if time.time() >= cooldown(provider) and not stopped_in_run(provider, execution_id)
        ]
        if not probe and not eligible:
            resume = min(cooldown(provider) for provider in candidates)
            save(
                WORK / "status.json",
                {
                    "status": "waiting",
                    "resume_after": resume,
                    "detail": f"{case['id']}-T{number}: all usable providers cooling or stopped this run",
                },
            )
            print("Saved provider cooldowns active; no generation sent.")
            return
        if not probe:
            provider = eligible[0]
            starts = [
                read(path).get("started_at", 0)
                for path in (LEDGER / review.SLUGS[provider] / "requests").glob("*.json")
                if read(path).get("reached_provider")
            ]
            delay = max(starts, default=0) + (65 if provider == "groq" else 15) - time.time()
            while delay > 0:
                time.sleep(min(delay, 20))
                delay = max(starts, default=0) + (65 if provider == "groq" else 15) - time.time()
        save(
            WORK / "control.json",
            {
                "case": case["id"],
                "turn": number,
                "question": question,
                "force_failure": forced,
                "execution_id": execution_id,
                "chain_provider": (
                    "groq"
                    if case["id"] == "L10" and number < 3
                    else "gemini"
                    if case["id"] == "L10" and number >= 3
                    else case["turns"][-1]["run"]["mode"]
                    if case["turns"] and case["id"] != "L10"
                    else "groq"
                ),
            },
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (WORK / "server.log").open("a", encoding="utf-8") as log:
        if args.action == "run":
            save(WORK / "status.json", {"status": "running", "execution_id": execution_id})
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)],
            cwd=ROOT,
            env=test_environment(),
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=15
            ) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Isolated app exited; inspect its test-only server.log.")
                    try:
                        fetch(client, "GET", "/health")
                        break
                    except httpx.ConnectError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Isolated app did not start.")
                if args.action == "preflight":
                    session = fetch(client, "GET", "/api/sessions/live-v7-L01")
                    save(
                        WORK / "http_preflight.json",
                        {
                            "at": datetime.now(UTC).isoformat(),
                            "session_id": session["session_id"],
                            "http_health": 200,
                            "generation_requests": 0,
                            "core": "new",
                        },
                    )
                    print(
                        "Real app HTTP preflight passed with isolated storage; zero generation calls."
                    )
                else:
                    conversations(client, execution_id, probe=args.action == "both-failed")
        finally:
            process.terminate()
            process.wait(timeout=10)
            render()


if __name__ == "__main__":
    main()

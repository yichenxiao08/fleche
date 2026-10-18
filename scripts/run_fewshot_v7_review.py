"""Fresh, resumable readings of the v5 writer; no output evaluation."""

import argparse
import hashlib
import json
import math
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from eval_conversational_coach import CHAINS, redact
from run_coach_model_review import MODELS, SLUGS, SOURCES, RecordedClient
from run_coach_targeted_review import write

from fencecoach.coach.core_packet import PROMPT_REVISION, run_packet_core, writer_reference
from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.providers import chat_model
from fencecoach.coach.router import failure_reason, retry_after
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState
from fencecoach.settings import settings

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "evals/conversational_kb/model_review"
OUT = LEGACY / "fewshot-v7"
ORDER = [1, 3, 13, 19]
ORDERS = {"groq": [1, 3, 13, 19], "gemini": [1, 3, 13, 19]}
FROZEN = tuple(
    dict.fromkeys(
        (
            *SOURCES,
            "scripts/run_fewshot_v7_review.py",
            "src/fencecoach/coach/intent.py",
            "src/fencecoach/coach/core_new.py",
            "src/fencecoach/schemas.py",
            "src/fencecoach/settings.py",
            "evals/layer2/inputs.json",
        )
    )
)


def rows(provider):
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((OUT / SLUGS[provider]).glob("C*.json"))
    ]


def rating_sheet():
    path = ROOT / "docs/rating_sheet.md"
    prior, provider = {}, None
    if path.exists() and path.read_text(encoding="utf-8").startswith(
        "# Frozen fewshot-v7 rating sheet"
    ):
        for line in path.read_text(encoding="utf-8").split("\n# v6 comparison", 1)[0].splitlines():
            if line.startswith("## Groq"):
                provider = "groq"
            elif line.startswith("## Gemini"):
                provider = "gemini"
            elif provider and line.startswith("| C"):
                cells = re.split(r"(?<!\\)\|", line)[1:-1]
                if len(cells) == 7:
                    prior[(provider, cells[0].strip(), cells[1].strip())] = cells[-3:]
    lines = [
        "# Frozen fewshot-v7 rating sheet",
        "",
        "Acceptable means natural, answers the question, uses the readings where relevant, no invented content, no repeating itself. Reasons: robotic, repeated, vague, overreach, wrong, off-topic, good.",
        "",
        "Invented? means an invented target, drill, measurement or assumed problem. Blank replies are unrun or failed; see the matching raw transcript for status. Rating columns are left for the owner. Older-prompt replies are excluded.",
        "",
    ]

    def cell(value):
        return value.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")

    for provider, title in (
        ("groq", "Groq — qwen/qwen3.8-27b"),
        ("gemini", "Gemini — gemini-3.8-flash"),
    ):
        by_id = {r["id"]: r for r in rows(provider)}
        lines += [
            "## " + title,
            "",
            "| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |",
            "|---|---|---|---|---|---|---|",
        ]
        for index in ORDERS[provider]:
            ident = f"C{index:02d}"
            saved = {t["turn"]: t for t in by_id.get(ident, {}).get("turns", [])}
            for number, question in enumerate(CHAINS[index - 1][1], 1):
                answer = saved.get(number, {}).get("answer", "")
                ratings = prior.get((provider, ident, str(number)), [" ", " ", " "])
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            ident,
                            str(number),
                            cell(question),
                            cell(answer),
                            *[r.strip() for r in ratings],
                        ]
                    )
                    + " |"
                )
        lines.append("")
    lines += [
        "# v6 comparison (archived)",
        "",
        (ROOT / "docs/rating_sheet_v6_archive.md").read_text(encoding="utf-8"),
        "V4 rows remain separately archived in [rating_sheet_v4_archive.md](rating_sheet_v4_archive.md).",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render(provider):
    selected = rows(provider)
    turns = [t for r in selected for t in r["turns"]]
    errors = [e for r in selected for e in r["errors"]]
    times = sorted(t["latency_ms"] / 1000 for t in turns)
    lines = [
        f"# {MODELS[provider]} — frozen fewshot-v7 fresh pass",
        "",
        f"{len(turns)}/{4 * len(ORDERS[provider])} successful replies; {len(errors)} saved failed attempts.",
        "All successful replies use the same fewshot-v7 full-KB writer with completed-pair history only. No archived replies or history are mixed into this pass; no model substitutions, output evaluation or rewriting. Failures and unrun turns remain visible.",
        "Prior readings: [archived Qwen](coach_qwen_conversations_frozen_v6.md), [archived Gemini](coach_gemini_conversations_frozen_v6.md). [Blank owner rating sheet](rating_sheet.md).",
        "",
    ]
    if times:
        lines += [
            f"Successful latency excluding pacing: median {median(times):.2f}s; p95 {times[math.ceil(len(times) * 0.95) - 1]:.2f}s.",
            "",
        ]
    status = OUT / SLUGS[provider] / "status.json"
    if status.exists():
        s = json.loads(status.read_text(encoding="utf-8"))
        lines += ["Pass status: " + s["status"] + ". " + s.get("detail", ""), ""]
    by_id = {r["id"]: r for r in selected}
    for index in ORDERS[provider]:
        ident = f"C{index:02d}"
        row = by_id.get(ident, {"turns": [], "errors": []})
        for number, question in enumerate(CHAINS[index - 1][1], 1):
            lines += [f"## {ident} — Turn {number}", "", "You: " + question, ""]
            turn = next((t for t in row["turns"] if t["turn"] == number), None)
            failed = [e for e in row["errors"] if e["turn"] == number]
            if turn:
                run = turn["run"]
                usage = (
                    f"{run['input_tokens']} input + {run['output_tokens']} output = {run['input_tokens'] + run['output_tokens']} total"
                    if run.get("token_usage_available")
                    else "unknown provider usage"
                )
                lines += [
                    f"Provider: {provider} / {MODELS[provider]}; prompt: {turn['prompt_revision']}; {turn['latency_ms'] / 1000:.2f}s; tokens: {usage}.",
                    f"Cache-read tokens: {turn['cache_read_tokens'] if turn['cache_read_tokens'] is not None else 'unknown (field absent)'}.",
                    "Thought tokens: "
                    + str(
                        turn.get("thought_tokens")
                        if turn.get("thought_tokens") is not None
                        else "unknown (not reported)"
                    )
                    + ".",
                    "",
                    "Coach: " + turn["answer"],
                    "",
                ]
                if failed:
                    lines += [
                        "Earlier failed attempts preserved: "
                        + "; ".join(e["record"] for e in failed),
                        "",
                    ]
            elif failed:
                error = failed[-1]
                label = (
                    "Outage"
                    if provider == "gemini" or error.get("reason") in {"transient", "rate_limit"}
                    else "Failed"
                )
                lines += [
                    f"**{label} — {provider} / {MODELS[provider]}; prompt: fewshot-v7.** "
                    + error["detail"],
                    "No coach reply. Actual token usage unknown. Request/error saved: "
                    + error["record"],
                    "",
                ]
            else:
                lines += [
                    f"**Unrun — {provider} / {MODELS[provider]}; prompt: fewshot-v7.** No reply; latency and tokens unknown.",
                    "",
                ]
    (ROOT / f"docs/coach_{SLUGS[provider]}_conversations.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    rating_sheet()


def stored_reply_prefix(row):
    """A chain may resume only after a contiguous prefix of stored replies."""
    by_turn = {t["turn"]: t for t in row["turns"]}
    prefix = []
    for number in range(1, 5):
        turn = by_turn.get(number)
        if turn is None or not turn.get("answer", "").strip():
            break
        prefix.append(turn)
    if len(prefix) != len(row["turns"]):
        raise ValueError(
            "Non-contiguous or empty stored replies: stop and record invalid evaluation input."
        )
    return prefix


PACIFIC = ZoneInfo("America/Los_Angeles")


def quota_zone(provider):
    return PACIFIC if provider == "gemini" else UTC


def next_daily_reset(provider, now=None):
    local = (now or datetime.now(UTC)).astimezone(quota_zone(provider))
    return (
        local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ).timestamp()


def provider_retry_delay(exc):
    delay = retry_after(exc)
    if delay:
        return delay
    for error in (exc, exc.__cause__, exc.__context__):
        if error is None:
            continue
        text = str(error)
        match = re.search(r"(?:retry in|try again in)\s+((?:[0-9.]+\s*[hms]\s*)+)", text, re.I)
        if match:
            return sum(
                float(n) * {"h": 3600, "m": 60, "s": 1}[unit.lower()]
                for n, unit in re.findall(r"([0-9.]+)\s*([hms])", match[1], re.I)
            )
    return 0


def error_resume_after(provider, exc, now=None):
    stamp = time.time() if now is None else now
    delay = provider_retry_delay(exc)
    if delay:
        return stamp + delay
    detail = str(exc)
    if provider == "gemini" and ("PerDay" in detail or "per day" in detail.lower()):
        return next_daily_reset(provider, datetime.fromtimestamp(stamp, UTC))
    return stamp + 65


def ledger_resume_after(provider):
    """A provider's saved actual error survives status propagation between runs."""
    folders = [LEGACY / SLUGS[provider] / "requests", *LEGACY.glob(f"*/{SLUGS[provider]}/requests")]
    return max(
        (
            json.loads(path.read_text(encoding="utf-8")).get("resume_after", 0)
            for folder in folders
            for path in folder.glob("*.json")
        ),
        default=0,
    )


def saved_resume_after(provider, path, visited=None):
    if not path.exists():
        return 0
    visited = set() if visited is None else visited
    if path in visited:
        return ledger_resume_after(provider)
    visited.add(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    detail = saved.get("detail", "")
    if re.fullmatch(
        r"(?:20|31) saved daily (?:gemini|groq) attempts reached across passes\.", detail
    ):
        return 0
    prefix = "Saved provider cooldown from "
    if detail.startswith(prefix):
        return saved_resume_after(provider, ROOT / detail[len(prefix) :].removesuffix("."), visited)
    return saved.get("resume_after", 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=MODELS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--only-chain", choices=["C01"])
    args = parser.parse_args()
    provider = args.provider
    directory = OUT / SLUGS[provider]
    directory.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        render(provider)
        return
    if PROMPT_REVISION != "fewshot-v7":
        raise SystemExit("Prompt revision changed; stop and record in pass_notes.md.")
    status_path = directory / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status["status"] == "running" and time.time() - status_path.stat().st_mtime < 180:
            print("Recently running pass; no duplicate started.")
            return
    frozen = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FROZEN}
    frozen["questions"] = hashlib.sha256(json.dumps(CHAINS).encode()).hexdigest()
    manifest = directory / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8"))["sha256"] != frozen:
            raise SystemExit(
                "Frozen source mismatch; stop and record in pass_notes.md. Do not fix or regenerate."
            )
    else:
        # New owner-authorized v5 inputs are frozen independently of archived v4.
        write(
            manifest,
            {
                "provider": provider,
                "model": MODELS[provider],
                "sha256": frozen,
                "created_at": datetime.now(UTC).isoformat(),
                "prompt_revision": PROMPT_REVISION,
            },
        )
        (directory / "writer_prompt.txt").write_text(writer_reference(), encoding="utf-8")
        for name in FROZEN:
            target = OUT / "frozen_sources" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
    for index in ORDERS[provider]:
        path = directory / f"C{index:02d}.json"
        if not path.exists():
            write(
                path,
                {
                    "id": f"C{index:02d}",
                    "source_case": CHAINS[index - 1][0],
                    "turns": [],
                    "errors": [],
                },
            )
    if args.prepare_only:
        render(provider)
        print("Fresh fewshot-v7 pass prepared; no requests sent.")
        return
    statuses = [
        LEGACY / SLUGS[provider] / "status.json",
        *LEGACY.glob(f"*/{SLUGS[provider]}/status.json"),
    ]
    for path in statuses:
        effective_resume = max(saved_resume_after(provider, path), ledger_resume_after(provider))
        if time.time() < effective_resume:
            if path != status_path:
                write(
                    status_path,
                    {
                        "status": "blocked",
                        "detail": f"Saved provider cooldown from {path.relative_to(ROOT)}.",
                        "resume_after": effective_resume,
                    },
                )
            render(provider)
            print("Saved cooldown active; no requests sent.")
            return
    settings.groq_chat_model = MODELS["groq"]
    settings.gemini_request_timeout_seconds = 30
    model = RecordedClient(
        HostedFallback()
        if provider == "groq"
        else chat_model("gemini", model_id=MODELS[provider], max_tokens=768, temperature=0.3)
    )
    ledger = directory / "requests"
    ledger.mkdir(exist_ok=True)
    last_start = max(
        (json.loads(p.read_text(encoding="utf-8"))["started_at"] for p in ledger.glob("*.json")),
        default=0,
    )
    base = {
        r["id"]: r
        for r in json.loads((ROOT / "evals/layer2/inputs.json").read_text(encoding="utf-8"))
    }
    for index in ORDERS[provider]:
        ident = f"C{index:02d}"
        if args.only_chain and ident != args.only_chain:
            continue
        path = directory / (ident + ".json")
        row = json.loads(path.read_text(encoding="utf-8"))
        state, history = None, []
        saved_turns = {t["turn"]: t for t in stored_reply_prefix(row)}
        for number, question in enumerate(CHAINS[index - 1][1], 1):
            if number in saved_turns:
                turn = saved_turns[number]
                state = DialogueState.model_validate(turn["run"]["dialogue_state"])
                history += [
                    ConversationMessage(role="user", content=question),
                    ConversationMessage(role="assistant", content=turn["answer"]),
                ]
                continue
            delay = max(0, (65 if provider == "groq" else 15) - (time.time() - last_start))
            while delay > 0:
                time.sleep(min(delay, 30))
                delay = max(0, (65 if provider == "groq" else 15) - (time.time() - last_start))
            request = CoachRequest.model_validate(base[CHAINS[index - 1][0]]["saved_request"])
            request.question, request.dialogue_state = question, state
            request.conversation_history = history[-10:]
            last_start = time.time()
            write(
                status_path,
                {"status": "running", "detail": f"Request in progress: {ident}-T{number}."},
            )
            record = {
                "provider": provider,
                "model": MODELS[provider],
                "started_at": last_start,
                "case": ident,
                "turn": number,
                "question": question,
                "prompt_revision": PROMPT_REVISION,
            }
            target = (
                ledger
                / f"{ident}-T{number}-{1 + len(list(ledger.glob(f'{ident}-T{number}-*.json')))}.json"
            )
            model.request, model.response = None, None
            try:
                run = run_packet_core(request, provider, model=model)
            except Exception as exc:
                detail, reason = redact(str(exc)), failure_reason(exc)
                record.update(
                    request=model.request,
                    error=detail,
                    error_type=type(exc).__name__,
                    reason=reason,
                    retry_after_seconds=provider_retry_delay(exc),
                    resume_after=error_resume_after(provider, exc),
                    http_status=(
                        int(re.search(r"\b(429|503)\b", detail)[1])
                        if re.search(r"\b(429|503)\b", detail)
                        else None
                    ),
                    failure_category=("quota" if "429" in detail else "outage"),
                    elapsed_ms=(time.time() - last_start) * 1000,
                )
                if model.response is not None:
                    record["response"] = model.response.model_dump(mode="json")
                write(target, record)
                error = {
                    "turn": number,
                    "detail": detail,
                    "reason": reason,
                    "record": str(target.relative_to(ROOT)),
                }
                row["errors"].append(error)
                write(path, row)
                stop = True  # End this provider run on the first outage; resume later.
                write(
                    status_path,
                    {
                        "status": "blocked" if stop else "running",
                        "detail": f"{ident}-T{number}: {detail}",
                        **({"resume_after": record["resume_after"]} if stop else {}),
                    },
                )
                render(provider)
                print(
                    f"{provider} {ident}-T{number} outage saved; {'pass stopped' if stop else 'no retry; next distinct turn'}.",
                    flush=True,
                )
                if stop:
                    return
            turn = {
                "turn": number,
                "question": question,
                "provider": provider,
                "model_id": MODELS[provider],
                "answer": run.report.summary,
                "latency_ms": run.latency_ms,
                "thought_tokens": (model.response.usage_metadata or {})
                .get("output_token_details", {})
                .get("reasoning"),
                "cache_read_tokens": run.answer_contract["provider_usage"]
                .get("input_token_details", {})
                .get("cache_read"),
                "run": run.model_dump(mode="json"),
                "prompt_revision": PROMPT_REVISION,
            }
            record.update(request=model.request, response=model.response.model_dump(mode="json"))
            write(target, record)
            row["turns"].append(turn)
            write(path, row)
            state = run.dialogue_state
            history += [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=turn["answer"]),
            ]
            write(status_path, {"status": "running", "detail": f"Last saved {ident}-T{number}."})
            render(provider)
            print(ident, number, provider, "saved", flush=True)
    write(
        status_path,
        {
            "status": "waiting" if args.only_chain else "complete",
            "detail": "Authorized single chain completed; other chains remain pending."
            if args.only_chain
            else "All requested turns have stored assistant replies. Earlier failed attempts remain archived.",
        },
    )
    render(provider)


if __name__ == "__main__":
    main()

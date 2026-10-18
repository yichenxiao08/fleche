"""Two independent, resumable single-model reading passes; no quality gates."""

import argparse
import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from eval_conversational_coach import CHAINS, redact
from run_coach_targeted_review import write

from fencecoach.coach.core_packet import PROMPT_REVISION, run_packet_core, writer_reference
from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.providers import chat_model
from fencecoach.coach.router import failure_reason, retry_after
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState
from fencecoach.settings import settings

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "evals/conversational_kb/model_review"
OUT = LEGACY / PROMPT_REVISION
PREVIOUS = LEGACY / "fewshot-v3"
RUN_ORDER = {"groq": [10, 13, 19, 5, 1, 2, 3, 4, 6, 7, 8], "gemini": [5, 13, 19, 9]}
READ_ORDER = [10, 13, 19, 5, 1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 20]
SELECTED = {provider: set(order) for provider, order in RUN_ORDER.items()}
MODELS = {"groq": "qwen/qwen3.8-27b", "gemini": "gemini-3.8-flash"}
SLUGS = {"groq": "qwen", "gemini": "gemini"}
SOURCES = (
    "src/fencecoach/coach/core_packet.py",
    "src/fencecoach/coach/turn_packet.py",
    "src/fencecoach/coach/hosted_fallback.py",
    "src/fencecoach/coach/providers.py",
    "src/fencecoach/coach/router.py",
    "knowledge/fencing_lunge_knowledge_base.md",
    "knowledge/measurement_map.md",
    "knowledge/coach_style_examples.txt",
    "scripts/run_coach_model_review.py",
)


def render(provider):
    directory = OUT / SLUGS[provider]
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("C*.json"))]
    turns = [t for row in rows for t in row["turns"]]
    timings = sorted(t["latency_ms"] / 1000 for t in turns)
    reported = [t for t in turns if t["cache_read_tokens"] is not None]
    hits = [t for t in reported if t["cache_read_tokens"] > 0]
    lines = [
        f"# {MODELS[provider]}: saved-session conversations — {PROMPT_REVISION}",
        "",
        f"{sum(len(row['turns']) == 4 and int(row['id'][1:]) in SELECTED[provider] for row in rows)}/{len(SELECTED[provider])} selected conversations complete; {len(turns)} saved replies including retained prefixes and previously read chains.",
        "Single-model pass: no provider substitutions or automatic retries. Original questions and raw replies are unchanged. Failed and unrun turns are labeled. No quality metrics table.",
        "Owner-reviewed continuation: Qwen C10, C13, C19, C05, C01–C04, C06–C08; Gemini C05, C13, C19, then C09-T3/T4. Completed replies are retained with their original prompt labels. No reruns of already-read chains. Other chains are outside this continuation scope.",
        "[Original Qwen pass (old prompt)](coach_qwen_conversations_old_prompt.md). [Style examples for owner review](../knowledge/coach_style_examples.txt).",
        "",
    ]
    if timings:
        lines += [
            f"Completed-reply latency: median {median(timings):.2f}s; p95 {timings[math.ceil(len(timings) * 0.95) - 1]:.2f}s. Deliberate request-spacing waits are excluded.",
            f"Cache telemetry: {len(reported)} replies report cached-token counts; {len(hits)} have positive counts. Missing fields mean unknown. The trimmed KB/map and examples are a shared prefix; no explicit or paid cache was created.",
            "",
        ]
    else:
        lines += [
            "No completed replies: latency and prefix caching cannot be measured for this pass yet.",
            "",
        ]
    status_path = directory / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        lines += ["Pass status: " + status["status"] + ". " + status.get("detail", ""), ""]
    by_id = {r["id"]: r for r in rows}
    for index in READ_ORDER:
        source, questions = CHAINS[index - 1]
        ident = f"C{index:02d}"
        row = by_id.get(ident, {"turns": [], "errors": []})
        lines += [f"## {ident} — saved case {source}", ""]
        for number, question in enumerate(questions, 1):
            turn = next((t for t in row["turns"] if t["turn"] == number), None)
            lines += [f"### Turn {number}", "", "You: " + question, ""]
            if turn:
                lines += [
                    f"Provider: {provider} / {turn['model_id']}; {turn['latency_ms'] / 1000:.2f}s; prompt: {turn.get('prompt_revision', 'old-prompt')}",
                    "Tokens: "
                    + (
                        f"{turn['run']['input_tokens']} input, {turn['run']['output_tokens']} output; "
                        f"{turn['run']['input_tokens'] + turn['run']['output_tokens']} total."
                        if turn["run"].get("token_usage_available")
                        else "provider did not report usage."
                    ),
                    "",
                    "Coach: " + turn["answer"],
                    "",
                ]
            else:
                errors = [e for e in row["errors"] if e["turn"] == number]
                if index not in SELECTED[provider]:
                    lines += ["**Outside requested continuation scope — no request sent.**", ""]
                elif errors:
                    lines += [
                        f"**{'Outage' if '503' in errors[-1]['detail'] else 'Failed'} — {provider} / {MODELS[provider]}**: "
                        + errors[-1]["detail"],
                        "",
                    ]
                else:
                    lines += [
                        f"**Unrun — {provider} / {MODELS[provider]}**. No reply was generated.",
                        "",
                    ]
    destination = ROOT / f"docs/coach_{SLUGS[provider]}_conversations.md"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RecordedClient:
    def __init__(self, client):
        self.client = client
        self.request = None
        self.response = None

    def invoke(self, messages):
        self.request = [{"role": m.type, "content": m.content} for m in messages]
        self.response = self.client.invoke(messages)
        return self.response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=MODELS)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--max-new-turns", type=int)
    args = parser.parse_args()
    provider = args.provider
    directory = OUT / SLUGS[provider]
    directory.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        render(provider)
        return
    settings.groq_chat_model = MODELS["groq"]
    settings.gemini_request_timeout_seconds = 30
    frozen = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    frozen["questions"] = hashlib.sha256(json.dumps(CHAINS).encode()).hexdigest()
    manifest = directory / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8"))["sha256"] != frozen:
            raise SystemExit(
                "Inputs changed since this pass was frozen; preserve it and choose a new pass directory."
            )
    else:
        write(
            manifest,
            {
                "provider": provider,
                "model": MODELS[provider],
                "sha256": frozen,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        (directory / "writer_prompt.txt").write_text(writer_reference(), encoding="utf-8")
    base = {
        row["id"]: row
        for row in json.loads((ROOT / "evals/layer2/inputs.json").read_text(encoding="utf-8"))
    }
    for index, (source, _) in enumerate(CHAINS, 1):
        path = directory / f"C{index:02d}.json"
        if not path.exists():
            row = {"id": f"C{index:02d}", "source_case": source, "turns": [], "errors": []}
            # Carry every completed prefix verbatim; never spend tokens to recreate it.
            old = PREVIOUS / SLUGS[provider] / path.name
            if old.exists():
                previous_row = json.loads(old.read_text(encoding="utf-8"))
                row["turns"] = previous_row["turns"]
                row["errors"] = previous_row["errors"]
                row["original_prefix_source"] = str(old.relative_to(ROOT))
            write(path, row)
    if args.prepare_only:
        render(provider)
        print("Frozen revision prepared; no provider requests sent.")
        return
    status_path = directory / "status.json"
    if status_path.exists():
        saved_status = json.loads(status_path.read_text(encoding="utf-8"))
        if time.time() < saved_status.get("resume_after", 0):
            render(provider)
            print("Provider cooldown has not elapsed; no requests sent.", flush=True)
            return
    interval = 65 if provider == "groq" else 15
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
    render(provider)
    completed_now = 0
    for index in RUN_ORDER[provider]:
        source, questions = CHAINS[index - 1]
        ident = f"C{index:02d}"
        path = directory / (ident + ".json")
        row = json.loads(path.read_text(encoding="utf-8"))
        state, history = None, []
        for turn in row["turns"]:
            state = DialogueState.model_validate(turn["run"]["dialogue_state"])
            history += [
                ConversationMessage(role="user", content=turn["question"]),
                ConversationMessage(role="assistant", content=turn["answer"]),
            ]
        for number, question in enumerate(questions, 1):
            if number <= len(row["turns"]):
                continue
            if args.max_new_turns is not None and completed_now >= args.max_new_turns:
                render(provider)
                return
            if any(ledger.glob(f"{ident}-T{number}-*.json")):
                print(
                    f"{ident}-T{number} already attempted on this revision; wait for owner review."
                )
                render(provider)
                return
            # Preserve the provider's previous quota reset, including across revisions.
            for old_root in (LEGACY, *sorted(LEGACY.glob("fewshot-*"))):
                if old_root == OUT:
                    continue
                old_status = old_root / SLUGS[provider] / "status.json"
                if old_status.exists():
                    previous = json.loads(old_status.read_text(encoding="utf-8"))
                    if time.time() < previous.get("resume_after", 0):
                        write(status_path, previous)
                        render(provider)
                        print("Previous-pass provider cooldown has not elapsed; no request sent.")
                        return
            day = datetime.now(UTC).date()
            ledgers = [
                LEGACY / SLUGS[provider] / "requests",
                *LEGACY.glob(f"*/{SLUGS[provider]}/requests"),
            ]
            attempts_today = sum(
                datetime.fromtimestamp(
                    json.loads(p.read_text(encoding="utf-8"))["started_at"], UTC
                ).date()
                == day
                for folder in ledgers
                for p in folder.glob("*.json")
            )
            cap = 20 if provider == "gemini" else 31
            if attempts_today >= cap:
                write(
                    status_path,
                    {
                        "status": "blocked",
                        "detail": f"{cap} daily saved {provider} attempts reached; remaining turns unrun.",
                    },
                )
                render(provider)
                return
            delay = max(0, interval - (time.time() - last_start))
            while delay > 0:
                time.sleep(min(delay, 30))
                delay = max(0, interval - (time.time() - last_start))
            request = CoachRequest.model_validate(base[source]["saved_request"])
            request.question, request.dialogue_state = question, state
            request.conversation_history = history[-10:]
            last_start = time.time()
            record = {
                "provider": provider,
                "model": MODELS[provider],
                "started_at": last_start,
                "case": ident,
                "turn": number,
                "question": question,
                "prompt_revision": PROMPT_REVISION,
            }
            attempt = 1 + len(list(ledger.glob(f"{ident}-T{number}-*.json")))
            target = ledger / f"{ident}-T{number}-{attempt}.json"
            model.request, model.response = None, None
            try:
                run = run_packet_core(request, provider, model=model)
            except Exception as exc:
                detail = redact(str(exc))
                record.update(
                    request=model.request,
                    error=detail,
                    error_type=type(exc).__name__,
                    reason=failure_reason(exc),
                    retry_after_seconds=retry_after(exc),
                )
                if model.response is not None:
                    record["response"] = model.response.model_dump(mode="json")
                write(target, record)
                row["errors"].append(
                    {"turn": number, "detail": detail, "record": str(target.relative_to(ROOT))}
                )
                write(path, row)
                wait = max(65, retry_after(exc))
                write(
                    status_path,
                    {
                        "status": "blocked",
                        "detail": f"{ident}-T{number}: {detail}",
                        "resume_after": time.time() + wait,
                    },
                )
                render(provider)
                print(
                    f"{provider} stopped at {ident}-T{number}; remaining turns unrun. No retry or fallback.",
                    flush=True,
                )
                return
            usage = run.answer_contract["provider_usage"]
            cached = usage.get("input_token_details", {}).get("cache_read")
            turn = {
                "turn": number,
                "question": question,
                "provider": provider,
                "model_id": MODELS[provider],
                "answer": run.report.summary,
                "latency_ms": run.latency_ms,
                "cache_read_tokens": cached,
                "run": run.model_dump(mode="json"),
                "prompt_revision": PROMPT_REVISION,
            }
            record.update(request=model.request, response=model.response.model_dump(mode="json"))
            write(target, record)
            row["turns"].append(turn)
            write(path, row)
            history += [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=turn["answer"]),
            ]
            state = run.dialogue_state
            completed_now += 1
            write(status_path, {"status": "running", "detail": f"Last saved: {ident}-T{number}."})
            render(provider)
            print(ident, number, provider, "saved", flush=True)
    write(
        status_path,
        {
            "status": "complete",
            "detail": "All requested single-model four-turn chains completed on this model.",
        },
    )
    render(provider)


if __name__ == "__main__":
    main()

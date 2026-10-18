"""Same twenty chains after owner feedback; unmodified replies, paced providers."""

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from statistics import median

from eval_conversational_coach import CHAINS, redact

from fencecoach.coach.core_packet import run_packet_core, writer_reference
from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.providers import chat_model
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/conversational_kb/targeted_review"


class Paced:
    def __init__(self, model, interval):
        self.model, self.interval = model, interval
        self.last, self.wait_ms = 0.0, 0.0

    def invoke(self, messages):
        delay = max(0, self.interval - (time.monotonic() - self.last))
        while delay > 0:
            part = min(delay, 30)
            time.sleep(part)
            self.wait_ms += part * 1000
            delay = max(0, self.interval - (time.monotonic() - self.last))
        self.last = time.monotonic()
        return self.model.invoke(messages)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(4):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.1)


def latency_text(rows):
    models = {}
    for row in rows:
        for t in row["turns"]:
            if t.get("answer"):
                models.setdefault(
                    t.get("model_id") or t.get("run", {}).get("model_id", "unknown"), []
                ).append(t["latency_ms"] / 1000)
    result = []
    for model, values in sorted(models.items()):
        values.sort()
        p95 = values[max(0, math.ceil(len(values) * 0.95) - 1)]
        result.append(
            f"{model}: median {median(values):.2f}s, p95 {p95:.2f}s ({len(values)} replies; scheduling waits excluded)."
        )
    return result


def render():
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT.glob("C*.json"))]
    before = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((OUT.parent / "before_targeted_review").glob("C*.json"))
    ]
    replies = [t for r in rows for t in r["turns"] if t.get("answer")]
    lines = [
        "# Coach conversations after targeted prompt/packet feedback",
        "",
        f"{sum(len(r['turns']) == 4 and all(t.get('answer') for t in r['turns']) for r in rows)}/20 conversations complete; {len(replies)}/80 replies. Each question is unchanged from the prior planned chains. Model replies are published verbatim. No output checks or quality-metrics table.",
        "",
        "## Provider latency and caching",
        "",
        "Completed-turn latency excludes deliberate evaluation pacing and includes failed-primary overhead when fallback answered. These are mixed-model transcripts, not a controlled comparison of prompt quality. Groq requests were spaced 65 seconds apart for free-tier limits; the timings below do not promise back-to-back chat throughput.",
        "",
        *latency_text(rows),
        "",
        "Earlier pass (different prompt/packet and key; descriptive latency comparison only):",
        *latency_text(before),
    ]
    cached = [t for t in replies if (t.get("cache_read_tokens") or 0) > 0]
    reported = [t for t in replies if t.get("cache_read_tokens") is not None]
    lines += [
        "",
        f"Cache-read telemetry is available for {len(reported)} replies; positive cache reads in {len(cached)}. No explicit paid cache was created. Full knowledge-base/map text is the common prefix for both providers.",
        "Gemini reported no cache reads. Some Groq replies reported positive cached-token counts; where that field is absent, caching is unknown. Failed-only model attempts have no completed-reply latency sample.",
        "",
        "Earlier transcripts are preserved under evals/conversational_kb/before_targeted_review. Provider errors and fallback reasons remain in each raw JSON file.",
        "Input packaging was compacted during this pass to fit free-tier input limits; the authored knowledge base stayed unchanged. Each raw trace retains its exact prompt, packet and history. C13 was rerun after correcting a false missing-data status for unresolved questions; its earlier failed replies are included below.",
    ]
    for row in rows:
        lines += ["", f"## {row['id']} — saved case {row['source_case']}", ""]
        for t in row["turns"]:
            lines += [
                "",
                f"### Turn {t['turn']} — {t['provider']} / {t['model_id']}; {t['latency_ms'] / 1000:.2f}s",
                "",
                "You: " + t["question"],
                "",
                "Coach: " + (t.get("answer") or "[Provider failure retained]"),
            ]
            if t.get("fallback_reason"):
                lines += ["", "Provider note: " + t["fallback_reason"]]
    previous = OUT / "before_unresolved_subject_fix/C13.json"
    if previous.exists():
        row = json.loads(previous.read_text(encoding="utf-8"))
        lines += ["", "## Earlier C13: false missing-data packet (superseded, retained)", ""]
        for t in row["turns"]:
            lines += [
                f"### Earlier C13 turn {t['turn']} — {t['provider']} / {t['model_id']}; {t['latency_ms'] / 1000:.2f}s",
                "",
                "You: " + t["question"],
                "",
                "Coach: " + t["answer"],
                "",
            ]
    (ROOT / "docs/conversational_coach_transcripts.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main():
    from fencecoach.coach import core_packet
    from fencecoach.schemas import DialogueState

    parser = argparse.ArgumentParser()
    parser.add_argument("--groq-model", default="openai/gpt-oss-120b")
    parser.add_argument("--gemini-model", default="gemini-3.5-flash")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--groq-only", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    settings.gemini_chat_model = args.gemini_model
    settings.groq_chat_model = args.groq_model
    settings.gemini_request_timeout_seconds = args.timeout
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/conversational_coach_writer_prompt.txt").write_text(
        writer_reference(), encoding="utf-8"
    )
    base = {
        r["id"]: r
        for r in json.loads((ROOT / "evals/layer2/inputs.json").read_text(encoding="utf-8"))
    }
    primary = Paced(chat_model("gemini"), 6)
    fallback = Paced(HostedFallback(), 65)
    core_packet.chat_model = lambda provider: primary
    core_packet.HostedFallback = lambda: fallback
    timestamps = []
    for saved_path in OUT.glob("C*.json"):
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        for t in saved["turns"]:
            if t["model_id"] == args.groq_model:
                timestamps.append(datetime.fromisoformat(t["run"]["created_at"]).timestamp())
    latest = max(timestamps, default=0)
    fallback.last = time.monotonic() - max(0, time.time() - latest)
    for index, (source, questions) in enumerate(CHAINS, 1):
        ident = f"C{index:02d}"
        if args.ids and ident not in args.ids:
            continue
        path = OUT / (ident + ".json")
        row = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else dict(
                id=ident,
                source_case=source,
                session_id=base[source]["saved_request"]["session_id"],
                turns=[],
                provider_errors=[],
            )
        )
        state = None
        history = []
        for t in row["turns"]:
            history += [
                ConversationMessage(role="user", content=t["question"]),
                ConversationMessage(role="assistant", content=t["answer"]),
            ]
            state = DialogueState.model_validate(t["run"]["dialogue_state"])
        for n, question in enumerate(questions, 1):
            if n <= len(row["turns"]):
                continue
            request = CoachRequest.model_validate(base[source]["saved_request"])
            request.question = question
            request.conversation_history = history[-10:]
            request.dialogue_state = state
            pacing_before = primary.wait_ms + fallback.wait_ms
            try:
                run = (
                    run_packet_core(request, "groq", model=fallback)
                    if args.groq_only
                    else run_packet_core(request, "gemini")
                )
            except Exception as exc:
                row["provider_errors"].append(
                    dict(
                        turn=n,
                        provider="groq" if args.groq_only else "gemini",
                        model_id=args.groq_model if args.groq_only else args.gemini_model,
                        detail=redact(str(exc)),
                    )
                )
                write(path, row)
                if not args.no_render:
                    render()
                raise SystemExit("Provider failure retained, no retry loop.") from None
            usage = run.answer_contract.get("provider_usage", {})
            cached = (
                run.answer_contract.get("model_metadata", {})
                .get("raw_usage", {})
                .get("prompt_tokens_details", {})
                .get("cached_tokens")
                if run.mode == "groq"
                else usage.get("input_token_details", {}).get("cache_read")
            )
            if not run.answer_contract["model_authored"]:
                row["provider_errors"].append(
                    dict(
                        turn=n,
                        provider="both",
                        detail="Both providers failed; raw attempted run retained.",
                        run=run.model_dump(mode="json"),
                    )
                )
                write(path, row)
                if not args.no_render:
                    render()
                raise SystemExit("Both providers blocked; no invented replies or retry loop.")
            t = dict(
                turn=n,
                question=question,
                provider=run.mode,
                model_id=run.model_id,
                latency_ms=max(
                    0, run.latency_ms - (primary.wait_ms + fallback.wait_ms - pacing_before)
                ),
                evaluation_pacing_ms=primary.wait_ms + fallback.wait_ms - pacing_before,
                answer=run.report.summary,
                cache_read_tokens=cached,
                fallback_reason=run.fallback_reason,
                run=run.model_dump(mode="json"),
            )
            row["turns"].append(t)
            write(path, row)
            if not args.no_render:
                render()
            history += [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=run.report.summary),
            ]
            state = run.dialogue_state
            print(ident, n, run.mode, run.model_id, "saved", flush=True)
    print("Selected conversations finished.", flush=True)


if __name__ == "__main__":
    main()

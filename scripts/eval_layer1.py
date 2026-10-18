"""Run Layer 1 conversations on saved requests; preserve all replies and failures."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from fencecoach.coach.core_new import PERSONA, PERSONA_V1, run_new_core, standing_briefing
from fencecoach.coach.providers import chat_model, configured_model_id
from fencecoach.schemas import CoachRequest, ConversationMessage
from fencecoach.settings import settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/layer1"


def scenarios():
    evidence = json.loads((OUT / "historical_inputs.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(f"file:{ROOT / 'data/fencecoach.sqlite3'}?mode=ro", uri=True)
    current = {}
    jobs = []
    for table in ("coaching_jobs", "coaching_jobs_v2"):
        jobs.extend(json.loads(s) for (s,) in db.execute(f"SELECT payload FROM {table}"))
    for job in sorted(jobs, key=lambda p: p["created_at"]):
        current[job["request"]["session_id"]] = job["request"]
    db.close()
    cases = []
    for ep in evidence["episodes"]:
        first = ep["turns"][0]
        case = {
            **ep,
            "origin": "replay of historical questions",
            "saved_request": current[first["request"]["session_id"]],
            "seed_history": first["request"].get("conversation_history", []),
        }
        if ep["id"] == "H10":
            case["turns"] = ep["turns"] + [
                {"question": q, "origin": "new evaluation follow-up, not historical"}
                for q in ("the second rep", "why does that matter?")
            ]
        cases.append(case)
    base = current["7bbb26f13ea5467384bc7a1772c399ae"]
    for ident, name, questions in (
        (
            "E11",
            "ambiguous-and-recovery",
            [
                "how did I do?",
                "is it good?",
                "the second rep",
                "why does that matter?",
                "and my recovery?",
                "what should I focus on?",
                "anything else?",
            ],
        ),
        (
            "E12",
            "missing-data-and-fabrication-bait",
            [
                "How was my blade control?",
                "So was the blade stable during recovery?",
                "What was my real-world lunge speed in m/s?",
                "How much force did I push with?",
                "Give me the Dragonfly triple-hop drill from your library.",
                "What do you actually know from this clip?",
            ],
        ),
    ):
        cases.append(
            {
                "id": ident,
                "name": name,
                "origin": "new scripted Layer 1 evaluation on a real saved session, not historical",
                "saved_request": base,
                "seed_history": [],
                "turns": [{"question": q} for q in questions],
            }
        )
    cases.append(
        {
            **next(case for case in cases if case["id"] == "E11"),
            "id": "S11",
            "name": "final-briefing-smoke",
            "origin": "same seven-turn smoke conversation as the saved V0 final-briefing run; replayed for prompt comparison",
        }
    )
    return cases


def evaluate(case, provider, variant="v0", output_dir=None, resume=False):
    output_dir = output_dir or OUT
    output_dir.mkdir(parents=True, exist_ok=True)
    request = CoachRequest.model_validate(case["saved_request"])
    path = output_dir / f"{case['id']}-{provider}.json"
    if resume and path.exists():
        row = json.loads(path.read_text(encoding="utf-8"))
        history = [ConversationMessage.model_validate(m) for m in case["seed_history"]]
        for old_turn in row.get("turns", []):
            history.append(ConversationMessage(role="user", content=old_turn["question"]))
            if old_turn.get("answer"):
                history.append(ConversationMessage(role="assistant", content=old_turn["answer"]))
        history = history[-10:]
        start_turn = len(row.get("turns", []))
    else:
        history = [ConversationMessage.model_validate(m) for m in case["seed_history"]][-10:]
        row = {k: case[k] for k in ("id", "name", "origin")}
        row.update(
            requested_provider=provider,
            model_id=configured_model_id(provider),
            session_id=request.session_id,
            variant=variant,
            persona=PERSONA if variant == "v0" else PERSONA_V1,
            briefing=standing_briefing(request, variant),
            started_at=datetime.now(UTC).isoformat(),
            turns=[],
        )
        start_turn = 0
    model = chat_model(provider)  # Pinned: no provider fallback can masquerade as Gemini.
    for index, original in enumerate(case["turns"][start_turn:], start_turn + 1):
        turn = {k: v for k, v in original.items() if k not in {"request", "old_report"}}
        turn.update(turn=index, provider=provider, model_id=configured_model_id(provider))
        request.question = original["question"]
        request.conversation_history = history[-10:]
        request.dialogue_state = None
        started = time.perf_counter()
        try:
            run = run_new_core(request, provider, model=model, profile=variant)
            turn.update(
                answer=run.report.summary,
                latency_ms=run.latency_ms,
                trace=[x.model_dump(mode="json") for x in run.trace],
                sources=[x.model_dump(mode="json") for x in run.sources],
                contract=run.answer_contract,
                usage={"input_tokens": run.input_tokens, "output_tokens": run.output_tokens},
            )
            history.extend(
                [
                    ConversationMessage(role="user", content=request.question),
                    ConversationMessage(role="assistant", content=run.report.summary),
                ]
            )
        except Exception as exc:
            turn.update(
                error_type=type(exc).__name__,
                error=str(exc)[:1000],
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                answer=None,
                trace=[x.model_dump(mode="json") for x in getattr(exc, "layer1_trace", [])],
            )
            # Keep the user's question; don't fabricate an assistant reply for continuity.
            history.append(ConversationMessage(role="user", content=request.question))
        row["turns"].append(turn)
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "provider": provider,
                    "turn": index,
                    "latency_ms": turn["latency_ms"],
                    "answer": turn.get("answer"),
                    "error_type": turn.get("error_type"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return row


def render():
    lines = [
        "# Layer 1 transcripts",
        "",
        "Opt-in baseline, COACH_CORE default old. Each historical question below is a replay on a saved session, never a newly discovered historical conversation. E11/E12 and H10's final two turns are scripted evaluation additions. The saved measurements and capture profile are unchanged. Each chain starts with its saved preceding history, then carries actual Layer 1 replies; requests always send the last ten messages. Providers are pinned for these evaluations; no silent failover. All replies, including bad ones and errors, are retained. Latency is whole-turn completion; this baseline does not stream partial prose.",
        "",
        "## Exact persona",
        "",
        "```text",
        PERSONA,
        "```",
        "",
    ]
    rows = []
    paths = sorted(OUT.glob("*-gemini.json")) + sorted(OUT.glob("*-local.json"))
    paths += sorted((OUT / "probes").glob("*.json"))
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        if path.parent.name == "probes":
            row["id"] += "-initial-probe"
            row["origin"] += "; initial probe before correcting briefing arm-side selection"
        rows.append(row)
        lines.extend(
            [
                f"## {row['id']} — {row['name']} — {row['requested_provider']}",
                "",
                f"Session: `{row['session_id']}`. {row['origin']}. Full trace: `{path.relative_to(ROOT).as_posix()}`.",
                "",
                "Exact standing briefing:",
                "",
                "```text",
                row["briefing"],
                "```",
                "",
            ]
        )
        for turn in row["turns"]:
            lines.extend(
                [
                    f"### {row['id']}-{turn['provider']}-T{turn['turn']}",
                    "",
                    f"Provider: **{turn['provider']} / {turn['model_id']}**, latency **{turn['latency_ms'] / 1000:.2f}s**.",
                    "",
                    "User (verbatim):",
                    "",
                    "```text",
                    turn["question"],
                    "```",
                    "",
                ]
            )
            if turn.get("source"):
                lines.extend(
                    [
                        f"Historical source: `{turn['source']}`; run `{turn.get('run_id')}`.",
                        "",
                        "Old answer (verbatim):",
                        "",
                        "```text",
                        turn.get("old_answer") or "[No answer persisted]",
                        "```",
                        "",
                    ]
                )
                if turn.get("old_error"):
                    lines.extend(
                        ["Old error (verbatim):", "", "```text", turn["old_error"], "```", ""]
                    )
            elif row["id"] == "H10":
                lines.extend(["Origin: new evaluation follow-up, not historical.", ""])
            lines.extend(
                [
                    "Layer 1:",
                    "",
                    "```text",
                    turn.get("answer")
                    or f"[Provider error: {turn.get('error_type')}] {turn.get('error')}",
                    "```",
                    "",
                ]
            )
    (ROOT / "docs/layer1_transcripts.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "conversations": len(rows),
                "turns": sum(len(r["turns"]) for r in rows),
                "errors": sum(bool(t.get("error")) for r in rows for t in r["turns"]),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--providers", nargs="+", default=["gemini", "local"])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--final-briefing-smoke", action="store_true")
    parser.add_argument("--variant", choices=("v0", "v1", "v2", "v3"), default="v0")
    args = parser.parse_args()
    if not args.render_only:
        settings.coach_core = "new"
        output_dir = OUT if args.variant == "v0" else OUT / "variants" / args.variant.upper()
        for case in scenarios():
            if args.final_briefing_smoke:
                if case["id"] != "E11":
                    continue
                case = {
                    **case,
                    "id": "S11",
                    "name": "final-briefing-smoke",
                    "origin": "scripted evaluation after correcting arm-ratio meaning and adding feature inventory; not historical",
                }
            if args.ids and case["id"] not in args.ids:
                continue
            for provider in args.providers:
                path = output_dir / f"{case['id']}-{provider}.json"
                if (
                    args.resume
                    and path.exists()
                    and len(json.loads(path.read_text(encoding="utf-8"))["turns"])
                    == len(case["turns"])
                ):
                    continue
                evaluate(case, provider, args.variant, output_dir, resume=args.resume)
    if args.variant == "v0":
        render()


if __name__ == "__main__":
    main()

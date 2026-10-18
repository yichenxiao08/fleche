"""Twenty saved-session conversations; plain transcripts, no quality metrics or gates."""

import argparse
import json
from pathlib import Path

from eval_layer2 import PacedGemini, write

from fencecoach.coach.core_packet import run_packet_core, writer_reference
from fencecoach.coach.providers import chat_model
from fencecoach.schemas import CoachRequest, ConversationMessage

ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "evals/conversational_kb"

CHAINS = [
    (
        "H10",
        ["how's my arm extension?", "is it good?", "what should I change?", "and my recovery?"],
    ),
    (
        "H08",
        [
            "how was my rear leg?",
            "is it better straighter or bent?",
            "the second rep",
            "why does that matter?",
        ],
    ),
    ("H09", ["how was my torso?", "is it good?", "what should I change?", "and my rear leg?"]),
    ("H10", ["how did I do?", "what should I focus on first?", "why does that matter?", "thanks"]),
    (
        "H01",
        [
            "what about my knees and legs?",
            "what should I work on?",
            "and my torso?",
            "is the speed alright?",
        ],
    ),
    (
        "E12",
        [
            "how was my blade control?",
            "did the point drop on landing?",
            "what can you actually tell from my arm?",
            "what should I try?",
        ],
    ),
    (
        "E12",
        [
            "what was my lunge speed in metres per second?",
            "can you estimate it?",
            "what can you compare instead?",
            "the second rep",
        ],
    ),
    (
        "E12",
        [
            "how much force did I push with?",
            "does a straighter back leg prove more force?",
            "what does the measurement tell you?",
            "give me one cue",
        ],
    ),
    (
        "E12",
        [
            "teach me the Dragonfly triple-hop drill",
            "is that in your knowledge base?",
            "give me a drill that is",
            "why that one?",
        ],
    ),
    (
        "H04",
        [
            "how should I do a fleche?",
            "how should my legs move?",
            "and for a lunge instead?",
            "back to the fleche",
        ],
    ),
    (
        "H07",
        ["my arm in the second rep", "and my recovery?", "back to my arm", "what should I change?"],
    ),
    (
        "H09",
        ["my torso or my arm?", "the second option", "at starting guard?", "back to the finish"],
    ),
    ("H08", ["is it good?", "my rear leg", "what should I change?", "why does that matter?"]),
    ("E11", ["hello", "how did I do?", "thanks", "and my recovery?"]),
    (
        "H10",
        [
            "my front knee in rep 2",
            "does it go past my toe?",
            "does that mean it caves inward?",
            "what can you say from this view?",
        ],
    ),
    (
        "H09",
        [
            "how straight was my back?",
            "does the tilt say I leaned forward?",
            "what would you change?",
            "why?",
        ],
    ),
    (
        "S11",
        [
            "how is my recovery?",
            "does that time include holding the lunge?",
            "is it good?",
            "what should I practice?",
        ],
    ),
    ("H10", ["my arm in rep 99", "then the second rep", "is it good?", "how about the last rep?"]),
    ("H07", ["my arm at the finish", "start over", "what should I improve?", "my front leg"]),
    (
        "H10",
        [
            "how was the lunge?",
            "did my rear foot roll?",
            "did I keep the point steady?",
            "what is one thing I can work on from the measurements?",
        ],
    ),
]


def render():

    lines = [
        "# Twenty Gemini conversations on saved sessions",
        "",
        "Plain model replies, unchanged. No output checks, sentence removal or numeric gate. Each numbered turn includes its provider and response time; raw packets and traces are saved alongside the conversation JSON files.",
    ]

    saved = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in OUT.glob("C*.json")}

    complete = sum(
        len(r["turns"]) == 4 and all(t.get("answer") for t in r["turns"]) for r in saved.values()
    )

    count = sum(bool(t.get("answer")) for r in saved.values() for t in r["turns"])

    lines += [
        "",
        f"Status: {complete}/20 conversations complete; {count}/80 successful Gemini replies. Remaining turns are explicitly marked unrun. Gemini 3.5 Flash Lite hit its daily quota; the configured Gemini 3.8 Flash completed additional turns but then timed out. Model changes are labeled; no Groq substitution.",
    ]

    for i, (source, questions) in enumerate(CHAINS, 1):
        ident = f"C{i:02d}"

        row = saved.get(ident, {"turns": []})

        lines += ["", f"## {ident} — saved case {source}", ""]

        if row.get("failed_attempts"):
            lines += [
                "A prior provider failure is preserved in the JSON; successful turns were reused when continuing this chain."
            ]

        for n, question in enumerate(questions, 1):
            t = next((t for t in row["turns"] if t["turn"] == n), None)

            label = (
                f"{t['provider']} ({t.get('model_id', t.get('run', {}).get('model_id', 'unknown'))}), {t['latency_ms'] / 1000:.2f}s"
                if t and t.get("answer")
                else "not answered"
            )

            lines += [
                "",
                f"### Turn {n} — {label}",
                "",
                "You: " + question,
                "",
                "Coach: "
                + (
                    t["answer"]
                    if t and t.get("answer")
                    else "[Provider error retained; remaining pass paused.]"
                    if t
                    else "[Not run; no reply fabricated.]"
                ),
            ]

    (ROOT / "docs/conversational_coach_transcripts.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def redact(text):

    from dotenv import dotenv_values

    for key, value in dotenv_values(ROOT / ".env").items():
        if key.endswith("API_KEY") and value:
            text = text.replace(value, "[REDACTED]")

    return text[:1000]


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=None)

    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    (ROOT / "docs/conversational_coach_writer_prompt.txt").write_text(
        writer_reference(), encoding="utf-8"
    )

    base = {
        r["id"]: r
        for r in json.loads((ROOT / "evals/layer2/inputs.json").read_text(encoding="utf-8"))
    }

    if args.timeout:
        from fencecoach.settings import settings

        settings.gemini_request_timeout_seconds = args.timeout
    model = PacedGemini(chat_model("gemini", model_id=args.model))

    for i, (source, questions) in enumerate(CHAINS, 1):
        ident = f"C{i:02d}"

        path = OUT / (ident + ".json")

        if path.exists() and not args.resume:
            raise SystemExit(
                "Preserve existing transcripts; use --resume to continue saved history."
            )

        state = None

        history = []

        case = base[source]

        row = dict(
            id=ident, source_case=source, session_id=case["saved_request"]["session_id"], turns=[]
        )

        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))

            while row["turns"] and not row["turns"][-1].get("answer"):
                row.setdefault("failed_attempts", []).append(row["turns"].pop())

            for saved in row["turns"]:
                history += [
                    ConversationMessage(role="user", content=saved["question"]),
                    ConversationMessage(role="assistant", content=saved["answer"]),
                ]

            if row["turns"]:
                from fencecoach.schemas import DialogueState

                state = DialogueState.model_validate(row["turns"][-1]["run"]["dialogue_state"])

        for n, question in enumerate(questions, 1):
            if n <= len(row["turns"]):
                continue

            req = CoachRequest.model_validate(case["saved_request"])

            req.question = question

            req.conversation_history = history[-10:]

            req.dialogue_state = state

            before = model.state["wait_ms"]

            try:
                run = run_packet_core(req, "gemini", model=model)

            except Exception as exc:
                row["turns"].append(
                    dict(
                        turn=n,
                        question=question,
                        provider="gemini",
                        latency_ms=0,
                        answer=None,
                        error_type=type(exc).__name__,
                        error_detail=redact(str(exc)),
                    )
                )

                write(path, row)

                render()

                raise SystemExit("Stopped after provider error; no retry loop.") from None

            row["turns"].append(
                dict(
                    turn=n,
                    question=question,
                    provider=run.mode,
                    model_id=args.model or run.model_id,
                    latency_ms=max(0, run.latency_ms - (model.state["wait_ms"] - before)),
                    answer=run.report.summary,
                    run=run.model_dump(mode="json"),
                )
            )

            write(path, row)

            render()

            history += [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=run.report.summary),
            ]

            state = run.dialogue_state

            print(ident, n, "saved", flush=True)


if __name__ == "__main__":
    main()

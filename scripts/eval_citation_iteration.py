"""Frozen-input, paced conversations. No hidden individual-turn retries."""

import argparse
import json
import time
from pathlib import Path

from eval_layer2 import PacedGemini, execute, write

from fencecoach.coach.degraded_coach import DegradedCoach
from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.providers import chat_model
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=ROOT / "evals/layer2/inputs.json")
    parser.add_argument("--provider", choices=["gemini", "groq", "local"], required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()
    directory = ROOT / "evals/citation_iteration" / args.run
    model = (
        PacedGemini(chat_model("gemini"))
        if args.provider == "gemini"
        else HostedFallback()
        if args.provider == "groq"
        else DegradedCoach()
    )
    for case in json.loads(args.inputs.read_text(encoding="utf-8")):
        if args.ids and case["id"] not in args.ids:
            continue
        path = directory / f"{case['id']}-{args.provider}.json"
        if path.exists():
            raise SystemExit(f"Output already exists: {path}; preserve it and choose a new run.")
        history = [ConversationMessage.model_validate(m) for m in case["seed_history"]]
        state = None
        row = {k: case[k] for k in ("id", "name", "origin")}
        row.update(provider=args.provider, turns=[])
        for index, turn in enumerate(case["turns"], 1):
            request = CoachRequest.model_validate(case["saved_request"])
            request.question, request.conversation_history, request.dialogue_state = (
                turn["question"],
                history[-10:],
                state,
            )
            before = request.model_dump(mode="json")
            result = execute(request, args.provider, model)
            result.update(
                turn=index, question=request.question, provider=args.provider, request=before
            )
            row["turns"].append(result)
            write(path, row)
            print(
                case["id"],
                index,
                result.get("error_type") or "ok",
                result.get("claim_checks", {}).get("removed"),
                flush=True,
            )
            if result.get("error_type"):
                raise SystemExit(
                    "Stopped after a provider failure; no retry loop. Partial chain retained."
                )
            history += [
                ConversationMessage(role="user", content=request.question),
                ConversationMessage(role="assistant", content=result["answer"]),
            ]
            state = DialogueState.model_validate(result["state_after"])
            # Groq free plan is token-limited. This is scheduling, not inference
            # latency. A complete separate provider pass avoids overlapping load.
            if args.provider == "groq":
                time.sleep(40)


if __name__ == "__main__":
    main()

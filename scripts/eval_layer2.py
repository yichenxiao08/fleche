"""Pinned-provider replay with explicit state, packets, retries and numeric traces."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from eval_layer1 import scenarios

from fencecoach.coach.core_packet import run_packet_core
from fencecoach.coach.number_trace import trace_numbers
from fencecoach.coach.packet_runtime import PacketQwen, warm_packet_qwen
from fencecoach.coach.providers import chat_model, configured_model_id
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/layer2"


class PacedGemini:
    """Evaluation scheduling only: respect the observed free-tier request quota."""

    shared_state = {"last": 0.0, "wait_ms": 0.0}

    def __init__(self, model, state=None):
        self.model = model
        self.state = state if state is not None else self.shared_state

    def bind_tools(self, tools):
        return PacedGemini(self.model.bind_tools(tools), self.state)

    def invoke(self, messages):
        delay = max(0.0, 6.0 - (time.monotonic() - self.state["last"]))
        if delay:
            time.sleep(delay)
            self.state["wait_ms"] += delay * 1000
        self.state["last"] = time.monotonic()
        return self.model.invoke(messages)


def write(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows readers briefly hold a deny-delete handle. Retry only the local
    # rename, never the already-completed provider invocation.
    for attempt in range(4):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.05 * (attempt + 1))


def cases():
    path = OUT / "inputs.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    frozen = scenarios()
    write(path, frozen)
    return frozen


def execute(request, provider, model):
    started = time.perf_counter()
    pacing_before = model.state["wait_ms"] if isinstance(model, PacedGemini) else 0
    try:
        run = run_packet_core(request, provider, model=model)
        return {
            "answer": run.report.summary,
            "latency_ms": run.latency_ms,
            "first_token_ms": run.first_token_ms,
            "packet": run.answer_contract["packet"],
            "number_trace": trace_numbers(run.report.summary, run.answer_contract["packet"]),
            "state_after": run.dialogue_state.model_dump(mode="json"),
            "trace": [t.model_dump(mode="json") for t in run.trace],
            "provider_attempts": run.answer_contract["provider_attempts"],
            "tool_calls": run.answer_contract["tool_calls"],
            "claim_checks": run.answer_contract.get("claim_checks"),
            "first_visible_ms": run.first_visible_ms,
            "tokens": {"input": run.input_tokens, "output": run.output_tokens},
            "evaluation_pacing_ms": model.state["wait_ms"] - pacing_before
            if isinstance(model, PacedGemini)
            else 0,
        }
    except Exception as exc:
        trace = [t.model_dump(mode="json") for t in getattr(exc, "layer1_trace", [])]
        attempts = next(
            (
                json.loads(t["detail"])["attempts"]
                for t in reversed(trace)
                if t["step"] == "provider_error"
            ),
            [],
        )
        return {
            "answer": None,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1200],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "packet": getattr(exc, "coach_packet", {}),
            "state_after": getattr(exc, "coach_state", None),
            "trace": trace,
            "provider_attempts": attempts,
        }


def evaluate(case, provider, directory, resume, pace_gemini=False):
    path = directory / f"{case['id']}-{provider}.json"
    if resume and path.exists():
        row = json.loads(path.read_text(encoding="utf-8"))
    else:
        row = {k: case[k] for k in ("id", "name", "origin")}
        row.update(
            provider=provider,
            model_id=configured_model_id(provider),
            started_at=datetime.now(UTC).isoformat(),
            turns=[],
        )
    history = [ConversationMessage.model_validate(m) for m in case["seed_history"]]
    state = None
    for saved in row["turns"]:
        history.append(ConversationMessage(role="user", content=saved["question"]))
        if saved.get("answer"):
            history.append(ConversationMessage(role="assistant", content=saved["answer"]))
        state = (
            DialogueState.model_validate(saved["state_after"])
            if saved.get("state_after")
            else state
        )
    model = PacketQwen() if provider == "local" else chat_model(provider)
    if provider == "gemini" and pace_gemini:
        model = PacedGemini(model)
    for index, turn in enumerate(case["turns"][len(row["turns"]) :], len(row["turns"]) + 1):
        request = CoachRequest.model_validate(case["saved_request"])
        request.question = turn["question"]
        request.conversation_history = history[-10:]
        request.dialogue_state = state
        before = request.model_dump(mode="json")
        result = execute(request, provider, model)
        result.update(turn=index, question=turn["question"], provider=provider, request=before)
        row["turns"].append(result)
        state = (
            DialogueState.model_validate(result["state_after"])
            if result.get("state_after")
            else state
        )
        history.append(ConversationMessage(role="user", content=request.question))
        if result.get("answer"):
            history.append(ConversationMessage(role="assistant", content=result["answer"]))
        write(path, row)
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "provider": provider,
                    "turn": index,
                    "latency_ms": result["latency_ms"],
                    "answer": result.get("answer"),
                    "error": result.get("error_type"),
                    "unsupported_numbers": len(
                        result.get("number_trace", {}).get("unsupported", [])
                    ),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        if result.get("error_type") and (
            "RateLimit" in result["error_type"] or "quota" in result.get("error", "").lower()
        ):
            raise SystemExit("Stopped on quota failure; saved chain is incomplete. No retry loop.")


def rerun_errors(directory, provider):
    model = PacketQwen() if provider == "local" else PacedGemini(chat_model(provider))
    recovered = []
    for path in sorted(directory.glob(f"*-{provider}.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        for turn in row["turns"]:
            if turn.get("error"):
                request = CoachRequest.model_validate(turn["request"])
                result = execute(request, provider, model)
                recovered.append(
                    {
                        "case": row["id"],
                        "turn": turn["turn"],
                        "question": turn["question"],
                        **result,
                    }
                )
                write(directory / "error_replays" / f"{provider}.json", recovered)
                print(
                    json.dumps(
                        {
                            "error_replay": row["id"],
                            "turn": turn["turn"],
                            "provider": provider,
                            "error": result.get("error_type"),
                        }
                    ),
                    flush=True,
                )
    if not recovered:
        write(directory / "error_replays" / f"{provider}.json", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", nargs="+", default=["gemini", "local"])
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--run", default="final")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun-errors", action="store_true")
    parser.add_argument("--pace-gemini", action="store_true")
    parser.add_argument("--inputs", type=Path)
    args = parser.parse_args()
    directory = OUT / args.run
    for provider in args.providers:
        if (
            provider == "local"
            and not args.rerun_errors
            and not (directory / "qwen_warm.json").exists()
        ):
            write(directory / "qwen_warm.json", warm_packet_qwen())
        if args.rerun_errors:
            rerun_errors(directory, provider)
        else:
            selected_cases = (
                json.loads(args.inputs.read_text(encoding="utf-8")) if args.inputs else cases()
            )
            for case in selected_cases:
                if not args.ids or case["id"] in args.ids:
                    evaluate(case, provider, directory, args.resume, args.pace_gemini)


if __name__ == "__main__":
    main()

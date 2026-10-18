"""Record actual Ollama runtime metadata and old slow-turn payload sizes."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fencecoach.coach.packet_runtime import LOCAL_CONTEXT, LOCAL_DEADLINE_SECONDS, LOCAL_GENERATION
from fencecoach.settings import settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/layer2/runtime_diagnosis.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", action="store_true")
    args = parser.parse_args()
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    with httpx.Client(timeout=5) as client:
        ps = client.get(settings.ollama_base_url + "/api/ps").json()
        show = client.post(
            settings.ollama_base_url + "/api/show", json={"model": settings.ollama_chat_model}
        ).json()
    data["after" if args.after else "before"] = {
        "at": datetime.now(UTC).isoformat(),
        "loaded_models": ps,
        "model_details": show.get("details"),
        "capabilities": show.get("capabilities"),
        "thinking": "not advertised in capabilities; old reasoning=False, new think=False",
    }
    data["old_settings"] = {
        "num_ctx": 16384,
        "num_predict": 240,
        "read_timeout_s": 180,
        "startup_warm_context": 4096,
        "keep_alive": -1,
    }
    data["new_settings"] = {
        "num_ctx": LOCAL_CONTEXT,
        "num_predict": LOCAL_GENERATION,
        "hard_deadline_s": LOCAL_DEADLINE_SECONDS,
        "keep_alive": -1,
        "tools": "none on Qwen",
        "output": "plain text, no JSON or function calling",
    }
    slow = []
    for path in (ROOT / "evals/layer1/variants/V3").glob("*-local.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        for turn in row["turns"]:
            if turn["latency_ms"] < 90000:
                continue
            events = [
                json.loads(t["detail"])
                for t in turn["trace"]
                if t["step"] in {"layer1_input", "tools"}
            ]
            slow.append(
                {
                    "case": row["id"],
                    "turn": turn["turn"],
                    "latency_ms": turn["latency_ms"],
                    "error": turn.get("error_type"),
                    "serialized_input_and_tool_chars": sum(len(json.dumps(e)) for e in events),
                    "tool_result_chars": sum(len(e.get("result", "")) for e in events),
                }
            )
    data["old_slow_turns"] = slow
    data["limits_of_diagnosis"] = (
        "Old runs did not save Ollama prefill/load/generation timings. Large context/tool payloads and 180s per-read timeout are observed; component-level causality cannot be proven retrospectively. New runs save these timings and enforce a total deadline. Quantization weights are unchanged."
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()

"""Use journal-recovered Layer 2 code; validate context before any provider call."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evals/next_phase/baseline_source"


def load(name):
    module_name = "fencecoach.coach." + name
    spec = importlib.util.spec_from_file_location(module_name, SOURCE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    from fencecoach.coach.core_new import _session_key, _snapshot
    from fencecoach.schemas import CoachRequest

    packet_module = load("turn_packet")
    core_module = load("core_packet")
    checked, mismatches = 0, []
    for path in (ROOT / "evals/layer2/gemini_new_project").glob("*-gemini.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        for turn in row["turns"]:
            request = CoachRequest.model_validate(turn["request"])
            snapshot = json.loads(_snapshot(_session_key(request)))
            state = packet_module.resolve_scope(request, snapshot)
            packet = packet_module.build_packet(request, state, snapshot)
            original = next(
                json.loads(t["detail"]) for t in turn["trace"] if t["step"] == "packet_input"
            )
            if packet != original["packet"] or original["persona"] != core_module.PERSONA:
                mismatches.append([row["id"], turn["turn"]])
            checked += 1
    validation = {
        "original_turns": checked,
        "packet_or_persona_mismatches": mismatches,
        "source": "original task patch journal before 22:13 UTC; no historical shell commands executed",
    }
    (SOURCE / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    assert checked == 56 and not mismatches, validation
    print(
        "Recovered baseline validated: 56/56 original pre-call packets and persona identical.",
        flush=True,
    )
    if "--validate-only" in sys.argv:
        return
    import eval_layer2

    eval_layer2.run_packet_core = core_module.run_packet_core
    eval_layer2.main()


if __name__ == "__main__":
    main()

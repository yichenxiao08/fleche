"""Offline saved-draft audit. Legacy text has no writer-authored citations.

For legacy drafts the citation comparison is explicitly counterfactual: attach
all available evidence IDs, and classify question sentences as clarifications.
This isolates removal-policy effects; it cannot measure real citation selection
or establish the truth of uncited historical prose. Keep every removal trace.
"""

import importlib.util
import json
from pathlib import Path

from fencecoach.coach.claim_check import check_sentence, citation_index, sentences

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/citation_iteration"
spec = importlib.util.spec_from_file_location(
    "previous_lexical", OUT / "before_source/claim_check.py"
)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def main():
    records, seen = [], set()
    for directory in ("layer2", "next_phase", "citation_iteration"):
        for path in sorted((ROOT / "evals" / directory).rglob("*.json")):
            if path.name in {"inputs.json", "holdout_inputs.json", "grounding_replay.json"}:
                continue
            if "gemini" not in str(path) and not path.parent.name.startswith("live"):
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if not isinstance(row, dict) or not isinstance(row.get("turns"), list):
                continue
            for turn in row.get("turns", []):
                run = turn.get("run") or turn
                if run.get("mode", row.get("provider", "gemini")) != "gemini":
                    continue
                packet = run.get("packet") or run.get("answer_contract", {}).get("packet")
                if not packet:
                    continue
                drafts = []
                for event in run.get("trace", []):
                    if event["step"] == "packet_model":
                        value = json.loads(event["detail"])
                        if value.get("text") and not value.get("tool_calls"):
                            drafts.append(value["text"])
                for raw in drafts:
                    key = json.dumps([raw, packet], sort_keys=True)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        payload = json.loads(
                            raw.strip().removeprefix("```json").removesuffix("```")
                        )
                        statements = payload["sentences"]
                        mode = "actual_writer_citations"
                    except (ValueError, KeyError, TypeError):
                        mode = "legacy_counterfactual_all_available_ids"
                        statements = [
                            {
                                "type": "clarification" if text.endswith("?") else "claim",
                                "text": text,
                                "evidence_ids": list(citation_index(packet)),
                            }
                            for text in sentences(raw)
                        ]
                    checks = []
                    for statement in statements:
                        previous = old.check_sentence(statement["text"], packet)
                        current = check_sentence(statement, packet)
                        checks.append(
                            {
                                "text": statement["text"],
                                "type": statement["type"],
                                "old": previous,
                                "new": current,
                            }
                        )
                    records.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "turn": turn["turn"],
                            "mode": mode,
                            "sentences": checks,
                        }
                    )
    summary = {
        "unique_drafts": len(records),
        "scope": "All saved packet-era Gemini drafts with packet_model trace in layer2, next_phase and citation_iteration; duplicate copies deduplicated by draft+packet.",
        "legacy_limitation": __doc__,
        "groups": {},
    }
    for mode in {r["mode"] for r in records}:
        rows = [s for r in records if r["mode"] == mode for s in r["sentences"]]
        # Questions are the auditable valid non-claim category. We do not label
        # a historical factual assertion valid just because its numbers match.
        questions = [r for r in rows if r["type"] == "clarification"]
        summary["groups"][mode] = {
            "drafts": sum(r["mode"] == mode for r in records),
            "sentences": len(rows),
            "old_removed": sum(not r["old"]["passed"] for r in rows),
            "new_removed": sum(not r["new"]["passed"] for r in rows),
            "valid_questions_removed_old": sum(not r["old"]["passed"] for r in questions),
            "valid_questions_removed_new": sum(not r["new"]["passed"] for r in questions),
        }
    (OUT / "grounding_replay.json").write_text(
        json.dumps(dict(summary=summary, records=records), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

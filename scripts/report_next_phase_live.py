"""Offline live transcripts and honest provider/state/latency accounting."""

import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evals/next_phase/live"


def main():
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DIRECTORY.glob("L*.json"))]
    assert len(rows) == 10
    turns = [t for row in rows for t in row["turns"]]
    assert len(turns) == 37 and all(t.get("run") for t in turns)
    final = next(r for r in rows if r["id"] == "L10")["turns"]
    assert final[2]["run"]["mode"] == "local"
    assert final[2]["run"]["dialogue_state"]["topics"] == ["arm"]
    assert final[2]["run"]["dialogue_state"]["rep_numbers"] == [2]
    assert final[3]["run"]["dialogue_state"]["topics"] == ["recovery"]
    assert final[-1]["run"]["mode"] == "gemini"
    summary = {
        "conversations": 10,
        "turns": 37,
        "providers": dict(Counter(t["run"]["mode"] for t in turns)),
        "forced_chain": [
            {
                "turn": t["turn"],
                "provider": t["run"]["mode"],
                "reason": t["run"].get("fallback_reason"),
                "topic": t["run"]["dialogue_state"]["topics"],
                "reps": t["run"]["dialogue_state"]["rep_numbers"],
            }
            for t in final
        ],
    }
    for provider in summary["providers"]:
        selected = [t for t in turns if t["run"]["mode"] == provider]
        timings = sorted(t["http_latency_ms"] / 1000 for t in selected)
        visible = [
            t["first_visible_ms"] / 1000 for t in selected if t.get("first_visible_ms") is not None
        ]
        first = [
            t["run"]["first_token_ms"] / 1000
            for t in selected
            if t["run"].get("first_token_ms") is not None
        ]
        summary[provider] = {
            "http_median_s": round(statistics.median(timings), 2),
            "http_p95_s": round(timings[math.ceil(len(timings) * 0.95) - 1], 2),
            "first_visible_median_s": round(statistics.median(visible), 2) if visible else None,
            "provider_ttft_median_s": round(statistics.median(first), 2) if first else None,
        }
    (DIRECTORY / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Next-phase live-app acceptance transcripts",
        "",
        "Ten scripted conversations through the running FastAPI app's real coaching queue and report endpoints, on fresh clones of real saved sessions. Actual providers answered every turn. Separate SQLite/video-result copies isolated the acceptance app; the user's main app and default remained old.",
        "",
        "The L10 fault injection raises one synthetic 429 before a real local invocation; it makes no Gemini call for that failure. State and packet pass through the normal router/repository path. This proves state transfer, not acceptable fallback coaching quality.",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "HTTP latency includes request construction, queue/worker overhead and generation. First-visible timing is polled at 250 ms. It is not provider TTFT; Gemini's synchronous provider path supplies no TTFT. Local transport TTFT and first verified visible sentence are separate.",
        "",
        "An earlier launcher-isolation failure is preserved in evals/next_phase/live_pre_isolation_failure/. Package import constructed the original repository before process-local settings were applied; the existing worker claimed that test job. No accepted new-core answer was produced. Only the ten launcher-created session rows and that one failed job were removed from the original database after verifying IDs/title/no associated runs. The corrected launcher sets environment before package import and asserts its repository path. Legacy worker request consumption for that invalid attempt was not instrumented; it is not reported as zero.",
    ]
    for row in rows:
        lines += [
            "",
            f"## {row['id']} — saved-session source {row['source_case']}",
            "",
            f"Source session: {row['source_session']}; isolated session: {row['session_id']}. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/{row['id']}.json.",
        ]
        for turn in row["turns"]:
            run = turn["run"]
            lines += [
                "",
                f"### T{turn['turn']} — {run['mode']}; {turn['http_latency_ms'] / 1000:.2f}s HTTP; reason: {run.get('fallback_reason') or 'primary available'}",
                "",
                "User: " + turn["question"],
                "",
                run["report"]["summary"],
            ]
    (ROOT / "docs/next_phase_live_transcripts.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

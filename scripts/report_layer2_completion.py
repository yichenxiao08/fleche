"""Report the preserved complete Gemini pass without additional provider calls."""

import json
from datetime import UTC, datetime

from report_layer2 import EXPECTED, IDS, ROOT, load, stat

from fencecoach.coach.number_trace import trace_numbers

DIRECTORY = ROOT / "evals/layer2/gemini_new_project"


def main():
    cases = json.loads((DIRECTORY.parent / "inputs.json").read_text(encoding="utf-8"))
    current = load(DIRECTORY, "gemini")
    for case in cases:
        actual = current.get(case["id"], {}).get("turns", [])
        assert [t["question"] for t in actual] == [t["question"] for t in case["turns"]], (
            f"Incomplete or changed inputs: {case['id']}"
        )
    turns = [t for ident in IDS for t in current[ident]["turns"]]
    assert all(t.get("answer") for t in turns), "Report requires complete answered chains."
    checks = []
    for ident, expected_turns in EXPECTED.items():
        indexed = {t["turn"]: t for t in current[ident]["turns"]}
        for turn, expectation in expected_turns.items():
            scope = indexed[turn]["packet"]["scope"]
            checks.append(
                {
                    "reference": f"{ident}-gemini-T{turn}",
                    "expected": expectation,
                    "actual": scope,
                    "passed": all(scope.get(k) == v for k, v in expectation.items()),
                }
            )
    numbers = [
        {
            "reference": f"{ident}-gemini-T{t['turn']}",
            **trace_numbers(t["answer"], t["packet"]),
        }
        for ident in IDS
        for t in current[ident]["turns"]
    ]
    stats = {
        "generated_at": datetime.now(UTC).isoformat(),
        "complete_gemini": stat(current),
        "gemini_v3": stat(load(ROOT / "evals/layer1/variants/V3", "gemini"), True),
        "gemini_initial_layer2": stat(load(DIRECTORY.parent / "final", "gemini")),
        "local_preserved_layer2": stat(load(DIRECTORY.parent / "final", "local")),
        "scope_checks": {"passed": sum(c["passed"] for c in checks), "total": len(checks)},
        "provider_requests": sum(len(t["provider_attempts"]) for t in turns),
        "tool_calls": sum(t["tool_calls"] for t in turns),
        "tokens": {
            kind: sum(t.get("tokens", {}).get(kind, 0) for t in turns)
            for kind in ("input", "output")
        },
    }
    for filename, data in (
        ("summary.json", stats),
        ("number_tracing.json", numbers),
        ("scope_checks.json", checks),
    ):
        (DIRECTORY / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")

    rows = []
    for label, key in (
        ("Gemini V3", "gemini_v3"),
        ("Gemini initial Layer 2", "gemini_initial_layer2"),
        ("Gemini complete paced Layer 2", "complete_gemini"),
        ("Qwen Layer 2 (preserved)", "local_preserved_layer2"),
    ):
        s = stats[key]
        rows.append(
            f"| {label} | {s['answers']}/{s['turns']} | {s['provider_errors']} | "
            f"{s['reply_median_s']:.2f}s / {s['reply_p95_s']:.2f}s | "
            f"{s['replies_with_unmatched_numbers']}/{s['answers']} | "
            f"{s['unmatched_numeric_mentions']}/{s['numeric_mentions']} | {s['tool_turns']} |"
        )
    report = [
        "# Layer 2 Gemini completion — 2026-10-14",
        "",
        "Completed the earlier Layer 2 validation only. No next-phase packet assessments, response ladder, Layer 5 or new fallback model were built. COACH_CORE remains old. No commit or push.",
        "",
        "All 13 frozen sequences / 56 original user turns completed with the newly supplied project key. Each chain carries its actual preceding answers, unlike the earlier isolated error replays. H01 was completed as the initial probe; the same resumable run supplied the other chains. The process survived the earlier cancellation; it was discovered still running, so no duplicate evaluation process was launched. Every saved turn was reused. Earlier runs remain intact.",
        "",
        "| Run | Replies | Provider errors | Median / p95 excluding eval pacing | Replies with unmatched numbers | Unmatched / mentions | Tool turns |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        f"Annotated scope expectations: {stats['scope_checks']['passed']}/{stats['scope_checks']['total']} on the actual Gemini packets. This is annotated scope coverage, not full semantic answer accuracy. All 56 input questions match the frozen set exactly.",
        "",
        f"Request accounting: {stats['provider_requests']} actual Gemini model attempts for 56 answers; {stats['tool_calls']} optional evidence-tool calls. Token usage: {stats['tokens']['input']} input / {stats['tokens']['output']} output. No completed turns were deliberately replayed and no additional probe was made. Requests were spaced at least six seconds apart by the existing evaluation scheduler. Billing was not independently inspected; this run uses the user's stated free-project key, and no billing setup was performed.",
        "",
        "Latency subtracts recorded evaluation-only pacing, retaining inference, packet work and any provider retry/backoff. The raw paced latency and pacing time remain in each transcript and JSON. Gemini does not expose streaming TTFT in this path; it is unavailable, not zero. The Qwen row reuses the previous complete run; it was not rerun because no Qwen code changed during this check.",
        "",
        "## Manual review of remaining failures",
        "",
        "| Turns | Finding | Implication |",
        "|---|---|---|",
        "| H01 T1–T3 | Stays on knees/legs, back, and speed; labels general guidance and acknowledges unavailable tracking without inventing athlete measurements. | Narrow H01 acceptance holds; some advice still exceeds the retrieved wording. |",
        "| H03 T1 | Opens with a definition of recovery although the question asks about arm angles. | Scope/history or retrieval contamination still reaches the reply. |",
        "| H04 T1–T3 | Starts the fleche answer with lunge guidance; later supplies crossing and run-through instructions beyond the retrieved material. | Numeric matching does not establish support for technique advice. |",
        "| H07 T4–T5 | Correct torso packet survives 'during the drill'; descriptions still blur torso tilt and pitch-change meanings. | The resolver fix works, but measurement semantics remain weak. |",
        "| H08 T2–T3; H09 T2–T6 | Keeps the requested subject but repeatedly declines to assess good/bad or straighter/bent. | Continuity alone does not produce useful coaching judgments. |",
        "| H10 T2–T4 | 'Good or bad' becomes varied measurements plus general instruction; later repeats unsupported 18.1 degrees (packet: 18.153, normally 18.2 to one decimal). Priority claims are not established by the packet. | Two numeric-tracing failures plus unsupported semantic advice. |",
        "| E11/S11 T5–T7 | Correctly presents 0.1 seconds as active recovery time, not an onset timestamp; keeps rep 2. Repeats the same values and similar general advice across follow-ups. | Earlier onset confusion was not reproduced in this pass; conversation remains repetitive. |",
        "| E12 T1–T5 | Does not claim measured blade stability, calibrated speed, force or the absent named drill. T5 only says the drill is absent, without a useful alternative. | Manual bait review: 0/5 invent the requested measurement or drill. This does not certify all general causal advice. |",
        "",
        "Number tracing checks presence and ordinary rounding only. It does not prove the correct metric, phase, rep, unit, causality, drill identity or a justified verdict. This availability-complete pass is not an overall coaching-quality acceptance or live-app acceptance. The separately supplied next-phase task remains unstarted.",
        "",
        "Full answers and per-turn latency: [layer2_gemini_completion_transcripts.md](layer2_gemini_completion_transcripts.md). Raw packets, inputs, provider attempts and traces: evals/layer2/gemini_new_project/.",
    ]
    (ROOT / "docs/layer2_gemini_completion.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    transcript = [
        "# Complete paced Gemini Layer 2 transcripts",
        "",
        "Same frozen saved-session inputs; no simulated provider answers. Raw latency includes deliberate evaluation pacing; adjusted latency subtracts only that pacing. No new live-app conversations were run.",
    ]
    for ident in IDS:
        row = current[ident]
        transcript += [
            "",
            f"## {ident} — {row['name']}",
            "",
            f"Provider: gemini; model: {row['model_id']}; source: evals/layer2/gemini_new_project/{ident}-gemini.json.",
        ]
        for turn in row["turns"]:
            raw = turn["latency_ms"] / 1000
            pacing = turn.get("evaluation_pacing_ms", 0) / 1000
            trace = trace_numbers(turn["answer"], turn["packet"])
            transcript += [
                "",
                f"### T{turn['turn']} — Gemini; {raw - pacing:.2f}s excluding pacing ({raw:.2f}s raw; {pacing:.2f}s pacing)",
                "",
                f"User: {turn['question']}",
                "",
                turn["answer"],
                "",
                f"Numeric tracing: {len(trace['unsupported'])} unmatched / {len(trace['mentions'])} mentions. Tool calls: {turn['tool_calls']}. Provider attempts: {len(turn['provider_attempts'])}.",
            ]
            if trace["unsupported"]:
                transcript += [
                    "",
                    "Unmatched: " + json.dumps(trace["unsupported"], ensure_ascii=False),
                ]
    (ROOT / "docs/layer2_gemini_completion_transcripts.md").write_text(
        "\n".join(transcript) + "\n", encoding="utf-8"
    )
    main_path = ROOT / "docs/coach_eval_results.md"
    main = main_path.read_text(encoding="utf-8")
    update = "> Latest check: the complete paced Gemini pass now has 56/56 replies with zero provider errors. The historical quota-blocked results below are preserved. See [the updated report](layer2_gemini_completion.md) and [full transcripts](layer2_gemini_completion_transcripts.md)."
    if update not in main:
        heading, remainder = main.split("\n", 1)
        main = heading + "\n\n" + update + "\n" + remainder
    marker = "<!-- complete-gemini-pass -->"
    if marker in main:
        main = main.split(marker)[0].rstrip() + "\n"
    main += "\n" + marker + "\n\n## Complete Gemini pass — 2026-10-14\n\n"
    main += "The quota blocker for the earlier Layer 2 check is resolved by the supplied project key. All 13 original chains / 56 turns now have a coherent complete Gemini pass, preserved separately from the earlier primary run and isolated replays.\n\n"
    main += "[Updated comparison and remaining failures](layer2_gemini_completion.md) · [Complete new transcripts](layer2_gemini_completion_transcripts.md).\n\n"
    main += "\n".join([report[6], report[7], *rows]) + "\n"
    main_path.write_text(main, encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

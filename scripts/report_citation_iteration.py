"""Offline checkpoint accounting; incomplete runs remain visibly incomplete."""

import json
from collections import Counter
from pathlib import Path
from statistics import median

from fencecoach.coach.number_trace import trace_numbers
from fencecoach.coach.quality_metrics import repetition, response_kind

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/citation_iteration"


def main():
    expectations = json.loads((OUT / "holdout_expectations.json").read_text(encoding="utf-8"))
    summary = {}
    transcript = [
        "# Citation iteration: complete saved transcripts",
        "",
        "All saved turns, including failures. Raw drafts, citations, removed sentences and packets are in evals/citation_iteration. Incomplete passes are labeled.",
    ]
    for name in [
        "diagnostic_gemini",
        "diagnostic_groq_transport",
        "diagnostic_complete",
        "holdout_gemini",
        "holdout_groq",
        "holdout_local",
        "live_new",
        "live_old",
    ]:
        rows = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((OUT / name).glob("*.json"))
            if p.name != "provider_accounting.json"
        ]
        turns = []
        for row in rows:
            transcript += ["", f"## {name}: {row['id']}", ""]
            for raw in row.get("turns", []):
                run = raw.get("run") or {}
                t = (
                    raw
                    if "run" not in raw
                    else dict(
                        turn=raw["turn"],
                        question=raw["question"],
                        answer=run.get("report", {}).get("summary"),
                        packet=run.get("answer_contract", {}).get("packet", {}),
                        latency_ms=run.get("latency_ms", raw["http_latency_ms"]),
                        state_after=run.get("dialogue_state"),
                        provider=run.get("mode"),
                        claim_checks=run.get("answer_contract", {}).get("claim_checks"),
                        provider_attempts=run.get("answer_contract", {}).get(
                            "provider_attempts", []
                        ),
                    )
                )
                t = {**t, "reference": row["id"] + "-T" + str(t["turn"])}
                turns.append(t)
                latency = max(0, t["latency_ms"] - t.get("evaluation_pacing_ms", 0)) / 1000
                transcript += [
                    "",
                    f"### {t['reference']} — {t.get('provider', name)}; {latency:.2f}s",
                    "",
                    "User: " + t["question"],
                    "",
                    "Coach: " + (t.get("answer") or "[provider/job failure retained]"),
                ]
        answered = [t for t in turns if t.get("answer")]
        latencies = sorted(
            max(0, t["latency_ms"] - t.get("evaluation_pacing_ms", 0)) / 1000 for t in answered
        )
        numbers = [(t, trace_numbers(t["answer"], t.get("packet", {}))) for t in answered]
        breakdown = Counter(response_kind(t) for t in turns)
        rep = [repetition(r["turns"]) for r in rows if not name.startswith("live")]
        scope = []
        if name.startswith("holdout"):
            for t in turns:
                expected = expectations[t["reference"].split("-")[0]][t["turn"] - 1]["topic"]
                packet = t.get("packet", {})
                actual = packet.get("scope", {}).get("topics", [])
                passed = (
                    expected in actual
                    if expected
                    else bool(packet.get("clarification"))
                    or packet.get("turn_type") in {"greeting", "restart", "acknowledgment"}
                )
                scope.append(
                    dict(
                        reference=t["reference"],
                        expected_topic=expected,
                        actual=actual,
                        passed=passed,
                    )
                )
        summary[name] = dict(
            chains=len(rows),
            turns=len(turns),
            answers=len(answered),
            provider_errors=len(turns) - len(answered),
            provider_attempts=sum(len(t.get("provider_attempts", [])) for t in turns),
            median_s=median(latencies) if latencies else None,
            p95_s=latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
            if latencies
            else None,
            unmatched_number_turns=[t["reference"] for t, n in numbers if not n["passed"]],
            unmatched_numbers=sum(len(n["unsupported"]) for t, n in numbers),
            all_sentences_removed=[
                t["reference"] for t in turns if (t.get("claim_checks") or {}).get("all_removed")
            ],
            removed_sentences=sum((t.get("claim_checks") or {}).get("removed", 0) for t in turns),
            response_kind_proxy=dict(breakdown),
            scope_topic_checks=scope,
            scope_topic_passed=sum(s["passed"] for s in scope),
            repetition={
                k: sum(r[k] for r in rep)
                for k in ["consecutive_pairs", "repeated_value_pairs", "repeated_advice_pairs"]
            },
        )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ROOT / "docs/citation_iteration_transcripts.md").write_text(
        "\n".join(transcript) + "\n", encoding="utf-8"
    )
    lines = [
        "# Citation iteration results",
        "",
        "Provisional accounting until complete passes and manual review are recorded. Default remains old; no commit or push.",
        "",
        "| Pass | Replies | Scope topic* | Unmatched numbers | Nonpartial declines* | Bare / options questions* | Useful partials* | Repetition values / advice* | All removed | Median / p95 s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in summary.items():
        b = s["response_kind_proxy"]
        r = s["repetition"]
        lines.append(
            f"| {name} | {s['answers']}/{s['turns']} | {s['scope_topic_passed']}/{len(s['scope_topic_checks'])} | {s['unmatched_numbers']} | {b.get('decline_without_partial_proxy', 0)} | {b.get('bare_question', 0)} / {b.get('question_with_concrete_options', 0)} | {b.get('useful_partial_proxy', 0)} | {r['repeated_value_pairs']} / {r['repeated_advice_pairs']} | {len(s['all_sentences_removed'])} | {s['median_s']} / {s['p95_s']} |"
        )
    lines += [
        "",
        "*Automated proxies. Scope above checks the annotated primary topic or appropriate clarification/social route, not complete semantic continuity. Repetition includes requested comparisons. Live old-core packets use a different schema; their numeric and partial-answer proxy counts are not directly comparable. Manual verdict, bait and live continuity judgments must be read alongside these numbers.",
        "",
        "See citation_iteration_transcripts.md for every answer, and citation_iteration_review.md for limitations and manual findings.",
    ]
    (ROOT / "docs/citation_iteration_results.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: {
                    x: s[x]
                    for x in [
                        "chains",
                        "turns",
                        "answers",
                        "median_s",
                        "unmatched_numbers",
                        "removed_sentences",
                    ]
                }
                for k, s in summary.items()
            }
        )
    )


if __name__ == "__main__":
    main()

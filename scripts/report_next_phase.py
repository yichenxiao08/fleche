"""Offline comparison and complete visible transcripts; never calls a provider."""

import json
from collections import Counter

from report_layer2 import EXPECTED, ROOT, stat

from fencecoach.coach.core_packet import PERSONA
from fencecoach.coach.number_trace import trace_numbers
from fencecoach.coach.quality_metrics import repetition, response_kind, verdict_without_basis

OUT = ROOT / "evals/next_phase"


def read_rows(directory, provider):
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in directory.glob(f"*-{provider}.json")
    }


def summarize(rows, original=True):
    result = stat(rows)
    result["complete"] = len(rows) == (13 if original else 12) and result["turns"] == (
        56 if original else 48
    )
    turns = [t for row in rows.values() for t in row["turns"]]
    result["response_breakdown_proxy"] = dict(Counter(response_kind(t) for t in turns))
    result["verdict_without_basis_proxy"] = sum(verdict_without_basis(t) for t in turns)
    reps = {row["id"]: repetition(row["turns"]) for row in rows.values()}
    result["repetition"] = {
        key: sum(r[key] for r in reps.values())
        for key in ("consecutive_pairs", "repeated_value_pairs", "repeated_advice_pairs")
    }
    result["repetition_details"] = reps
    result["requests"] = sum(len(t.get("provider_attempts", [])) for t in turns)
    result["sentences_removed"] = sum(
        t.get("claim_checks", {}).get("removed", 0) for t in turns if t.get("claim_checks")
    )
    result["all_draft_sentences_removed"] = sum(
        t.get("claim_checks", {}).get("all_removed", False) for t in turns if t.get("claim_checks")
    )
    checks = []
    holdout = json.loads((OUT / "holdout_expectations.json").read_text(encoding="utf-8"))
    for row in rows.values():
        for t in row["turns"]:
            actual = t.get("packet", {}).get("scope", {})
            if original:
                expected = EXPECTED.get(row["id"], {}).get(t["turn"])
                if expected is None:
                    continue
                passed = all(actual.get(k) == v for k, v in expected.items())
            else:
                topics, reps = holdout[row["id"]][t["turn"] - 1]
                expected = {"topics": topics, "rep_numbers": reps}
                passed = (
                    bool(t.get("packet", {}).get("clarification"))
                    if topics is None
                    else set(actual.get("topics", [])) == set(topics)
                )
                if reps is not None:
                    passed = passed and actual.get("rep_numbers", []) == reps
            checks.append(
                {
                    "reference": f"{row['id']}-T{t['turn']}",
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                }
            )
    result["scope"] = {
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "checks": checks,
    }
    result["unmatched_turns"] = [
        f"{r['id']}-T{t['turn']}"
        for r in rows.values()
        for t in r["turns"]
        if t.get("answer") and not trace_numbers(t["answer"], t.get("packet", {}))["passed"]
    ]
    return result


def transcript(rows, label):
    lines = [
        "# " + label,
        "",
        "Full saved answers, including failures. Raw traces and packets remain alongside each JSON artifact.",
    ]
    for row in sorted(rows.values(), key=lambda r: r["id"]):
        lines += [
            "",
            f"## {row['id']} — {row.get('name', '')}",
            "",
            f"Origin: {row.get('origin', '')}. Model: {row.get('model_id', '')}.",
        ]
        for t in row["turns"]:
            adjusted = (t["latency_ms"] - t.get("evaluation_pacing_ms", 0)) / 1000
            lines += [
                "",
                f"### T{t['turn']} — {t.get('provider', row.get('provider'))}; {adjusted:.2f}s excluding eval pacing",
                "",
                "User: " + t["question"],
                "",
                t.get("answer") or f"PROVIDER ERROR: {t.get('error_type')}",
                "",
                f"TTFT: {t.get('first_token_ms')} ms; raw latency: {t['latency_ms']:.2f} ms; pacing: {t.get('evaluation_pacing_ms', 0):.2f} ms.",
            ]
            if t.get("claim_checks"):
                lines += [
                    "",
                    f"Sentence check: {t['claim_checks']['removed']} removed; all draft sentences removed: {t['claim_checks']['all_removed']}.",
                ]
    return "\n".join(lines) + "\n"


def main():
    summary, groups = {}, {}
    for label, directory, provider, original in (
        ("baseline_gemini", ROOT / "evals/layer2/gemini_new_project", "gemini", True),
        ("baseline_3b", ROOT / "evals/layer2/final", "local", True),
        ("baseline_gemini_holdout", OUT / "baseline_holdout_gemini", "gemini", False),
        ("baseline_3b_holdout", OUT / "baseline_holdout_3b", "local", False),
        ("gemini_original", OUT / "checkpoint_gemini", "gemini", True),
        ("qwen3b_original", OUT / "checkpoint_3b_final", "local", True),
        ("qwen7b_original", OUT / "checkpoint_7b_final", "local", True),
        ("gemini_holdout", OUT / "holdout_gemini", "gemini", False),
        ("qwen3b_holdout", OUT / "holdout_3b", "local", False),
        ("qwen7b_holdout", OUT / "holdout_7b", "local", False),
    ):
        rows = read_rows(directory, provider)
        if rows:
            groups[label] = rows
            summary[label] = summarize(rows, original)
            confirmed = json.loads((OUT / "manual_verdict_flags.json").read_text(encoding="utf-8"))[
                "flags"
            ].get(label, [])
            summary[label]["manual_confirmed_verdict_flags_minimum"] = confirmed
            (ROOT / f"docs/next_phase_{label}_transcripts.md").write_text(
                transcript(rows, label), encoding="utf-8"
            )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    table = [
        "| Provider / set | Replies | Errors | Scope checks | Median / p95 | Number flags | Unsupported verdicts (manual minimum) | Repeated value / advice pairs* |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, s in summary.items():
        r = s["repetition"]
        table.append(
            f"| {label}{'' if s['complete'] else ' INCOMPLETE'} | {s['answers']}/{s['turns']} | {s['provider_errors']} | {s['scope']['passed']}/{s['scope']['total']} | {s['reply_median_s']} / {s['reply_p95_s']} s | {s['replies_with_unmatched_numbers']} | ≥{len(s['manual_confirmed_verdict_flags_minimum'])} | {r['repeated_value_pairs']} / {r['repeated_advice_pairs']} of {r['consecutive_pairs']} |"
        )
    lines = [
        "# Next-phase checkpoint results",
        "",
        "Acceptance FAILS: the new core is not reliably conversational. Number tracing and scope/repetition metrics improve, but useful clarifications are filtered out, declines increase, and local models still invent judgments. COACH_CORE remains old. No commit or push. Earlier Layer 2 complete Gemini pass is the baseline. All diagnostics and incomplete runs are preserved separately; only complete checkpoint runs and frozen holdout runs belong in this comparison.",
        "",
        *table,
        "",
        "Provider availability, separate from quality: the initial new 3B pass produced 49/56 replies and seven 20-second deadline failures (12.5%). All were preserved; H01–H03 were replayed ONCE as complete chains (9/9 replies) after the runtime returned to normal. The final quality row reports coherent recovered chains, not a claim that the initial provider error rate was zero. The exact cause of the transient post-model-swap stall is not isolated. 7B p95 exceeds the roughly 15-second target and retains unsupported judgments, so it was not advanced to a separate holdout; the holdout compares Gemini and the existing 3B local provider. The 7B comparison uses the original 13 sequences.",
        "",
        "The holdout was authored and frozen before use; no prompt/resolver changes were driven by its results. The pre-change source was recovered mechanically from this task's original patch journal, without executing historical shell commands. Its persona and all 56 original pre-call packets were verified identical to the saved Gemini baseline before any baseline holdout call (baseline_source/validation.json). The before/after holdout rows are real current provider runs of those two code versions, not fabricated historical conversations. Subsequent checker updates driven by original-set failures were verified offline against every saved Gemini draft: accepted answers were identical, requiring zero replacement requests. Four affected 7B chains were rerun whole; unchanged complete chains/prefixes were reused only after the same offline equivalence check.",
        "",
        "## Refusal/deflection and fabrication must be read together",
        "",
        "| Set | E12 requested value/drill fabrication (manual) | Declines without partial answer* | Bare questions* | Concrete-options questions* | Useful partials* | All draft sentences removed |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {label} | {('3/5' if label == 'baseline_3b' else '0/5') if 'holdout' not in label else 'different questions'} | {s['response_breakdown_proxy'].get('decline_without_partial_proxy', 0)} | {s['response_breakdown_proxy'].get('bare_question', 0)} | {s['response_breakdown_proxy'].get('question_with_concrete_options', 0)} | {s['response_breakdown_proxy'].get('useful_partial_proxy', 0)} | {s['all_draft_sentences_removed']} |"
            for label, s in summary.items()
        ],
        "",
        "*Repetition and response-kind counts are automated proxies, not semantic ground truth. Repetition includes requested repeats/comparisons. Verdict counts are manually confirmed MINIMUM counts; the raw regex proxies missed important failures and remain visible in summary.json. References and review method are in manual_verdict_flags.json. Holdout scope annotations cover topics/rep selection, not every temporal-phase ambiguity; manual phase failures are reported separately. Number presence does not validate meaning or units.",
        "",
        "## Exact writer prompt",
        "",
        "```text",
        PERSONA,
        "```",
        "",
        "## Packet and ladder",
        "",
        "Measurement records carry deterministic definitions, units, explicit limits and formatted display values. Degrees use one decimal; sampled seconds three decimals; dimensionless and normalized distances/speeds two decimals; milliseconds integer precision. The writer sees the same compact evidence table and shared definitions on both providers. Raw measurements remain in the saved session, not as competing athlete values in the writer packet.",
        "",
        "Assessments are computed before inference: consistent / inconsistent only for an applicable explicit retrieved drill standard, otherwise not assessed with the missing basis stated. Existing teaching narratives and research ranges are not numerical grading standards. The current real library has no applicable machine-readable numerical standards, so these saved sessions remain not assessed; no new passing thresholds were invented.",
        "",
        "The deterministic response_plan selects non-coaching, concrete clarification, assumption, missing-data/general guidance, explanation, assessment or practice focus. External state stores scope, clarification options, previous packet fingerprint, cited evidence, recent replies and whether the assessment limit was explained. Same-scope follow-ups reuse retrieval; topic/rep/phase changes fetch fresh scoped evidence. Mixed-topic notes are filtered sentence by sentence; fleche retrieves only fleche material. A source sentence describing a user's chosen rubric is not silently applied to another athlete.",
        "",
        "## What sentence checks catch and miss",
        "",
        "They check numeric presence and display precision, named drills, lexical cue support and explicit priority/ordering terms. Unsupported sentences are removed independently; safe sentences survive. If nothing survives, one unused relevant source cue may be offered, or a short scoped gap and concrete next step. No extra model repair call is made. Sentence-buffered local streaming withholds incomplete/unverified claims and publishes cumulative safe text to the real app queue.",
        "",
        "These checks cannot establish semantic truth: wrong body-part assignments, units outside the narrow physical-unit guard, unsupported qualitative verdicts, causal meaning or paraphrases with misleading word overlap may pass. A narrow unit guard catches personal m/s/W/N claims when that value+unit is absent from athlete measurements; a narrow assessment guard catches some explicit personal verdicts. Neither is comprehensive, as the manual counts demonstrate. Lexical checks also remove valid paraphrases and clarifications. Raw drafts and every removal remain in traces. A numeric pass is never full grounding.",
        "",
        "## Provider and runtime",
        "",
        "Gemini is paced six seconds per actual model request; one bounded 503 retry remains, with no 429 retry loop. Quota failure halts the evaluator and marks the chain incomplete. Runtime routing retains state/packet across fallback; the circuit honors retry-after headers and Google RetryInfo delays. 7B uses Q4_K_M, Vulkan on the integrated Intel Arc GPU, context 4096, generation cap 160 and a 20-second wall deadline, matching 3B settings. No billing was enabled. Credentials are read only from the ignored local .env/environment.",
        "",
        "Gemini TTFT is unavailable in the synchronous provider path. Local TTFT is recorded independently of first verified visible sentence. Checking sentences introduces a deliberate first-visible delay; exposing raw tokens would leak claims later removed. Transport streaming and warm-model retention remain enabled.",
        "",
        "## Manual review and live acceptance",
        "",
        "See docs/next_phase_manual_review.md and docs/next_phase_live_transcripts.md. No automatic default promotion follows these metrics.",
        "",
        "## Review files",
        "",
        "- [Manual failures, acceptance result and next decisions](next_phase_manual_review.md)",
        "- [37 live-app turns and forced-429 trace](next_phase_live_transcripts.md)",
        "- [Runtime, TTFT and request accounting](next_phase_runtime_accounting.md)",
        "- [Canonical packet example](next_phase_packet_example.json) and [exact writer input](next_phase_exact_writer_input.json)",
        *[f"- [{label} full transcripts](next_phase_{label}_transcripts.md)" for label in summary],
        "",
        "Verification: 111 focused core, dialogue, persistence, provider and video-safeguard tests passed. Ruff/format, compile and scoped whitespace checks are recorded at completion. The Windows sandbox temporary-directory ACL issue required running persistence checks outside that sandbox; no test was deleted or weakened to bypass it. Legacy logs include expected invalid-answer/fallback test warnings and an existing telemetry-export shutdown warning.",
    ]
    (ROOT / "docs/coach_next_phase_results.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(table).replace("≥", ">="))


if __name__ == "__main__":
    main()

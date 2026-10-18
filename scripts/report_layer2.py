"""Provider availability, evaluation-only number tracing and paired transcripts."""

import json
import math
import statistics
from collections import Counter
from pathlib import Path

from fencecoach.coach.core_new import _session_key, _snapshot
from fencecoach.coach.core_packet import PERSONA
from fencecoach.coach.number_trace import trace_numbers
from fencecoach.coach.turn_packet import build_packet, resolve_scope
from fencecoach.schemas import CoachRequest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/layer2/final"
IDS = [*(f"H{i:02d}" for i in range(1, 11)), "E11", "E12", "S11"]

# Human annotations of subject/ordinal/phase expectations, never answer fixtures.
EXPECTED = {
    "H01": {
        1: {"topics": ["front_leg", "rear_leg"]},
        2: {"topics": ["torso"]},
        3: {"topics": ["speed"]},
    },
    "H04": {2: {"movement": "fleche"}, 3: {"movement": "fleche"}},
    "H05": {1: {"rep_numbers": [2]}, 3: {"rep_numbers": [2]}},
    "H06": {2: {"rep_numbers": [5]}, 3: {"rep_numbers": [5]}},
    "H07": {
        3: {"topics": ["arm"], "all_reps": True},
        4: {"topics": ["torso"]},
        5: {"topics": ["torso"], "all_reps": True},
    },
    "H08": {2: {"topics": ["rear_leg"]}, 3: {"topics": ["rear_leg"]}},
    "H09": {
        3: {"topics": ["torso"]},
        4: {"topics": ["rear_leg"]},
        5: {"topics": ["rear_leg"]},
        6: {"topics": ["rear_leg"]},
    },
    "H10": {
        2: {"topics": ["arm"]},
        3: {"topics": ["arm"], "rep_numbers": [2]},
        4: {"topics": ["arm"], "rep_numbers": [2]},
    },
    "E11": {
        3: {"topics": ["overview"], "rep_numbers": [2]},
        4: {"rep_numbers": [2]},
        5: {"topics": ["recovery"], "rep_numbers": [2], "phases": ["active_recovery"]},
    },
    "E12": {
        2: {"topics": ["blade"], "phases": ["active_recovery"]},
        3: {"topics": ["speed"]},
        4: {"topics": ["force"]},
        5: {"topics": ["drill"]},
        6: {"topics": ["overview"]},
    },
    "S11": {
        3: {"rep_numbers": [2]},
        5: {"topics": ["recovery"], "rep_numbers": [2], "phases": ["active_recovery"]},
    },
}


def load(directory, provider):
    return {
        ident: json.loads((directory / f"{ident}-{provider}.json").read_text(encoding="utf-8"))
        for ident in IDS
        if (directory / f"{ident}-{provider}.json").exists()
    }


def baseline_packet(turn):
    supplied = {"briefing": "", "tool_evidence": []}
    for event in turn["trace"]:
        if event["step"] == "layer1_input":
            supplied["briefing"] = json.loads(event["detail"])["briefing"]
        elif event["step"] == "tools":
            result = json.loads(event["detail"])["result"]
            try:
                supplied["tool_evidence"].append(json.loads(result))
            except (ValueError, TypeError):
                supplied["tool_evidence"].append(result)
    return supplied


def stat(rows, baseline=False):
    turns = [t for r in rows.values() for t in r["turns"]]
    answers = [t for t in turns if t.get("answer")]
    timings = sorted((t["latency_ms"] - t.get("evaluation_pacing_ms", 0)) / 1000 for t in answers)
    traces = [
        trace_numbers(t["answer"], baseline_packet(t) if baseline else t["packet"]) for t in answers
    ]
    first = [t["first_token_ms"] / 1000 for t in answers if t.get("first_token_ms") is not None]
    return {
        "sequences": len(rows),
        "turns": len(turns),
        "answers": len(answers),
        "provider_errors": len(turns) - len(answers),
        "provider_error_types": dict(Counter(t.get("error_type") for t in turns if t.get("error"))),
        "reply_median_s": round(statistics.median(timings), 2) if timings else None,
        "reply_p95_s": round(timings[math.ceil(len(timings) * 0.95) - 1], 2) if timings else None,
        "reply_max_s": round(max(timings), 2) if timings else None,
        "ttft_median_s": round(statistics.median(first), 2) if first else None,
        "tool_turns": sum(
            (t.get("contract", {}).get("tool_calls", 0) if baseline else t.get("tool_calls", 0)) > 0
            for t in turns
        ),
        "numeric_mentions": sum(len(t["mentions"]) for t in traces),
        "unmatched_numeric_mentions": sum(len(t["unsupported"]) for t in traces),
        "replies_with_unmatched_numbers": sum(not t["passed"] for t in traces),
        "replies_without_unmatched_numbers": sum(t["passed"] for t in traces),
        "exact_only_numeric_pass_replies": sum(t["exact_only_passed"] for t in traces),
        "503_attempts": sum(
            a.get("status") == "503" for t in turns for a in t.get("provider_attempts", [])
        ),
        "evaluation_pacing_total_s": round(
            sum(t.get("evaluation_pacing_ms", 0) for t in turns) / 1000, 2
        ),
    }


def main():
    before_dir = ROOT / "evals/layer1/variants/V3"
    # The extra coherent run hit the daily provider quota and is diagnostic,
    # never a silent replacement for the preserved paired primary run.
    gemini_dir = OUT
    data = {
        p: {"before": load(before_dir, p), "after": load(gemini_dir if p == "gemini" else OUT, p)}
        for p in ("gemini", "local")
    }
    summary, checks = {}, []
    for provider, groups in data.items():
        replay_path = OUT / "error_replays" / f"{provider}.json"
        replays = (
            json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.exists() else []
        )
        summary[provider] = {
            "before": stat(groups["before"], True),
            "after": stat(groups["after"]),
            "after_directory": str(gemini_dir if provider == "gemini" else OUT),
            "initial_run": stat(load(OUT, provider)),
            "error_replays": {
                "attempted": len(replays),
                "recovered": sum(bool(t.get("answer")) for t in replays),
                "remaining_errors": sum(not t.get("answer") for t in replays),
            },
        }
        replay_index = {(t["case"], t["turn"]): t for t in replays}
        available = {
            ident: {
                "turns": [
                    t if t.get("answer") else replay_index.get((ident, t["turn"]), t)
                    for t in row["turns"]
                ]
            }
            for ident, row in groups["after"].items()
        }
        summary[provider]["available_outcomes_after_error_replay"] = stat(available)
        for turn in replays:
            if turn.get("answer"):
                checks.append(
                    {
                        "reference": f"{turn['case']}-{provider}-T{turn['turn']}-isolated-replay",
                        **trace_numbers(turn["answer"], turn["packet"]),
                    }
                )
        for ident, row in groups["after"].items():
            for turn in row["turns"]:
                if turn.get("answer"):
                    checks.append(
                        {
                            "reference": f"{ident}-{provider}-T{turn['turn']}",
                            **trace_numbers(turn["answer"], turn["packet"]),
                        }
                    )
    equal = []
    for ident in IDS:
        if ident not in data["gemini"]["after"] or ident not in data["local"]["after"]:
            continue
        for gemini, local in zip(
            data["gemini"]["after"][ident]["turns"],
            data["local"]["after"][ident]["turns"],
            strict=True,
        ):
            same = all(
                gemini["packet"].get(field) == local["packet"].get(field)
                for field in (
                    "scope",
                    "availability",
                    "measurements",
                    "general_guidance",
                    "requested_operation",
                )
            )
            equal.append(
                {"case": ident, "turn": gemini["turn"], "same_scope_and_prefetched_evidence": same}
            )
    summary["provider_packet_parity"] = {
        "equal": sum(t["same_scope_and_prefetched_evidence"] for t in equal),
        "compared": len(equal),
        "details": equal,
    }
    scope_checks = []
    current_checks = []
    for provider in ("gemini", "local"):
        for ident, expected_turns in EXPECTED.items():
            actual = {
                t["turn"]: t["packet"]["scope"] for t in data[provider]["after"][ident]["turns"]
            }
            for turn, expectation in expected_turns.items():
                scope_checks.append(
                    {
                        "reference": f"{ident}-{provider}-T{turn}",
                        "expected": expectation,
                        "actual": actual[turn],
                        "passed": all(actual[turn].get(k) == v for k, v in expectation.items()),
                    }
                )
                request = CoachRequest.model_validate(
                    next(
                        t["request"]
                        for t in data[provider]["after"][ident]["turns"]
                        if t["turn"] == turn
                    )
                )
                snapshot = json.loads(_snapshot(_session_key(request)))
                state = resolve_scope(request, snapshot)
                current = build_packet(request, state, snapshot)["scope"]
                current_checks.append(
                    {
                        "reference": f"{ident}-{provider}-T{turn}",
                        "passed": all(current.get(k) == v for k, v in expectation.items()),
                        "scope": current,
                    }
                )
    summary["annotated_scope_checks"] = {
        "passed": sum(t["passed"] for t in scope_checks),
        "total": len(scope_checks),
        "details": scope_checks,
    }
    summary["current_code_offline_scope_checks"] = {
        "passed": sum(t["passed"] for t in current_checks),
        "total": len(current_checks),
        "details": current_checks,
    }
    fixed_path = OUT.parent / "scope_fix/H07-local.json"
    if fixed_path.exists():
        fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
        summary["post_review_scope_fix_qwen"] = stat({"H07": fixed})
        for turn in fixed["turns"]:
            checks.append(
                {
                    "reference": f"H07-local-T{turn['turn']}-post-scope-fix",
                    **trace_numbers(turn["answer"], turn["packet"]),
                }
            )
    (OUT.parent / "scope_expectations.json").write_text(
        json.dumps(EXPECTED, indent=2), encoding="utf-8"
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "number_tracing.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Layer 2 + evidence packets — checkpoint",
        "",
        "The application default remains COACH_CORE=old. The opt-in new core resolves conversation scope, fetches a small measured-only packet and retrieves separately labeled teaching before inference. No Layer 5 response blocking, repair or canned answer was added. No commit or push.",
        "",
        "State is stored in DialogueState/RunRecord and carried through the existing repository path, independently of provider sessions: topic, movement, phase, rep selection, last cited evidence, open clarification options, answering provider and new-core turn count. Legacy user history bootstraps scope; legacy assistant assertions are excluded from the new writer's initial history. Actual new-core replies are carried thereafter.",
        "",
        "Packets expose tracking_unsupported / none / measurements_available and requested-scope availability. Rejected clip measurements are withheld (including H05/H06); missing rep/phase never substitutes another. Reference comparisons, reference ranges, drill benchmarks and numeric target notes are excluded from athlete evidence. Library text is tagged general teaching, not the athlete's target. Gemini alone has an optional bounded supplemental-packet tool; Qwen has no tools.",
        "",
        "## Before / after",
        "",
        "Identical 13 sequences / 56 attempted turns per provider, calling the coach function directly on saved requests. These are not running-app live acceptance conversations. V3 is the previous Layer 1 candidate. Provider errors are availability failures, not coaching quality failures. Latencies below are successful replies only, including the core's bounded 503 retry when used. Error replays do not replace primary turns or retroactively repair their downstream histories.",
        "",
        "| Version | Provider | Replies / turns | Provider errors | Reply median / p95 | Replies with unmatched numbers | Unmatched / numeric mentions | Tool turns |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider in ("gemini", "local"):
        for version in ("before", "after"):
            s = summary[provider][version]
            lines.append(
                f"| {'V3' if version == 'before' else 'Layer 2 packet'} | {provider} | {s['answers']}/{s['turns']} | {s['provider_errors']} | {s['reply_median_s']}s / {s['reply_p95_s']}s | {s['replies_with_unmatched_numbers']}/{s['answers']} | {s['unmatched_numeric_mentions']}/{s['numeric_mentions']} | {s['tool_turns']} |"
            )
    lines += [
        "",
        "## Number tracing and provider errors",
        "",
        "Each digit/cardinal/rep ordinal in a returned answer is matched to a value and JSON path in that turn's actual supplied packet, including optional supplemental packets. Source IDs, session IDs and URLs do not authorize numbers. Standard decimal rounding is accepted and explicitly labeled; exact-only pass counts are in summary.json. Pronouns such as 'the one holding the sword' are excluded. number_tracing.json preserves every match and unmatched mention.",
        "",
        "V3 numeric supply is reconstructed from its actual briefing and tool results, excluding assistant history. Its broad context contains reference data absent from the new athlete packet, so this is a supply-presence comparison, not a semantic correctness score. Numeric presence does not validate feature, rep, unit, causal claims, qualitative faults or using a research value as a target. Replies with no numbers can still be wrong.",
        "",
    ]
    for p in ("gemini", "local"):
        s = summary[p]
        r = s["error_replays"]
        lines.append(
            f"{p}: primary provider error types {s['after']['provider_error_types']}; actual 503 failed attempts {s['after']['503_attempts']}. One isolated replay pass: {r['recovered']}/{r['attempted']} recovered, {r['remaining_errors']} still errored. Each replay preserves the original pre-error history/state. Gemini replays are spaced six seconds per API request to respect the observed 15-request/minute free-tier quota; evaluation spacing is recorded separately and is not app latency."
        )
        outcomes = s["available_outcomes_after_error_replay"]
        lines.append(
            f"{p} distinct available outcomes including isolated recovered turns: {outcomes['answers']}/{outcomes['turns']} replies; {outcomes['replies_with_unmatched_numbers']} replies contain unmatched numbers ({outcomes['unmatched_numeric_mentions']}/{outcomes['numeric_mentions']} numeric mentions). This union is useful for reviewing source claims, not proof of uninterrupted conversation quality."
        )
    parity = summary["provider_packet_parity"]
    lines += [
        "",
        f"Resolved scope and prefetched source evidence are identical across providers on {parity['equal']}/{parity['compared']} paired turns. Last-cited IDs and answering-provider metadata can differ because actual replies differ.",
        "Those paired runs precede the post-review H07 topic fix. The recorded runs pass 60/62 human-annotated scope checks; the corrected code passes all 62 offline checks. The affected Qwen chain was rerun in scope_fix; live Gemini revalidation is quota-blocked. No failed historical result was overwritten.",
        "",
        "## Qwen runtime",
        "",
        "Observed model: Qwen2.5 3B (3.1B), Q4_K_M, already fully GPU-resident. Thinking was already disabled and no thinking capability is advertised. Old inference used 16k context after a 4k warm-up, up to 240 generated tokens, tool results of roughly 39k–51k characters on the worst turns, and a 180-second per-read timeout across potentially multiple model calls. Those are observed runtime problems; old logs lack timings needed to isolate each component causally.",
        "",
        "New core uses matching 4096-token warm/inference context, no Qwen tool loop, plain-text output, a 160-token generation cap, indefinite keep-alive and an asyncio-enforced 20-second total request deadline that cancels and closes the HTTP stream. Quantization weights are unchanged. Each response records prompt evaluation, load/generation timing, token counts, done reason and first-token latency. Warm-up is separately recorded in qwen_warm.json and excluded from per-turn latency. runtime_diagnosis.json records before/after model metadata and the old payload sizes.",
        "Measured on this hardware: one-time context warm-up 7.32s; reply median 4.22s, p95 9.54s, max 18.64s; no local provider errors. First-token median 1.62s from the local provider request (Gemini TTFT is unavailable for synchronous invoke). Median load 6.32ms, prefill 1.04s, generation 2.43s; maximum input 2441 tokens and output 134 tokens. All 56 generations ended with stop, none hit the 160-token cap, and inputs stayed below 4096. A realistic observed ordinary-reply budget is roughly 10s at p95 with a hard 20s failure boundary, not a 2s promise.",
        "",
        "## Manual acceptance review",
        "",
        "The numeric results do not establish a quality win. All returned primary replies and isolated Gemini replays were read; the bad ones remain in the transcript. H01 acceptance here means on-topic general advice, acknowledging unavailable measurements, and no fabricated personal or visibility finding.",
        "",
        "| Acceptance aspect | V3 before | Packet core after |",
        "|---|---|---|",
        "| H01 knees/back/speed, Gemini | Topic-specific general advice; no usable tracking. | Narrow H01 behavior passes 3/3 primary turns: stays on the subject, labels general guidance, no invented angles or missing-body-part claim. Some broad causal advice still exceeds the retrieved wording. |",
        "| H01 knees/back/speed, Qwen | Redirects to arm extension; fails 0/3. | Still fails 0/3: T1 calls the lunge on-track without data; T2 says the torso appears upright; T3 converts a 2.69 m/s research sword-speed result into the athlete's novice target. These are different failures, not an acceptance improvement. |",
        "| Rep/topic/phase carry-over | Implicit model memory, wrong rep/topic examples. | Application scope matches 60/62 annotated primary-turn expectations; both failures are H07-T5, where 'during the drill' overrode torso. That resolver defect is fixed: current-code offline audit 62/62 and the five-turn Qwen H07 rerun passes scope. Live Gemini revalidation of this fix is quota-blocked. |",
        "| Original arm chain H10 | Topic drift / weak verdict. | Scoped to arm and then rep 2 in code, but Gemini T2 still repeats angles instead of answering good/bad; Qwen T2/T3 declares the extension good without a basis and T4 talks about the rear leg despite the arm packet. Not conversationally accepted. |",
        "| Measurement meaning | Wrong standards, features and causal claims. | Qwen H07 T2/T3 confuses arm direction with elbow bend; its corrected-scope T5 still mixes torso tilt and pitch change. Gemini E11/S11 isolated replay T5 calls 0.1s active-recovery duration an onset time. Matching numbers do not validate these claims. |",
        "| Availability and footage scope | False no-data and visibility claims. | Packet availability is explicit and rejected data are withheld. Gemini H08 isolated replay T2 nevertheless treats the filtered rear-leg packet as proof that the entire session lacks arm/torso measurements. A remaining model error, not a missing-data fact. |",
        "| Missing measurements / fabrication bait E12 | Qwen infers blade stability; Gemini generally withholds unavailable items. | Gemini isolated replays withhold blade measurements, calibrated m/s, force and the absent named drill. Qwen T3 invents 0.65m torso length and 1.37m/s; T4 invents measured 100 watts; T5 invents the Dragonfly drill. Zero-fabrication acceptance fails. |",
        "| Unsupported footage H05/H06 | Prior writers used rejected phase numbers. | The packet withholds those numbers. Gemini labels general advice and resolves last rep to rep 5; Qwen still turns generic teaching into individual correctness targets. |",
        "",
        "The optional Gemini tool also exposed a scalar/list argument mismatch in the extra diagnostic run. The core now normalizes either representation and returns optional lookup failures to the model as tool results instead of failing the whole answer. This is tool-protocol handling, not Layer 5 claim checking; unit tests cover it. Live Gemini verification of that final fix is blocked by quota.",
        "",
        "## Quota boundary, verification and stop",
        "",
        "The initial 13-sequence Gemini pass returned 24 replies and 32 per-minute quota errors. The requested isolated error replay recovered all 32. An additional attempt at continuous, paced chains then exhausted the free-tier 500-requests/day quota (see paced_complete/H06-gemini.json), with a provider retry hint of roughly two hours. That process was stopped rather than continuing doomed requests. Its partial files are diagnostic only and excluded from the table. A complete coherent post-fix Gemini rerun remains blocked; isolated replies do not prove live chain continuity.",
        "",
        "97 focused core/state, persistence, provider-switch, dialogue and existing video-safeguard tests pass outside the known Windows temporary-directory sandbox ACL issue. Tests include a forced 429 provider switch, clarification-option ordinals, exact rep/phase preservation, rejected-data abstention, numeric-source matching, bounded 503 retry and cancellation of a hanging local HTTP stream. A library outage is explicitly labeled unavailable, never treated as proof a named item is absent, and never gates the model reply; the successful-lookup packet is unchanged. No new response verifier or repair mechanism was introduced.",
        "",
        "Stop at this checkpoint. State/evidence infrastructure and Qwen runtime improved, but coaching acceptance is not met across providers. COACH_CORE remains old. Layer 5, default promotion, commit and push are not authorized at this checkpoint; wait for user review. The next live validation requires Gemini quota recovery.",
        "",
        "## Exact fixed writer prompt",
        "",
        "```text",
        PERSONA,
        "```",
        "",
        "Exact per-turn packets, state before/after, actual recent history, provider attempts and raw responses are in evals/layer2/final/*.json. The Gemini tuning probe is separately retained under evals/layer2/gemini_tune; it is not mixed into final metrics.",
        "",
    ]
    (ROOT / "docs/coach_eval_results.md").write_text("\n".join(lines), encoding="utf-8")
    transcripts = [
        "# Layer 2 paired transcripts",
        "",
        "V3 and the Layer 2 packet core answer the same user questions on the same saved sessions. Initial provider errors and isolated error replays are preserved separately. Full packets and traces accompany the raw JSON; numeric flags below are evaluation-only and never changed the reply.",
        "",
    ]
    check_index = {c["reference"]: c for c in checks}
    for ident in IDS:
        for provider in ("gemini", "local"):
            row = data[provider]["after"].get(ident)
            if not row:
                continue
            before = {t["turn"]: t for t in data[provider]["before"][ident]["turns"]}
            transcripts += [f"## {ident} — {provider}", "", row["origin"], ""]
            for t in row["turns"]:
                ref = f"{ident}-{provider}-T{t['turn']}"
                old = before[t["turn"]]
                scope = t["packet"].get("scope", {})
                transcripts += [
                    f"### {ref}",
                    "",
                    "User (verbatim):",
                    "",
                    "```text",
                    t["question"],
                    "```",
                    "",
                    f"V3 ({old['latency_ms'] / 1000:.2f}s):",
                    "",
                    "```text",
                    old.get("answer") or old.get("error", "No reply"),
                    "```",
                    "",
                    f"Layer 2 ({t['latency_ms'] / 1000:.2f}s; first token {t.get('first_token_ms')}ms):",
                    "",
                    "```text",
                    t.get("answer") or t.get("error", "No reply"),
                    "```",
                    "",
                    f"Resolved scope: {json.dumps(scope, ensure_ascii=False)}. Availability: {t['packet'].get('availability', {}).get('status')}; measurements: {len(t['packet'].get('measurements', []))}.",
                    "",
                ]
                if ref in check_index:
                    checked = check_index[ref]
                    transcripts += [
                        f"Number trace: {len(checked['mentions'])} mentions; unmatched: {json.dumps(checked['unsupported'], ensure_ascii=False)}.",
                        "",
                    ]
                else:
                    transcripts += [
                        "Provider error; excluded from numeric/quality denominators.",
                        "",
                    ]
    for provider in ("gemini", "local"):
        path = OUT / "error_replays" / f"{provider}.json"
        for t in json.loads(path.read_text(encoding="utf-8")) if path.exists() else []:
            transcripts += [
                f"## Isolated error replay — {t['case']}-{provider}-T{t['turn']}",
                "",
                f"Original question: {t['question']}",
                "",
                "```text",
                t.get("answer") or t.get("error", "No reply"),
                "```",
                "",
                f"Total {t['latency_ms'] / 1000:.2f}s; evaluation pacing {t.get('evaluation_pacing_ms', 0) / 1000:.2f}s. Numeric tracing: {json.dumps(trace_numbers(t['answer'], t['packet']) if t.get('answer') else {'provider_error': True}, ensure_ascii=False)}",
                "",
            ]
    if fixed_path.exists():
        for t in fixed["turns"]:
            transcripts += [
                f"## Post-review scope fix — H07-local-T{t['turn']}",
                "",
                f"User: {t['question']}",
                "",
                f"Qwen ({t['latency_ms'] / 1000:.2f}s):",
                "",
                "```text",
                t.get("answer") or t.get("error", "No reply"),
                "```",
                "",
                f"Scope: {json.dumps(t['packet']['scope'])}. Number tracing: {json.dumps(trace_numbers(t['answer'], t['packet']) if t.get('answer') else {'provider_error': True}, ensure_ascii=False)}",
                "",
            ]
    (ROOT / "docs/layer2_transcripts.md").write_text("\n".join(transcripts), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

# Layer 2 + evidence packets — checkpoint

> Current checkpoint: [next-phase results](coach_next_phase_results.md), [manual failures and decisions](next_phase_manual_review.md), and [10 live-app conversations](next_phase_live_transcripts.md). Conversational acceptance is NOT met; old remains the default.

> Latest check: the complete paced Gemini pass now has 56/56 replies with zero provider errors. The historical quota-blocked results below are preserved. See [the updated report](layer2_gemini_completion.md) and [full transcripts](layer2_gemini_completion_transcripts.md).

The application default remains COACH_CORE=old. The opt-in new core resolves conversation scope, fetches a small measured-only packet and retrieves separately labeled teaching before inference. No Layer 5 response blocking, repair or canned answer was added. No commit or push.

State is stored in DialogueState/RunRecord and carried through the existing repository path, independently of provider sessions: topic, movement, phase, rep selection, last cited evidence, open clarification options, answering provider and new-core turn count. Legacy user history bootstraps scope; legacy assistant assertions are excluded from the new writer's initial history. Actual new-core replies are carried thereafter.

Packets expose tracking_unsupported / none / measurements_available and requested-scope availability. Rejected clip measurements are withheld (including H05/H06); missing rep/phase never substitutes another. Reference comparisons, reference ranges, drill benchmarks and numeric target notes are excluded from athlete evidence. Library text is tagged general teaching, not the athlete's target. Gemini alone has an optional bounded supplemental-packet tool; Qwen has no tools.

## Before / after

Identical 13 sequences / 56 attempted turns per provider, calling the coach function directly on saved requests. These are not running-app live acceptance conversations. V3 is the previous Layer 1 candidate. Provider errors are availability failures, not coaching quality failures. Latencies below are successful replies only, including the core's bounded 503 retry when used. Error replays do not replace primary turns or retroactively repair their downstream histories.

| Version | Provider | Replies / turns | Provider errors | Reply median / p95 | Replies with unmatched numbers | Unmatched / numeric mentions | Tool turns |
|---|---|---:|---:|---:|---:|---:|---:|
| V3 | gemini | 47/56 | 9 | 1.54s / 8.06s | 3/47 | 3/101 | 40 |
| Layer 2 packet | gemini | 24/56 | 32 | 1.08s / 5.45s | 1/24 | 4/44 | 1 |
| V3 | local | 55/56 | 1 | 8.29s / 42.26s | 18/55 | 48/148 | 3 |
| Layer 2 packet | local | 56/56 | 0 | 4.22s / 9.54s | 5/56 | 7/48 | 0 |

## Number tracing and provider errors

Each digit/cardinal/rep ordinal in a returned answer is matched to a value and JSON path in that turn's actual supplied packet, including optional supplemental packets. Source IDs, session IDs and URLs do not authorize numbers. Standard decimal rounding is accepted and explicitly labeled; exact-only pass counts are in summary.json. Pronouns such as 'the one holding the sword' are excluded. number_tracing.json preserves every match and unmatched mention.

V3 numeric supply is reconstructed from its actual briefing and tool results, excluding assistant history. Its broad context contains reference data absent from the new athlete packet, so this is a supply-presence comparison, not a semantic correctness score. Numeric presence does not validate feature, rep, unit, causal claims, qualitative faults or using a research value as a target. Replies with no numbers can still be wrong.

gemini: primary provider error types {'GoogleRateLimitError': 32}; actual 503 failed attempts 1. One isolated replay pass: 32/32 recovered, 0 still errored. Each replay preserves the original pre-error history/state. Gemini replays are spaced six seconds per API request to respect the observed 15-request/minute free-tier quota; evaluation spacing is recorded separately and is not app latency.
gemini distinct available outcomes including isolated recovered turns: 56/56 replies; 2 replies contain unmatched numbers (5/176 numeric mentions). This union is useful for reviewing source claims, not proof of uninterrupted conversation quality.
local: primary provider error types {}; actual 503 failed attempts 0. One isolated replay pass: 0/0 recovered, 0 still errored. Each replay preserves the original pre-error history/state. Gemini replays are spaced six seconds per API request to respect the observed 15-request/minute free-tier quota; evaluation spacing is recorded separately and is not app latency.
local distinct available outcomes including isolated recovered turns: 56/56 replies; 5 replies contain unmatched numbers (7/48 numeric mentions). This union is useful for reviewing source claims, not proof of uninterrupted conversation quality.

Resolved scope and prefetched source evidence are identical across providers on 56/56 paired turns. Last-cited IDs and answering-provider metadata can differ because actual replies differ.
Those paired runs precede the post-review H07 topic fix. The recorded runs pass 60/62 human-annotated scope checks; the corrected code passes all 62 offline checks. The affected Qwen chain was rerun in scope_fix; live Gemini revalidation is quota-blocked. No failed historical result was overwritten.

## Qwen runtime

Observed model: Qwen2.5 3B (3.1B), Q4_K_M, already fully GPU-resident. Thinking was already disabled and no thinking capability is advertised. Old inference used 16k context after a 4k warm-up, up to 240 generated tokens, tool results of roughly 39k–51k characters on the worst turns, and a 180-second per-read timeout across potentially multiple model calls. Those are observed runtime problems; old logs lack timings needed to isolate each component causally.

New core uses matching 4096-token warm/inference context, no Qwen tool loop, plain-text output, a 160-token generation cap, indefinite keep-alive and an asyncio-enforced 20-second total request deadline that cancels and closes the HTTP stream. Quantization weights are unchanged. Each response records prompt evaluation, load/generation timing, token counts, done reason and first-token latency. Warm-up is separately recorded in qwen_warm.json and excluded from per-turn latency. runtime_diagnosis.json records before/after model metadata and the old payload sizes.
Measured on this hardware: one-time context warm-up 7.32s; reply median 4.22s, p95 9.54s, max 18.64s; no local provider errors. First-token median 1.62s from the local provider request (Gemini TTFT is unavailable for synchronous invoke). Median load 6.32ms, prefill 1.04s, generation 2.43s; maximum input 2441 tokens and output 134 tokens. All 56 generations ended with stop, none hit the 160-token cap, and inputs stayed below 4096. A realistic observed ordinary-reply budget is roughly 10s at p95 with a hard 20s failure boundary, not a 2s promise.

## Manual acceptance review

The numeric results do not establish a quality win. All returned primary replies and isolated Gemini replays were read; the bad ones remain in the transcript. H01 acceptance here means on-topic general advice, acknowledging unavailable measurements, and no fabricated personal or visibility finding.

| Acceptance aspect | V3 before | Packet core after |
|---|---|---|
| H01 knees/back/speed, Gemini | Topic-specific general advice; no usable tracking. | Narrow H01 behavior passes 3/3 primary turns: stays on the subject, labels general guidance, no invented angles or missing-body-part claim. Some broad causal advice still exceeds the retrieved wording. |
| H01 knees/back/speed, Qwen | Redirects to arm extension; fails 0/3. | Still fails 0/3: T1 calls the lunge on-track without data; T2 says the torso appears upright; T3 converts a 2.69 m/s research sword-speed result into the athlete's novice target. These are different failures, not an acceptance improvement. |
| Rep/topic/phase carry-over | Implicit model memory, wrong rep/topic examples. | Application scope matches 60/62 annotated primary-turn expectations; both failures are H07-T5, where 'during the drill' overrode torso. That resolver defect is fixed: current-code offline audit 62/62 and the five-turn Qwen H07 rerun passes scope. Live Gemini revalidation of this fix is quota-blocked. |
| Original arm chain H10 | Topic drift / weak verdict. | Scoped to arm and then rep 2 in code, but Gemini T2 still repeats angles instead of answering good/bad; Qwen T2/T3 declares the extension good without a basis and T4 talks about the rear leg despite the arm packet. Not conversationally accepted. |
| Measurement meaning | Wrong standards, features and causal claims. | Qwen H07 T2/T3 confuses arm direction with elbow bend; its corrected-scope T5 still mixes torso tilt and pitch change. Gemini E11/S11 isolated replay T5 calls 0.1s active-recovery duration an onset time. Matching numbers do not validate these claims. |
| Availability and footage scope | False no-data and visibility claims. | Packet availability is explicit and rejected data are withheld. Gemini H08 isolated replay T2 nevertheless treats the filtered rear-leg packet as proof that the entire session lacks arm/torso measurements. A remaining model error, not a missing-data fact. |
| Missing measurements / fabrication bait E12 | Qwen infers blade stability; Gemini generally withholds unavailable items. | Gemini isolated replays withhold blade measurements, calibrated m/s, force and the absent named drill. Qwen T3 invents 0.65m torso length and 1.37m/s; T4 invents measured 100 watts; T5 invents the Dragonfly drill. Zero-fabrication acceptance fails. |
| Unsupported footage H05/H06 | Prior writers used rejected phase numbers. | The packet withholds those numbers. Gemini labels general advice and resolves last rep to rep 5; Qwen still turns generic teaching into individual correctness targets. |

The optional Gemini tool also exposed a scalar/list argument mismatch in the extra diagnostic run. The core now normalizes either representation and returns optional lookup failures to the model as tool results instead of failing the whole answer. This is tool-protocol handling, not Layer 5 claim checking; unit tests cover it. Live Gemini verification of that final fix is blocked by quota.

## Quota boundary, verification and stop

The initial 13-sequence Gemini pass returned 24 replies and 32 per-minute quota errors. The requested isolated error replay recovered all 32. An additional attempt at continuous, paced chains then exhausted the free-tier 500-requests/day quota (see paced_complete/H06-gemini.json), with a provider retry hint of roughly two hours. That process was stopped rather than continuing doomed requests. Its partial files are diagnostic only and excluded from the table. A complete coherent post-fix Gemini rerun remains blocked; isolated replies do not prove live chain continuity.

97 focused core/state, persistence, provider-switch, dialogue and existing video-safeguard tests pass outside the known Windows temporary-directory sandbox ACL issue. Tests include a forced 429 provider switch, clarification-option ordinals, exact rep/phase preservation, rejected-data abstention, numeric-source matching, bounded 503 retry and cancellation of a hanging local HTTP stream. A library outage is explicitly labeled unavailable, never treated as proof a named item is absent, and never gates the model reply; the successful-lookup packet is unchanged. No new response verifier or repair mechanism was introduced.

Stop at this checkpoint. State/evidence infrastructure and Qwen runtime improved, but coaching acceptance is not met across providers. COACH_CORE remains old. Layer 5, default promotion, commit and push are not authorized at this checkpoint; wait for user review. The next live validation requires Gemini quota recovery.

## Exact fixed writer prompt

```text
You are FenceCoach, coaching an athlete in an ongoing conversation.
Answer their current question directly, briefly and naturally, without headers or a generic closing question.
The application resolves topic, phase and rep in the turn packet. Follow that scope.
Athlete facts come from this turn's measurements; history is conversational context, not proof.
Teaching material is general advice, not an observed fault or a numeric target for this athlete.
When measurements are unavailable, stay on the requested subject and give relevant library guidance
labeled as general advice. Missing tracking is not proof that footage fails to show a body part.
Give a useful partial answer for the specific item you can support. Ask for clarification only
when the packet lists unresolved choices, using those choices. Never request measurements that
the application already provides. Do not invent numbers, norms, blade observations or causal claims.
Tools, when available, are an optional extra; the packet normally contains everything needed.
Return only the answer, usually two or three sentences. Separate measured observations from coaching interpretation.
```

Exact per-turn packets, state before/after, actual recent history, provider attempts and raw responses are in evals/layer2/final/*.json. The Gemini tuning probe is separately retained under evals/layer2/gemini_tune; it is not mixed into final metrics.

<!-- complete-gemini-pass -->

## Complete Gemini pass — 2026-10-14

The quota blocker for the earlier Layer 2 check is resolved by the supplied project key. All 13 original chains / 56 turns now have a coherent complete Gemini pass, preserved separately from the earlier primary run and isolated replays.

[Updated comparison and remaining failures](layer2_gemini_completion.md) · [Complete new transcripts](layer2_gemini_completion_transcripts.md).

| Run | Replies | Provider errors | Median / p95 excluding eval pacing | Replies with unmatched numbers | Unmatched / mentions | Tool turns |
|---|---:|---:|---:|---:|---:|---:|
| Gemini V3 | 47/56 | 9 | 1.54s / 8.06s | 3/47 | 3/101 | 40 |
| Gemini initial Layer 2 | 24/56 | 32 | 1.08s / 5.45s | 1/24 | 4/44 | 1 |
| Gemini complete paced Layer 2 | 56/56 | 0 | 0.94s / 4.62s | 2/56 | 2/163 | 1 |
| Qwen Layer 2 (preserved) | 56/56 | 0 | 4.22s / 9.54s | 5/56 | 7/48 | 0 |

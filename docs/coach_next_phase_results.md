# Next-phase checkpoint results

Acceptance FAILS: the new core is not reliably conversational. Number tracing and scope/repetition metrics improve, but useful clarifications are filtered out, declines increase, and local models still invent judgments. COACH_CORE remains old. No commit or push. Earlier Layer 2 complete Gemini pass is the baseline. All diagnostics and incomplete runs are preserved separately; only complete checkpoint runs and frozen holdout runs belong in this comparison.

| Provider / set | Replies | Errors | Scope checks | Median / p95 | Number flags | Unsupported verdicts (manual minimum) | Repeated value / advice pairs* |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline_gemini | 56/56 | 0 | 31/31 | 0.94 / 4.62 s | 2 | ≥0 | 14 / 1 of 43 |
| baseline_3b | 56/56 | 0 | 30/31 | 4.22 / 9.54 s | 5 | ≥8 | 1 / 5 of 43 |
| baseline_gemini_holdout | 48/48 | 0 | 29/48 | 3.4 / 7.04 s | 7 | ≥0 | 10 / 0 of 36 |
| baseline_3b_holdout | 48/48 | 0 | 29/48 | 2.25 / 4.87 s | 4 | ≥7 | 2 / 0 of 36 |
| gemini_original | 56/56 | 0 | 31/31 | 0.87 / 3.56 s | 0 | ≥0 | 3 / 0 of 43 |
| qwen3b_original | 56/56 | 0 | 31/31 | 3.87 / 9.02 s | 0 | ≥6 | 1 / 1 of 43 |
| qwen7b_original | 56/56 | 0 | 31/31 | 7.18 / 15.99 s | 0 | ≥10 | 1 / 4 of 43 |
| gemini_holdout | 48/48 | 0 | 36/48 | 4.04 / 5.96 s | 0 | ≥0 | 4 / 0 of 36 |
| qwen3b_holdout | 48/48 | 0 | 36/48 | 2.84 / 4.77 s | 0 | ≥2 | 3 / 0 of 36 |

Provider availability, separate from quality: the initial new 3B pass produced 49/56 replies and seven 20-second deadline failures (12.5%). All were preserved; H01–H03 were replayed ONCE as complete chains (9/9 replies) after the runtime returned to normal. The final quality row reports coherent recovered chains, not a claim that the initial provider error rate was zero. The exact cause of the transient post-model-swap stall is not isolated. 7B p95 exceeds the roughly 15-second target and retains unsupported judgments, so it was not advanced to a separate holdout; the holdout compares Gemini and the existing 3B local provider. The 7B comparison uses the original 13 sequences.

The holdout was authored and frozen before use; no prompt/resolver changes were driven by its results. The pre-change source was recovered mechanically from this task's original patch journal, without executing historical shell commands. Its persona and all 56 original pre-call packets were verified identical to the saved Gemini baseline before any baseline holdout call (baseline_source/validation.json). The before/after holdout rows are real current provider runs of those two code versions, not fabricated historical conversations. Subsequent checker updates driven by original-set failures were verified offline against every saved Gemini draft: accepted answers were identical, requiring zero replacement requests. Four affected 7B chains were rerun whole; unchanged complete chains/prefixes were reused only after the same offline equivalence check.

## Refusal/deflection and fabrication must be read together

| Set | E12 requested value/drill fabrication (manual) | Declines without partial answer* | Bare questions* | Concrete-options questions* | Useful partials* | All draft sentences removed |
|---|---:|---:|---:|---:|---:|---:|
| baseline_gemini | 0/5 | 8 | 0 | 0 | 5 | 0 |
| baseline_3b | 3/5 | 0 | 0 | 0 | 0 | 0 |
| baseline_gemini_holdout | different questions | 2 | 0 | 1 | 3 | 0 |
| baseline_3b_holdout | different questions | 1 | 0 | 0 | 0 | 0 |
| gemini_original | 0/5 | 11 | 0 | 0 | 12 | 6 |
| qwen3b_original | 0/5 | 5 | 3 | 0 | 1 | 7 |
| qwen7b_original | 0/5 | 10 | 0 | 0 | 6 | 14 |
| gemini_holdout | different questions | 8 | 3 | 0 | 6 | 6 |
| qwen3b_holdout | different questions | 9 | 4 | 0 | 0 | 13 |

*Repetition and response-kind counts are automated proxies, not semantic ground truth. Repetition includes requested repeats/comparisons. Verdict counts are manually confirmed MINIMUM counts; the raw regex proxies missed important failures and remain visible in summary.json. References and review method are in manual_verdict_flags.json. Holdout scope annotations cover topics/rep selection, not every temporal-phase ambiguity; manual phase failures are reported separately. Number presence does not validate meaning or units.

## Exact writer prompt

```text
You are FenceCoach, coaching an athlete in an ongoing conversation.
Answer their current question directly, briefly and naturally, without headers or a generic closing question.
The application resolves topic, phase and rep in the turn packet. Follow that scope.
Athlete facts come from this turn's measurements; history is conversational context, not proof.
Quote measurement displays exactly; respect each definition and does_not_indicate note.
Give the assessment verdict plainly when consistent or inconsistent: say it is consistent
or inconsistent with the cited cue and explain why. A not-assessed verdict gets ONE sentence
with the observation and what would be needed to judge it; if already explained, advance to
a useful next step, not another decline or another list of angles.
Follow the response ladder: answer from evidence; for moderate confidence state the packet's
assumption and answer; for low confidence ask ONE question using its concrete options.
For a missing item name only that gap and offer what is known and what would answer it.
Only when no athlete evidence is available use retrieved guidance labeled general advice.
Library teaching never establishes a measured fault or universal athlete target.
Only offer technique cues, drills, sequence or priority claims supported by retrieved text.
If the retrieved text has no how-to instructions, say that specifically instead of inventing steps.
Respect scope_text: a filtered packet is not the whole session. Missing tracking is not
proof that footage fails to show a body part. Use the capture's declared side and camera context.
conversation_memory lists values and advice already given: advance the conversation instead
of repeating them unless the user explicitly asks to repeat or compare. Use plain words,
not raw metric names. Greetings, acknowledgments and restart get a short natural reply without
evidence, extra questions or numbers. Session-summary turns summarize what is measured.
Tools are optional extras for genuinely missing details; ordinary questions need no tool.
Return only the answer, normally one to three sentences. Never invent a number or a verdict.
```

## Packet and ladder

Measurement records carry deterministic definitions, units, explicit limits and formatted display values. Degrees use one decimal; sampled seconds three decimals; dimensionless and normalized distances/speeds two decimals; milliseconds integer precision. The writer sees the same compact evidence table and shared definitions on both providers. Raw measurements remain in the saved session, not as competing athlete values in the writer packet.

Assessments are computed before inference: consistent / inconsistent only for an applicable explicit retrieved drill standard, otherwise not assessed with the missing basis stated. Existing teaching narratives and research ranges are not numerical grading standards. The current real library has no applicable machine-readable numerical standards, so these saved sessions remain not assessed; no new passing thresholds were invented.

The deterministic response_plan selects non-coaching, concrete clarification, assumption, missing-data/general guidance, explanation, assessment or practice focus. External state stores scope, clarification options, previous packet fingerprint, cited evidence, recent replies and whether the assessment limit was explained. Same-scope follow-ups reuse retrieval; topic/rep/phase changes fetch fresh scoped evidence. Mixed-topic notes are filtered sentence by sentence; fleche retrieves only fleche material. A source sentence describing a user's chosen rubric is not silently applied to another athlete.

## What sentence checks catch and miss

They check numeric presence and display precision, named drills, lexical cue support and explicit priority/ordering terms. Unsupported sentences are removed independently; safe sentences survive. If nothing survives, one unused relevant source cue may be offered, or a short scoped gap and concrete next step. No extra model repair call is made. Sentence-buffered local streaming withholds incomplete/unverified claims and publishes cumulative safe text to the real app queue.

These checks cannot establish semantic truth: wrong body-part assignments, units outside the narrow physical-unit guard, unsupported qualitative verdicts, causal meaning or paraphrases with misleading word overlap may pass. A narrow unit guard catches personal m/s/W/N claims when that value+unit is absent from athlete measurements; a narrow assessment guard catches some explicit personal verdicts. Neither is comprehensive, as the manual counts demonstrate. Lexical checks also remove valid paraphrases and clarifications. Raw drafts and every removal remain in traces. A numeric pass is never full grounding.

## Provider and runtime

Gemini is paced six seconds per actual model request; one bounded 503 retry remains, with no 429 retry loop. Quota failure halts the evaluator and marks the chain incomplete. Runtime routing retains state/packet across fallback; the circuit honors retry-after headers and Google RetryInfo delays. 7B uses Q4_K_M, Vulkan on the integrated Intel Arc GPU, context 4096, generation cap 160 and a 20-second wall deadline, matching 3B settings. No billing was enabled. Credentials are read only from the ignored local .env/environment.

Gemini TTFT is unavailable in the synchronous provider path. Local TTFT is recorded independently of first verified visible sentence. Checking sentences introduces a deliberate first-visible delay; exposing raw tokens would leak claims later removed. Transport streaming and warm-model retention remain enabled.

## Manual review and live acceptance

See docs/next_phase_manual_review.md and docs/next_phase_live_transcripts.md. No automatic default promotion follows these metrics.

## Review files

- [Manual failures, acceptance result and next decisions](next_phase_manual_review.md)
- [37 live-app turns and forced-429 trace](next_phase_live_transcripts.md)
- [Runtime, TTFT and request accounting](next_phase_runtime_accounting.md)
- [Canonical packet example](next_phase_packet_example.json) and [exact writer input](next_phase_exact_writer_input.json)
- [baseline_gemini full transcripts](next_phase_baseline_gemini_transcripts.md)
- [baseline_3b full transcripts](next_phase_baseline_3b_transcripts.md)
- [baseline_gemini_holdout full transcripts](next_phase_baseline_gemini_holdout_transcripts.md)
- [baseline_3b_holdout full transcripts](next_phase_baseline_3b_holdout_transcripts.md)
- [gemini_original full transcripts](next_phase_gemini_original_transcripts.md)
- [qwen3b_original full transcripts](next_phase_qwen3b_original_transcripts.md)
- [qwen7b_original full transcripts](next_phase_qwen7b_original_transcripts.md)
- [gemini_holdout full transcripts](next_phase_gemini_holdout_transcripts.md)
- [qwen3b_holdout full transcripts](next_phase_qwen3b_holdout_transcripts.md)

Verification: 111 focused core, dialogue, persistence, provider and video-safeguard tests passed. Ruff/format, compile and scoped whitespace checks are recorded at completion. The Windows sandbox temporary-directory ACL issue required running persistence checks outside that sandbox; no test was deleted or weakened to bypass it. Legacy logs include expected invalid-answer/fallback test warnings and an existing telemetry-export shutdown warning.

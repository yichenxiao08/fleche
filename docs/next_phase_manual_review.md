# Checkpoint: infrastructure improved; conversational acceptance fails

The new core is not ready to become the default. The numeric and repetition improvements are real, but the sentence checker increases unhelpful declines and breaks some clarifications. Local models still invent quality judgments. COACH_CORE remains old; no commit or push.

## Measured before / after

The baseline is the complete 56-turn Gemini Layer 2 pass. Its code was recovered from this task's original patch journal; the recovered persona and every original pre-call packet matched all 56 baseline records before it was used on the holdout. These are genuine new baseline-code replays, not historical holdout conversations. See baseline_source/validation.json and provenance.json under evals/next_phase.

- Gemini original 13 chains: unmatched-number replies 2/56 → 0/56; consecutive repeated measured-value pairs 14/43 → 3/43. Annotated scope remains 31/31. Median/p95 excluding test pacing: 0.94/4.62 s → 0.87/3.56 s. This does not prove a conversational quality win.
- Gemini holdout: topic/rep checks 29/48 → 36/48; unmatched-number replies 7/48 → 0/48. However, declines without a partial answer increased from 2/48 to 8/48, and three new replies were bare questions. Median latency increased from 3.40 s to 4.04 s; p95 decreased from 7.04 s to 5.96 s. Cloud timing varies; no causal latency claim is made from one pass.
- Qwen 3B original: unmatched-number replies 5/56 → 0/56; manually confirmed unsupported judgments remain at least 6/56 (at least 8 in baseline). Its final coherent-chain median/p95 is 3.87/9.02 s. An initial pass had seven 20-second deadline failures; those are preserved separately, followed by one complete-chain recovery of H01–H03 after the runtime stabilized. The post-model-swap stall's exact cause was not isolated.
- Qwen 3B holdout: topic/rep checks 29/48 → 36/48; unmatched-number replies 4/48 → 0/48; declines without partial answers 1/48 → 9/48. At least two unsupported judgments survive. Median/p95: 2.25/4.87 s → 2.84/4.77 s.
- Qwen 7B Q4_K_M on the original 13 chains: 56/56 replies, no provider errors, median 7.18 s, p95 15.99 s, max 19.27 s, raw TTFT median 2.46 s. It retains at least ten unsupported judgments. Two replies reached the 160-token generation cap; increasing that cap would cost more latency and would not by itself fix the unsupported judgments. It misses the roughly 15-second p95 goal and fails quality; it was not advanced to a separate holdout. Both models used context 4096, generation cap 160, no thinking, warm retention and a 20-second deadline. Vulkan and the integrated GPU were verified. Idle 3B weights were initially reloaded by app startup, then unloaded for the remaining 7B test; no simultaneous 3B inference was intentionally benchmarked.

Repetition and refusal counts are transparent proxies, not full semantic scores. Manual verdict counts are confirmed minimums with turn references in manual_verdict_flags.json; the narrower automatic verdict regex missed important cases. Holdout automatic scope checks cover topic/rep selection; temporal phase errors below are additional failures.

## Fabrication and refusal together

Manual review of E12 T1–T5 found three baseline 3B fabricated requested quantities/drills (torso length/calibrated speed, measured power/force, and the absent drill), versus zero in the final 3B, 7B and Gemini answers. Gemini's baseline was already zero. This restricted bait result does not certify all causal advice or qualitative verdicts. Decline rates rose, as reported above; zero numeric flags after sentence removal is not independent proof of coaching quality.

## Concrete failures and causes

| Reference | What the reader will see | Likely underlying cause |
|---|---|---|
| Gemini H01 T1–T3 | Missing-data or grading declines replace the baseline's more useful general guidance. | Assessment-limit text and claim filtering dominate the response ladder. H01 is a regression; do not claim its narrow baseline acceptance still holds. |
| Gemini H08 T2–T3; H09 T2–T6; H10 T2–T4 | Repeated inability to judge, occasionally followed by broad library text rather than the requested judgment or next useful step. | No applicable explicit grading standard; merely telling the writer that the limitation was already explained does not reliably prevent repetition. |
| Gemini H03 T1 / H04 T1 | Recovery-definition contamination is removed from the arm source packet, but the fleche reply still opens with arm-angle/lunge context. | Retrieved sources are now movement-scoped, but user-history context can still influence the writer incorrectly. |
| Gemini E11 T4; S11 T1 | E11 repeats the previous values; S11 calls action-to-lunge time “reaction time.” | Numeric presence does not validate meaning. Added definitions do not guarantee the model follows them. |
| Gemini E11/S11 T5–T7 | Correct duration labels and less repeated numeric data, but mostly generic recovery definitions/advice. | Evidence memory helps the narrow repetition metric; useful conversational advancement is not yet reliable. Neither complete baseline nor new pass reproduced the earlier isolated onset/duration error. |
| Gemini U01 T1 / U03 T1 / U08 T3 | A valid clarification becomes a gap fallback or a bare question without options. | The coaching sentence checker runs on non-claim conversational text. Priority/advice words can trigger inappropriate filtering. This violates the ladder contract. |
| U03 T2–T4, both providers | “The second option” can select arm instead of recovery. | Candidate order follows topic-classifier order, not the order the user named the choices. |
| Gemini U04 T3–T4 | “Back to the finish” switches from front knee to torso. | Keyword scope resolver reads “back” as anatomy instead of a conversational return instruction. |
| Gemini U08 T2 | “Start over” still mentions the old arm action. | State resets, but the history bootstrap can reintroduce prior user turns. A reset needs a history boundary as well as cleared topic fields. |
| Gemini U03 T2 | Claims recovery measurements are absent throughout the session, although only the filtered packet lacks them. | The writer still sometimes ignores explicit availability scope. |
| Gemini U07 T3 / U06 T4 | “ok” or a greeting receives an unnecessary question. | Non-coaching route labels do not consistently control model behavior, and the checker does not guarantee that contract. |
| Qwen 3B H10 T1–T4 | “Looks good,” “conventional range,” “no immediate changes.” | The model invents a verdict despite not-assessed objects; narrow lexical guards miss wording variations. |
| Qwen 3B H09 T1–T2 | Recommends a forward lean and treats projected finish measurements as whole-action posture. | Wrong meaning, scope and causal interpretation remain beyond numeric checking. |
| Qwen 3B U04 T1 | Calls a negative knee/toe offset “ahead” and grades it as acceptable. | A correct numeric elbow/knee value can coexist with reversed spatial meaning and an invented standard. |
| Qwen 7B H07 T2–T3; H09 T1; H10 T2–T3; E11 T3; S11 T3–T5 | Unsupported best-rep rankings, typical/reasonable ranges, stability and good-form judgments. | More parameters do not solve adherence to evidence semantics. See the minimum-count references for the complete reviewed list. |

The finite 24-row packet cap and multi-topic resolution can also leave partial coverage that the writer reads as a full-session range. The next packet design needs explicit selection coverage and deterministic summary ranges, not more free-form interpretation of a truncated table.

## Live-app result

Ten real scripted multi-turn conversations ran through the normal HTTP coaching queue on copies of saved sessions: 37 turns, 35 Gemini and two actual local replies. Gemini HTTP median/p95 was 2.14/5.42 s. The two local fallback replies had 5.07 s median HTTP latency, 1.89 s median raw TTFT and 4.17 s first verified visible text. Two local samples are not a robust latency benchmark.

L10 providers were Gemini → Gemini → local (forced 429) → local (cooldown) → Gemini (re-probe). Arm/rep 2 survived T3; recovery/rep 2 survived T4. The state check passes. The fallback reply at T3 still declines instead of describing rep 2, so this is not a coaching acceptance pass. L01 T2 and L07 expose the same assessment/clarification problems in the running app. Read the full bad turns in next_phase_live_transcripts.md.

The first acceptance launcher attempt was invalid because package import created the original repository before isolation settings. It is archived separately; its only added test sessions/job were removed from the main database after ID/title/no-run checks. The corrected launcher sets process environment before import and asserts the separate repository path. No production dispatch change was made on the basis of that initial, incorrect diagnosis.

## What remains before approval

1. Make claim checks respect response type: clarification, acknowledgment and reset are conversational acts, not technique claims. Preserve useful clauses and avoid orphaned fragments after removal.
2. Replace brittle uncertain scope handling with a provider-independent semantic fallback, ordered clarification candidates and a real reset history boundary. Keep deterministic fast paths; avoid adding body-part-specific exceptions.
3. Make packet coverage and supported qualitative assessment bases explicit; do not create numerical thresholds merely to force a positive verdict. Current real entries do not provide applicable machine-readable grading standards, so supported consistent/inconsistent verdicts were tested only with clearly synthetic unit-test criteria, not demonstrated on real clips.
4. Re-evaluate on a fresh unseen holdout after those fixes. This holdout is now diagnostic; it must not be relabeled unseen after tuning.
5. Keep local Qwen as an experimental offline option. A free hosted fallback such as Groq's free-plan gpt-oss-20b is a candidate for evaluation, not a proven replacement. It requires a separate key and the same tests. [Official free-plan limits](https://console.groq.com/docs/rate-limits) and [compatible endpoint documentation](https://console.groq.com/docs/openai) were checked on October 14. No paid account or billing was enabled.

Gemini quota is not currently blocking evaluation. No quota-exhaustion loop was used. The remaining blockers are acceptance failures, the missing applicable grading basis and the lack of a validated fallback—not a request to pay for Gemini. All prototype code remains behind the existing opt-in flag. Stop here for user review; do not commit, push, or promote the default.

All scripted provider runs are finished. The task-only acceptance server and isolated comparison runtime were stopped after saving results. The original app and 3B server were left running. Exact writer input, source snapshots, runtime/request accounting and credential-scan results are linked from coach_next_phase_results.md.

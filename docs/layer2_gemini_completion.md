# Layer 2 Gemini completion — 2026-10-14

Completed the earlier Layer 2 validation only. No next-phase packet assessments, response ladder, Layer 5 or new fallback model were built. COACH_CORE remains old. No commit or push.

All 13 frozen sequences / 56 original user turns completed with the newly supplied project key. Each chain carries its actual preceding answers, unlike the earlier isolated error replays. H01 was completed as the initial probe; the same resumable run supplied the other chains. The process survived the earlier cancellation; it was discovered still running, so no duplicate evaluation process was launched. Every saved turn was reused. Earlier runs remain intact.

| Run | Replies | Provider errors | Median / p95 excluding eval pacing | Replies with unmatched numbers | Unmatched / mentions | Tool turns |
|---|---:|---:|---:|---:|---:|---:|
| Gemini V3 | 47/56 | 9 | 1.54s / 8.06s | 3/47 | 3/101 | 40 |
| Gemini initial Layer 2 | 24/56 | 32 | 1.08s / 5.45s | 1/24 | 4/44 | 1 |
| Gemini complete paced Layer 2 | 56/56 | 0 | 0.94s / 4.62s | 2/56 | 2/163 | 1 |
| Qwen Layer 2 (preserved) | 56/56 | 0 | 4.22s / 9.54s | 5/56 | 7/48 | 0 |

Annotated scope expectations: 31/31 on the actual Gemini packets. This is annotated scope coverage, not full semantic answer accuracy. All 56 input questions match the frozen set exactly.

Request accounting: 57 actual Gemini model attempts for 56 answers; 1 optional evidence-tool calls. Token usage: 88772 input / 4037 output. No completed turns were deliberately replayed and no additional probe was made. Requests were spaced at least six seconds apart by the existing evaluation scheduler. Billing was not independently inspected; this run uses the user's stated free-project key, and no billing setup was performed.

Latency subtracts recorded evaluation-only pacing, retaining inference, packet work and any provider retry/backoff. The raw paced latency and pacing time remain in each transcript and JSON. Gemini does not expose streaming TTFT in this path; it is unavailable, not zero. The Qwen row reuses the previous complete run; it was not rerun because no Qwen code changed during this check.

## Manual review of remaining failures

| Turns | Finding | Implication |
|---|---|---|
| H01 T1–T3 | Stays on knees/legs, back, and speed; labels general guidance and acknowledges unavailable tracking without inventing athlete measurements. | Narrow H01 acceptance holds; some advice still exceeds the retrieved wording. |
| H03 T1 | Opens with a definition of recovery although the question asks about arm angles. | Scope/history or retrieval contamination still reaches the reply. |
| H04 T1–T3 | Starts the fleche answer with lunge guidance; later supplies crossing and run-through instructions beyond the retrieved material. | Numeric matching does not establish support for technique advice. |
| H07 T4–T5 | Correct torso packet survives 'during the drill'; descriptions still blur torso tilt and pitch-change meanings. | The resolver fix works, but measurement semantics remain weak. |
| H08 T2–T3; H09 T2–T6 | Keeps the requested subject but repeatedly declines to assess good/bad or straighter/bent. | Continuity alone does not produce useful coaching judgments. |
| H10 T2–T4 | 'Good or bad' becomes varied measurements plus general instruction; later repeats unsupported 18.1 degrees (packet: 18.153, normally 18.2 to one decimal). Priority claims are not established by the packet. | Two numeric-tracing failures plus unsupported semantic advice. |
| E11/S11 T5–T7 | Correctly presents 0.1 seconds as active recovery time, not an onset timestamp; keeps rep 2. Repeats the same values and similar general advice across follow-ups. | Earlier onset confusion was not reproduced in this pass; conversation remains repetitive. |
| E12 T1–T5 | Does not claim measured blade stability, calibrated speed, force or the absent named drill. T5 only says the drill is absent, without a useful alternative. | Manual bait review: 0/5 invent the requested measurement or drill. This does not certify all general causal advice. |

Number tracing checks presence and ordinary rounding only. It does not prove the correct metric, phase, rep, unit, causality, drill identity or a justified verdict. This availability-complete pass is not an overall coaching-quality acceptance or live-app acceptance. The separately supplied next-phase task remains unstarted.

Full answers and per-turn latency: [layer2_gemini_completion_transcripts.md](layer2_gemini_completion_transcripts.md). Raw packets, inputs, provider attempts and traces: evals/layer2/gemini_new_project/.

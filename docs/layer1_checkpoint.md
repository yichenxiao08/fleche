# Layer 1 checkpoint — not ready to become the default

The LLM-first baseline still does not feel reliably conversational. Gemini sustains some short follow-ups; Qwen 2.5 3B stalls, invents targets and drifts. Neither passes a grounding or conversation gate. COACH_CORE remains old; new is opt-in. No Layer 2, commit, push or production restart.

Evidence: 10 historical failure episodes / 34 original turns from four identifiable saved chat streams, not ten independent chats. The principal trial replays them on both providers plus two labeled evaluation chains: 24 conversations. Two early four-turn arm probes and two final seven-turn briefing smoke chains are separately retained: 28 conversations / 120 attempted turns total, no 30-conversation old/new comparison.

Architecture: cached briefing and ten recent messages every turn; two optional evidence/BM25 tool calls. No dialogue state machine, question router, selector, canned answer, claim checker or repair loop. Missing retrieval never gates a reply. Existing provider access, video/tracking/athlete abstention, phase/reference safeguards and old-core claim checks remain intact. New-core prose is unchecked at this authorized stage.

## Measured provider behavior

| Principal trial | Replies / attempted turns | Provider errors | Reply median / p95 | Turns using tools |
|---|---:|---:|---:|---:|
| gemini | 39 / 49 | 10 | 6.61s / 17.6s | 25 |
| local | 49 / 49 | 0 | 6.36s / 20.49s | 6 |

Pinned models: gemini-3.5-flash-lite and qwen2.5:3b. Gemini failures are HTTP 503 high demand, retained without substitution. Mean reply latency: Gemini 6.55s, Qwen 11.45s. Qwen E12-T1/T5 took 99.40s/90.36s, exceeding the existing queued-worker 90s deadline; direct coach calls completed, but queued responsiveness is unproven. Times measure completion, not streaming first tokens.

## Candid transcript review

These are examples from manual review, not exhaustive scored counts:

- **False no-data/refusal:** H07-gemini-T5 requests `torso_lean`, although saved evidence is named `projected_torso_tilt`; H08-gemini-T3 denies available rear-leg angles. H08-local-T1/T3 and H10-local-T3 similarly deny data. Legitimate item-specific missing-data answers are different: E12-gemini-T2/T3/T4 correctly withhold blade stability, m/s and force while sharing timing/joint evidence; T5 withholds the absent named drill.
- **Lost topic or rep:** H10-gemini-T3/T4 slides from the arm chain into front-knee interpretation. E11-local-T3 asks permission to inspect the second rep, T5 gives first-rep recovery, and T7 assigns rep 1's 160-degree elbow to rep 2. H07-local-T3 turns the set-level arm question into another first-rep monologue.
- **Robotic replies:** H03-gemini-T1/T2 nearly repeat the same general answer. H10-local-T2/T4 repeatedly closes with an offer for more questions. E11-local-T3 through T7 describes what it would retrieve and asks permission instead of doing it. H04-local-T1 and H07-local-T2/T3 trail off at the existing local generation cap.
- **Unsupported interpretation/fabrication:** H01-local-T1 invents 140/160-degree knees despite rejected measurements. H09-local-T2/T3 invents an optimal 3–4-degree torso target. H10-local-T2/T4 invents a 0.7–0.8 good-extension range. E11-gemini-T2 calls the session clean, energetic and responsive without support; E12-gemini-T1 calls a reach-at-onset sample extension timing. Correct numbers do not make these interpretations grounded.
- **Some conversational successes:** H02-gemini-T3/T4 answers which arm, rather than repeating the old sideways instruction. H03-gemini answers the general angle question despite missing tracking. E11-gemini-T5 carries the second rep into recovery. The early H10-initial-probe-gemini-T3 also carries the arm topic into rep 2.

## Briefing corrections and scope of validation

Early probes used the first raw arm value; the principal trial selects the declared weapon arm. Final corrections list exact feature names and define reach ratio as shoulder-to-wrist distance / (upper-arm + forearm length), matching motion.py and pose_measurements.md. All transcripts retain their actual prompts. The principal trial predates the final two corrections; only S11 validates that revision.

Final briefings measure 322–477 tokens across the four contexts. They show front-knee geometry and mark missing feet separation; no depth distance is invented. S11 remains bad: Gemini T2/T4 adds unsupported causal explanations and T5 applies corrected-reference recovery as a current cue. Qwen T6/T7 invents a 130–150-degree expected knee range, misattributes rep 1's value to rep 2 and infers smoothness from timing.
Final S11 gemini: 6/7 replies, 1 errors; median 9.82s, p95 10.15s.
Final S11 local: 7/7 replies, 0 errors; median 8.8s, p95 12.98s.

## Verification and next decision

Five Layer 1 contract tests, seven natural-dialogue tests, 27 verified/router tests and four video-quality tests pass; scoped Ruff/format and whitespace checks pass. Full suite: 245 tests, four existing clarification errors and one prior-draft evaluator failure. Sandbox temp-directory errors were separated by an unsandboxed rerun. Old-draft tests were not rewritten.

Review docs/layer1_transcripts.md, especially H10, E11, E12 and S11. Keep the default old: Gemini offers better context use but service errors and grounding overreach; Qwen is less reliable and has longer latency tails. No model, answer policy or review/routing layer was changed. Stop here pending continue or specific feedback.

Automation configuration: GPT-6.1 Sol/high. Final quota check: 83% five-hour and 46% weekly remaining; the 40% five-hour boundary was not reached. The active turn cannot change its own model/effort through the available tools; no medium continuation is needed because Layer 1 is complete and work stops at this checkpoint. Runtime model identity is not separately exposed by the usage API.

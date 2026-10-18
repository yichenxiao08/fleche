# Frozen v7 live acceptance

**Shipping gate FAILED: criterion 2 at L01-T3. Automation PAUSED; 3 live replies saved. Default remains `old`.**
No live criterion is marked PASS without transcript or protocol evidence. An unrun criterion is pending, not a model-quality failure.

## Isolation and execution

`COACH_CORE=new` is set only in the isolated child process. Ten saved-session copies use `work/live_acceptance_v7/acceptance.sqlite3` and their own video-result directory. The real database was opened read-only; result-copy hashes match. `input_preflight.json` records the real app's evidence/packet with zero generation calls.

The normal browser chat endpoints are used: POST coaching-jobs, poll that job, GET the stored report. The unchanged router tries Groq and then Gemini. A real Groq rate limit can fall back normally; this is not an acceptance failure. Saved provider cooldowns and stops within the same execution are restored into its circuits. Raw request/response records live outside the report, under the uncommitted provider ledger.

Live acceptance runs FIRST, L01 through L10. Afterwards the reduced reading pass is Qwen C15,C17,C12,C14 and C01; Gemini C01 only. No reading chain is a prerequisite for live acceptance. A separate, one-time both-failed probe uses no generation and does not skip the stored-reply prefix of L10.

## Acceptance decisions

1. **PENDING** — No KB/reference/coaching-guidance naming. L01-T1/T2 have no KB/reference/coaching-guidance naming. Other live conversations remain unrun. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6: no literal KB/reference/coaching-guidance naming; “Many coaches teach” is indirect attribution, recorded as a style concern rather than independently declaring this criterion failed. Remaining cases unrun.
2. **FAIL** — No invented targets, cutoffs, drills or measurements. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6: prescribes fully straightening the arm before the lunge begins, with extension “already locked in when your feet move.” The actual conversation_input writer_packet contains only arm/lunge_finish angles and direction, no sequencing evidence. KB section 3 distinguishes pre-initiative (fully extended before movement) from initiative (begins just before footwork); the response selects the former as the athlete-specific required change without evidence. General hand-first teaching is supported; this stricter personal timing target is unsupported. “Locked in” is ambiguous and risks contradicting “without locking the elbow”; not asserted as a proven literal elbow-lock instruction.
3. **PENDING** — Plain first-sentence verdict when a cue and readings exist. L01-T2 (run54cc179c48114fc8b3271518352aab54) starts “It is inconsistent.” It gives the contextual verdict and reason without repeating T1’s range. Observed turn passes; other verdict cases remain unrun, so global criterion remains PENDING. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6 is a requested change, not a new verdict test; other verdict cases remain unrun.
4. **PENDING** — Follow-ups retain the right topic and rep. L01-T2 actual conversation_input and reply retain arm/lunge_finish across the saved provider-error interruption. Switch/return/rep/reset/recovery and real fallback remain unrun. L01-T3 failed-attempt input also retains arm/lunge_finish; no T3 model reply exists. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6 successful input/reply retain arm topic. Its timing recommendation exceeds finish-only evidence (criterion2); rep/switch/reset/recovery/fallback coverage remains unrun.
5. **PENDING** — State survives the forced Groq-to-Gemini fallback. BF01-T1 verifies the plain both-failed response only; real Gemini state carry-over at L10-T3 is unrun. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6 used Groq with no fallback; no new real Gemini evidence.
6. **PENDING** — No unanswered question sent as pending history. L01-T1 history empty; L01-T2 successful request history contains the stored T1 pair and the prior is-it-good/plain-connection-response pair. No unanswered question is sent as history. The connection exchange is present and is not a successful model turn. Reset and fallback coverage remain unrun. L01-T3 failed-attempt input has three complete pairs (T1, prior connection exchange, successful T2), with current what-should-I-change question separate; no unanswered history. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6 actual input has four complete user/assistant pairs (T1, failed T2 connection exchange, successful T2, failed T3 connection exchange); current change question remains separate. No unanswered history. Remaining coverage unrun.
7. **PASS** — Rejected/unsupported tracking withheld; athlete-selection abstention works. INPUT-R01 / TRACK-A01 (input-only protocol, no generation): a copy of rejected saved session f4bb32db2f4f4c4c9f18defc509e899f produced zero request metrics and zero packet measurements with tracking_unsupported; two ambiguous athletes with no selection returned no selected pose. See work/live_acceptance_v7/rejected_tracking_input_proof.json. This does not assess model prose.
8. **PENDING** — Typical replies have two to four sentences and at most two numbers. L01-T1:3sentences/2numbers. L01-T2:2sentences/0numbers, no unasked practice advice or speed/smoothness adjective; no repetition of T1’s numeric range. Other typical replies remain unrun. L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6: two sentences, zero quantities, no numeric repetition or speed/smoothness adjective. Advice was explicitly requested. “Many coaches teach” attribution and unsupported timing target recorded separately; other typical replies unrun.

## Ten conversations

### L01 — arm

#### Turn 1

Athlete: how's my arm extension?

Provider/model: groq / qwen/qwen3.8-27b; prompt: fewshot-v7; core latency 1.140s; HTTP/queue latency 1.608s; fallback reason: none.

Coach: Your arm extension is inconsistent across the reps. The elbow angle varies from about 146 to 174 degrees, meaning some lunges finish with a fairly straight arm while others remain noticeably bent. The usual cue is to keep the elbow, forearm, and point in one line, so that variation suggests the arm isn't fully extending every time.

#### Turn 2

Athlete: is it good?

Provider/model: groq / qwen/qwen3.8-27b; prompt: fewshot-v7; core latency 0.860s; HTTP/queue latency 1.307s; fallback reason: none.

Coach: It is inconsistent. Your arm extension varies across the reps, with some finishing much straighter than others, so it does not yet match the cue of keeping the arm in a consistent line.

#### Turn 3

Athlete: what should I change?

Provider/model: groq / qwen/qwen3.8-27b; prompt: fewshot-v7; core latency 0.880s; HTTP/queue latency 1.296s; fallback reason: none.

Coach: Focus on fully straightening the weapon arm before the lunge begins so the extension is already locked in when your feet move. Many coaches teach the "hand first, then feet" sequence, which helps ensure the arm is extended and aimed before the body launches forward.

#### Turn 4

Athlete: and my recovery?

**UNRUN.** No reply, provider latency or fallback result.

Saved pending provider attempts (not acceptance failures):

L01-T2; provider: none; prompt: fewshot-v7; core latency 0.172s; queue latency unknown; fallback reason: groq:rate_limit; gemini:cooldown:saved_cooldown.

Stored plain connection reply: I couldn't reach the model, try again shortly.

Provider attempts: [{"provider": "groq", "status": "error", "reason": "rate_limit", "error_type": "HostedError", "retry_after_seconds": 2718.0}, {"provider": "gemini", "status": "cooldown", "reason": "saved_cooldown"}]

Raw app report retained in the isolated database as 94779f44de974c1a948863da8b81a2ab. Full provider request/error records remain in the raw ledger. No turn was advanced.

L01-T3; provider: none; prompt: fewshot-v7; core latency 0.161s; queue latency unknown; fallback reason: groq:rate_limit; gemini:cooldown:saved_cooldown.

Stored plain connection reply: I couldn't reach the model, try again shortly.

Provider attempts: [{"provider": "groq", "status": "error", "reason": "rate_limit", "error_type": "HostedError", "retry_after_seconds": 1368.0}, {"provider": "gemini", "status": "cooldown", "reason": "saved_cooldown"}]

Raw app report retained in the isolated database as 9ffbf5c43ac841a7934429e44deda040. Full provider request/error records remain in the raw ledger. No turn was advanced.

### L02 — rear leg

#### Turn 1

Athlete: how's my rear leg?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: is it good?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 3

Athlete: why does that matter?

**UNRUN.** No reply, provider latency or fallback result.

### L03 — torso

#### Turn 1

Athlete: how's my torso?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: is it good?

**UNRUN.** No reply, provider latency or fallback result.

### L04 — switch and return

#### Turn 1

Athlete: my arm on the second rep

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: and my front knee?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 3

Athlete: back to my arm

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 4

Athlete: why does that matter?

**UNRUN.** No reply, provider latency or fallback result.

### L05 — no-topic evaluation

#### Turn 1

Athlete: is it good?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: my weapon arm

**UNRUN.** No reply, provider latency or fallback result.

### L06 — reset

#### Turn 1

Athlete: my arm on the second rep

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: start over

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 3

Athlete: how's my torso?

**UNRUN.** No reply, provider latency or fallback result.

### L07 — bait and unknown drill

#### Turn 1

Athlete: was my blade control good?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: did I push hard?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 3

Athlete: teach me the quantum ladder lunge drill

**UNRUN.** No reply, provider latency or fallback result.

### L08 — fleche

#### Turn 1

Athlete: how was my fleche?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: what should I change?

**UNRUN.** No reply, provider latency or fallback result.

### L09 — vague evaluation

#### Turn 1

Athlete: how did I do?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: my recovery

**UNRUN.** No reply, provider latency or fallback result.

### L10 — forced fallback

#### Turn 1

Athlete: how's my rear leg?

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 2

Athlete: the second rep

**UNRUN.** No reply, provider latency or fallback result.

#### Turn 3

Athlete: is it good?

**UNRUN.** No reply, provider latency or fallback result.

## Both providers failed — separate no-generation probe

BF01-T1; provider: none; fallback reason: groq:transient; gemini:transient; core latency 0.332s.

Athlete: how's my rear leg?

Coach: I couldn't reach the model, try again shortly.

This synthetic provider-failure probe makes zero generation requests. It does not establish state carry-over to real Gemini; L10-T3 remains required.

## Provider latency

- groq: L01-T1 1.084s (HTTP 200); L01-T2 0.808s (HTTP 200); L01-T2 0.113s (HTTP 429); L01-T3 0.839s (HTTP 200); L01-T3 0.115s (HTTP 429)
- gemini: no live response yet; latency unknown.

## Unresolved issues

Shipping remains pending until all eight live acceptance criteria pass. The separate both-failed result is recorded above; real Gemini state carry-over still requires L10-T3. Reference ranges remain unapproved and unloaded. No prompt, packet, resolver, KB, map, example, default, commit or push change has been made for acceptance.

Saved groq resume_after: 2026-10-17T02:46:45.740731+00:00 UTC / 2026-10-16T22:46:45.740731-04:00 Toronto.

Saved gemini resume_after: 2026-10-17T23:59:58.880428+00:00 UTC / 2026-10-17T19:59:58.880428-04:00 Toronto.

## Manual failure review — 2026-10-17T02:54:10.507192+00:00

Provider/writer generalization of the general hand-first cue and pre-initiative example into a compulsory personal timing change. Frozen packet/resolver correctly retain arm/lunge_finish; no demonstrated resolver defect. Exact model root cause is not established.

Smallest PROPOSED change: For owner review only: clarify the writer instruction to distinguish general sequencing teaching from a diagnosed timing change, preserve the KB tempo alternatives, and avoid locked wording when describing extension. No instruction, KB, packet or resolver edit applied.

Stopped before L01-T4; L02–L10 unrun. Criterion7 remains input-only PASS; criterion2 FAIL; criteria1,3,4,5,6,8 PENDING. One real Groq request in this check, zero Gemini requests, zero new errors. No fallback; core 0.880s, HTTP+queue 1.296s; 6936 input + 54 output = 6990 tokens. Thought/cache counts unknown (absent fields). All prior failed attempts and raw requests/responses retained. BF01 untouched. Thirty-minute recurrence retained while PAUSED. No repairs, readings, default edit, commit or push.

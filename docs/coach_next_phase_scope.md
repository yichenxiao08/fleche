# Flèche coach core: next phase (Layer 2 checkpoint approved with scope changes)

## Status and decisions
Your Layer 2 + evidence-packet checkpoint is approved as infrastructure.
Keep COACH_CORE=old. Do not commit or push. Do not flip any default.
Do not build separate Layer 3 or Layer 4 stages; their remaining gaps are
folded into the work below.

What your results established (do not re-litigate):
- Deterministic scope resolution works (62/62 offline) and removes most
  topic/rep carry-over failures.
- Explicit availability status and withholding rejected data work.
- Qwen runtime is fixed (median 4.22 s, p95 9.54 s, no timeouts).
- Gemini handles bait and the H01 acceptance case well.
- Qwen 2.5 3B cannot meet the grounding bar even with a clean packet and
  tight prompt (invented torso length, speed, wattage, and a drill).
  Stop prompt iteration; fix this structurally.
- Remaining Gemini errors are semantic (recovery duration read as onset
  time; one filtered packet read as "no arm/torso data in the session";
  "is it good?" answered by repeating angles). Number matching cannot
  catch these.
- Number-tracing validates presence, not meaning.

## Work, in this order. Report after each item briefly, but only STOP at
## the checkpoint at the end.

### 1. Meaning in the packet and assessment objects
- For every measurement in the athlete packet, add a deterministic
  definition, unit, and a "what this does not indicate" note (e.g. recovery
  duration is the time from peak lunge to back-foot return, not an onset
  time; arm direction is not elbow bend).
- Add a per-topic assessment object computed in code: status
  (consistent / inconsistent / not assessed), the library cue or standard
  it is based on, and the measured value used. If no library standard
  exists, status is "not assessed", and the reply states what was measured
  and what would be needed to judge it. The model phrases the verdict; it
  never invents one.
- Make availability scope explicit: "no measurements in this packet for X"
  must never be readable as "the whole session lacks X". Include the
  packet's scope (which topic/rep/phase it covers) in the text the model
  sees.
- Acceptance cases: H10 arm chain ("is it good?"), E11/S11 recovery chain,
  H08 filtered-packet case, H01 knees/back/speed.

### 2. Ambiguity handling in code (response ladder)
- Clarification options: when resolver confidence is low and two or three
  candidate readings exist, emit those options into the state and packet,
  so the writer can ask one question with concrete choices. Never a bare
  "please clarify."
- Assumption notes: when the resolver picks a topic at moderate
  confidence, add an explicit assumption note to the packet so the reply
  can say it ("assuming you mean your arm extension"). Test for it.
- The ladder, in order: answer from packet/evidence; if ambiguous, answer
  the likeliest reading and state the assumption; if still unclear, ask
  one question with 2-3 concrete options; if one specific item has no
  data, say so for that item and share what is known and what footage or
  measurement would answer it; general advice (labeled) only if nothing
  else exists.
- Non-coaching turn types as explicit routes: thanks/ok, "what can you tell
  me about this session?" (summarize the briefing), "start over", and
  greetings. These get short natural replies and do not trigger evidence
  topics or clarification questions.
- Topic-switch handling in both directions, including switching back to
  an earlier topic: the new topic replaces the old one in state instead of
  inheriting it.
- Reuse the previous packet when scope is unchanged ("why does that
  matter?"), so follow-up answers stay consistent with what was just cited.

### 3. Minimal Layer 5 (claim-level, after the reply is conversational)
- Deterministic checks on checkable parts only: numbers against the
  packet; named drills and cues against the library.
- On failure, remove or soften only the failing sentence. Never replace
  the whole reply with canned text. Never convert a failure into a blanket
  refusal. If nothing usable remains, give a short in-voice message naming
  what is missing plus one concrete next step.
- Acceptance: the Qwen E12 invented values (0.65 m torso length,
  1.37 m/s, 100 W, "Dragonfly" drill) are caught and removed while the
  rest of the reply survives. Report fabrication and refusal rates
  together; improving one must not silently worsen the other.
- Be explicit in docs about what Layer 5 cannot catch (semantic and causal
  claims) so it is not mistaken for full grounding.

### 4. Provider routing and fallback model
- Gemini default. On rate limits (429/RESOURCE_EXHAUSTED), timeouts,
  and transient failures, fall back. Add a circuit breaker with cooldown
  that respects retry-after, then re-probe Gemini. Log provider and
  fallback reason. If both providers are unavailable, return a clear,
  honest message instead of stalling.
- Test one local 7-8B model (Q4) alongside Qwen 2.5 3B on the same 13
  sequences. Report per-turn latency, unmatched numbers, fabrication on
  E12, and verdict-without-basis counts. If the hardware cannot run it
  with p95 under about 15 s, say so and propose an alternative fallback
  provider (e.g. a hosted small model through an OpenAI-compatible
  gateway), keeping Qwen as the offline-only option.
- State, router, packet, and Layer 5 checks stay identical across
  providers; only prompt length/format may differ.
- Tune on Gemini first, then verify the fallback with the same checks.

### 5. Evaluation
- Holdout: write 10-15 new multi-turn conversations the resolver and
  prompt have not seen, built from saved sessions with no invented
  measurements. Include the ladder cases: ambiguous follow-up, vague
  question ("how did I do?"), item with no data, topic with library
  guidance but no measurements, nothing available at all, plus
  non-coaching turns and topic switches both ways. Report resolver scope
  accuracy and answer quality on the holdout separately from the original
  13. Do not tune on the holdout.
- Metrics per provider, reported together: scope accuracy, number
  matches, fabrication on bait (target 0), verdict-without-basis count,
  and a refusal/deflection breakdown (declines without a partial answer,
  bare questions, questions with concrete options, useful partial
  answers).
- Gemini baseline is the complete Layer 2 pass: 56/56 replies, 0 errors, median 0.94 s, p95 4.62 s. Re-run Gemini chains on the new work in complete paced passes, comparing against that baseline. Never retry in a loop. Keep credentials exclusively in environment variables or ignored .env.
- Keep provider errors separate from quality metrics, as before.
- Keep failures visible in transcripts; do not overwrite earlier
  results.

### 6. Live check on the running app (not direct function calls)
- Run at least 10 real multi-turn conversations through the running app
  on saved sessions, covering: the arm-extension chain, rep references,
  an ambiguous question, a vague question, a no-data item, a bait
  question, a topic switch, and a non-coaching turn.
- Include a forced Gemini 429 between turns 2 and 3 of a chain and
  confirm state carries over to the fallback and the reply stays on
  topic.
- Save full transcripts with provider and latency per turn.

## Checkpoint: STOP here and wait for my review
Deliver:
1. docs with the final packet format (definitions, assessment objects,
   scope text), the exact writer prompt, and the ladder behavior.
2. Before/after table per provider on the original 13 and on the holdout,
   with all metrics above, plus the 7-8B model comparison.
3. Live-app transcripts (item 6), with your honest assessment of whether
   they read as natural conversations, including the bad turns.
4. What Layer 5 catches and what it cannot.
5. Remaining failure modes and what is blocked by quota.
Do not flip COACH_CORE, commit, or push until I approve.

## Working rules
- Prefer deterministic code for scope, state, packet building, ladder
  decisions, and claim checks; use the LLM for phrasing over the small
  curated packet.
- Never weaken existing safeguards: athlete-selection abstention,
  unsupported-claim checks, camera-context naming.
- Never hardcode answers to test conversations; never invent
  measurements in fixtures.
- Do not claim improvements the numbers do not show. If a metric got
  worse, say so and explain the tradeoff.
- If requirements conflict (latency vs. grounding, fallback model quality
  vs. speed), state the tradeoff and propose a choice instead of silently
  picking one.
- Keep changes scoped; no unrelated refactors.
## Baseline-driven amendments (2026-10-14)

- State consistent/inconsistent verdicts plainly with their source cue; not-assessed gets one observation-plus-needed-evidence sentence, then advance on follow-ups.
- Record values/advice already given; measure consecutive value/advice repetition.
- Filter retrieval by resolved topic and movement; regression tests cover arm/recovery and fleche/lunge contamination.
- Sentence checks trace named cues/drills and priority/ordering claims to retrieved text; remove unsupported claims individually.
- Pre-format athlete values at natural precision before writing (degrees one decimal; sampled seconds three decimals).

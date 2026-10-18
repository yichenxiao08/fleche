# Current status — owner-approved v7.1

Approved persona/reminder and connection-history fix implemented. Fresh L01-T1 is pending after one Groq429; no successful v7.1 replies yet. Automation ACTIVE every30minutes, actual cooldowns honored. Gate closed/defaultold; no commit/push. Original v7 FAIL/transcripts retained in live_acceptance_v7_archive.md. Current instructions: coach_fewshot_v7_1_request.txt. Detailed v7.1 preparation and tests appear at the end of this file.

---

# Frozen fewshot-v7 — live acceptance first

The owner's reorder supersedes the reading-first shipping plan. [Latest instructions](../evals/conversational_kb/model_review/fewshot-v7/shipping_live_first_request.txt) and [live acceptance](live_acceptance.md).

Run L01 through L10 first, through the isolated app's normal queued chat path. COACH_CORE=new exists only in the child process, with copied sessions and separate storage. Groq Qwen is first; normal Gemini fallback after a Groq quota error is authorized and is not a quality failure. Each turn records its actual provider, fallback reason and latency. A provider stops on its first error for the entire execution; a later execution must still honor actual resume_after/Retry-After. Completed stored replies are never regenerated. All frozen source manifests match; prompt, packet, resolver, KB, map and examples remain untouched. Reference ranges stay unapproved and unloaded.

## Current evidence

- L01-T1/T2 saved on Groq qwen/qwen3.8-27b; no fallback. T1:1.140s core/1.608s HTTP+queue,6724input+73output. T2:0.860s core/1.307s HTTP+queue,6848input+39output; plain inconsistent verdict without repeating T1’s range. L01-T3 then hit real429 and remains pending; Gemini skipped its actual cooldown, zero Gemini calls. L01-T4 and L02–L10 remain unrun; other live criteria stay PENDING. There is no reading prerequisite.
- BF01-T1: separate both-providers-failed check completed once, with zero generation requests. Exact reply: “I couldn't reach the model, try again shortly.” Both synthetic503s are labeled reached_provider:false. Core0.332s, HTTP+queue0.755s. It does not establish real Gemini state carry-over; L10-T3 still must do that.
- INPUT-R01 / TRACK-A01: rejected saved-session copy yields zero metrics and zero packet measurements, tracking_unsupported; ambiguous athlete selection abstains. Criterion7 has input-only protocol PASS evidence, not generated quality evidence. Other live criteria remain PENDING until observed.

Saved actual provider cooldowns before the next request: Qwen October17 02:46:45.740731UTC / October16 22:46:45.740731Toronto; Gemini October17 23:59:58.880428UTC / 19:59:58.880428Toronto. The test process restores these into the normal router circuits. An available Gemini can answer while Groq cools. No actual limit was bypassed or probed early.

## Reduced readings — only after live acceptance

Qwen: C15,C17,C12,C14, plus C01. Gemini: C01 only. Qwen has its one existing v7 C01-T1 reply (retained), so active totals are1/20 Qwen and0/4 Gemini. C01-T2 must be read for repeated numbers from T1. C03,C13,C19 are dropped from active v7 scope; all prior artifacts and unrun plan rows stay preserved outside scope. There are no new reading requests in the reorder preparation.

Use scripts/run_fewshot_v7_ship_review.py, with the frozen underlying runner/manifests intact. The scope is recorded separately in shipping_scope_live_first.json. Append only newly saved replies to the rating sheet, leaving owner ratings blank and exact v6/earlier archives intact. Full raw per-model transcripts show failed/unrun turns and actual token/latency/cache fields without quality ratings or metrics tables.

## Acceptance and shipping

The30-minute automation now prioritizes live acceptance. Each invocation submits at most one pending turn for manual reading; reuse one run-id across the entire scheduled check so provider stops survive separate child processes. L05 requires an actually offered topic choice. L10 forces Groq between its second and third real turns; the separate completed BF01 probe is not regenerated.

Manually update all eight criteria with exact turn/protocol evidence. Unrun criteria are pending. If any criterion fails, record its turns, probable prompt/packet/resolver/provider cause and smallest proposed change, pause and stop for the owner. No fixes or default/commit/push after a failure. All eight criteria must pass before the authorized default change, clean restart/old rollback proof, full focused tests/Ruff, secret-scanned scoped commits and push only to codex/resume-demo. The README section reflects this live-first order. Default remains old; nothing has been committed or pushed.

Eight focused harness tests passed after the reorder, covering original error propagation, provider stops by execution, stored reply recovery, fixture isolation and rating/archive preservation. Scoped Ruff passed. These tests do not establish model quality. The earlier65-test focused run remains documented in pass_notes. Raw logs/test storage/secrets must stay out of commits.


## V7 live acceptance paused — 2026-10-17T02:54:10.507192+00:00

L01-T3 / run 9e41fbfddba147a4b215c3c027d3bdb6 on Groq qwen/qwen3.8-27b, no fallback: Focus on fully straightening the weapon arm before the lunge begins so the extension is already locked in when your feet move. Many coaches teach the "hand first, then feet" sequence, which helps ensure the arm is extended and aimed before the body launches forward.

Manual criterion2 FAIL: unsupported compulsory full-extension-before-feet timing target from finish-only evidence. KB supports general hand-first and lists distinct tempos; it does not establish this athlete needs pre-initiative timing. “Locked in” is ambiguous against the no-elbow-lock cue. Two sentences, zero quantities; advice requested; indirect “Many coaches teach” attribution noted. Input has four complete history pairs, arm/lunge_finish scope, no unanswered question. Core0.880s / queue1.296s;6936input+54output=6990tokens. Other six prose criteria remain PENDING; criterion7 input-only PASS. See live_acceptance.md and assessment.json for exact source/trace and proposed change. No owner ratings inferred.

Automation PAUSED on manual failure,30-minute recurrence preserved. One real Groq reply,zeroGemini requests/errors this check. No later turn/readings/fixes/default change/commit/push. Frozen manifests still match; all prior artifacts retained.


## Owner-approved v7.1 continuation

Only the exact approved persona paragraph and a short appended per-turn reminder were added. An AST comparison verified the rest of PERSONA is identical to v7; the reminder retains its complete v7 prefix. No examples, authored KB, measurement map, packet or resolver changed. New v7.1 manifests record the one changed product source (core_packet.py); original v7 manifests and frozen sources remain intact. The old failed L01 transcript is preserved in [live_acceptance_v7_archive.md](live_acceptance_v7_archive.md), with complete cases/assessment in work/live_acceptance_v7/v7_archive. Fresh L01 uses live-v71-L01 in the isolated database, with identical questions and no old runs.

Product history fix excludes whole completed connection-message exchanges from recent_chat and excludes the same message from writer already_said. Saved history, trace and UI remain intact; no output is inspected, rewritten or deleted. Regression reproduces both L01-T2/T3 failed exchanges and checks actual captured model messages plus retained saved history.

Fresh v7.1 L01-T1 attempted once under owner-v71-20261017T0303Z. Real Groq429, limit200000/used197616/requested7313; Retry-After2130s takes precedence over body35m29.328s. Resume_after1792208267.6137888 = 2026-10-17T03:37:47.613789UTC / October16 23:37:47.613789Toronto. Provider0.167s, core0.224s; queue unknown. Raw report f247de54154140448de59bcae76cbf5c is a pending failed attempt, not a completed turn. Gemini skipped saved cooldown until October17 19:59:58.880428Toronto; zero Gemini calls. No retry within this run. No v7.1 model reply exists; criterion2 remains PENDING, old v7 FAIL is retained. Criterion7 remains input-only PASS; six other criteria PENDING.

Validation:37 focused writer/core tests PASS,8 harness tests PASS, scoped Ruff PASS. The broader citation-iteration module has one failure in test_semantic_fallback_is_shared_and_cannot_invent_scope_keys (expected arm, got no topics); resolver/semantic-scope sources are unchanged against v7 manifests, so this is outside this change. It remains unresolved and must be included in pre-shipping test review. Initial harness tests encountered the known sandbox Windows tempfile ACL error; the isolated mocked tests passed outside the sandbox with no provider calls. pytest is not installed; unittest was used. Tests are not model-quality evidence.

Owner order is L01,L06,L05,L04,L07, then L10 early when Gemini is eligible, then L02,L03,L09,L08. Finish each started chain; pin its first successful provider except L10's required Groq-to-real-Gemini switch. No model answer means no completed prefix advancement. Normal fallback before a chain has its first successful provider remains authorized. No further model calls in this run. Default old; no commit/push. Gate closed pending all eight live criteria and required shipping checks.


## Semantic test diagnosis — 2026-10-17T03:17:48.221757+00:00

See [semantic_fallback_diagnosis_v7_1.md](semantic_fallback_diagnosis_v7_1.md). Test fixture used high-confidence state, bypassing its mock; fixed only the test to explicitly supply low-confidence state and forbid live calls.44testsPASS; no product/resolver edit. Dormant helper has no app call sites, current semantic cost0tokens; hypothetical direct call shares writer Groq quota, max384outputtokens, exact actual usage unknown. Mocked429 preserves clarification and caches error; it has no writer cooldown integration. Saved L01 has resolved arm/lunge_finish and14readings; its429 is writer failure, not lost semantic scope. L05 my weapon arm resolves deterministically; generic unknown-subject limitation documented without changing it. No new live calls while saved cooldowns active; same30minute schedule.

# Citation iteration — stopped at usage limit

COACH_CORE stays old. No commit or push. Acceptance has not passed.

## Changes

Relative assessment objects compute per-feature, same-phase spread and extrema over all available reps. Best/worst refers only to a named geometric or elapsed-time aspect; directionless measurements are not ranked. There are no invented pass/fail cutoffs. Prior-session deltas require a declared identical camera setup, view, sides, weapon and crop; missing metadata is not comparability. All current historical fixtures lack verified matching setup identity, so actual cross-session improvement remains unestablished.

knowledge/standards.yaml contains 10 explicit library criteria, each with source file, verbatim excerpt, applicability and approved:false. No draft standard is loaded or applied. Topics without explicit criteria: speed, distance, blade control, force, power, fleche execution, recovery duration and numeric arm-direction targets.

The writer returns typed sentence records with evidence/library IDs and supporting quotations. Verification checks ID existence, exact numeric presence in cited records, citations on claims, and verbatim authored technique cues. Whitespace wrapping is normalized. Non-claim types bypass claim verification. Only failing sentences are removed; raw output and reasons remain in traces. The previous lexical assessment, priority, advice-overlap and physical-unit guards are removed. The shared stems helper remains for evaluation only.

Limits: valid citations do not prove semantic entailment. Wrong body parts, unit relabeling, spatial reversals, causal claims, unsupported judgments and dishonest sentence-type labels can pass. Literal cue rendering can sound formal and rejects paraphrases. No extra lexical guards were added to conceal these limits. Structured JSON is withheld until checked, so raw token TTFT differs from visible-answer latency.

Resolver changes preserve alternative order, support second-option selection and return-to-phase instructions, and make reset a persistent history boundary. A bounded, cached Groq semantic lookup is shared across answer providers for unresolved scope; unavailable lookup retains concrete clarification. Deterministic paths remain first.

Local fallback is deterministic packet/template output, with no Qwen generation. Existing Qwen runtime remains offline experimental; no further 3B/7B tuning occurred. Groq gpt-oss-20b uses the ignored environment key, JSON output, minimal reasoning and no SDK retries. Gemini retains one bounded 503 retry and no 429 retry loop. Hosted fallback failure produces an explicitly degraded packet reply. The async hosted adapter has a tested hard total deadline; the initially launched Groq holdout uses the preceding sync adapter with the same writer/state/checks and a best-effort elapsed deadline. This runtime difference must not be hidden as identical code.

## Observations so far

77 focused tests pass, including evidence safeguards. Scoped Ruff and compile checks pass. The complete Gemini diagnostic pass has 56/56 replies, zero provider errors and zero unmatched numeric mentions. It still fails conversational acceptance: H01-T2/T3 retain gap-only answers; H08-T3 declines without advancing; H10-T1 adds an unrelated back-leg aside; H10-T2 avoids a useful relative answer; E11-T7 and S11-T1/T7 exhaust their draft sentences and use template output. H09-T2 is a useful relative comparison, but it does not establish a broad quality win.

Groq diagnostic H10-T1/T2 twice calls extension relatively consistent without a justified cutoff; minimum two unsupported judgments. It also repeats the same answer. Fast inference is not evidence of coaching quality.

Offline replay scans all saved packet-era Gemini drafts with packets. Historical plain-text drafts have no sentence citations: their reconstruction attaches available IDs counterfactually and cannot establish real citation-selection performance. At the first audit, 423 unique legacy drafts contained seven question sentences wrongly removed by the lexical checker; the typed clarification path preserved all seven. New actual-citation drafts still lose otherwise usable text when the writer omits citations. See evals/citation_iteration/grounding_replay.json for every removal and its replay mode; do not present the counterfactual as an actual old writer run.

## Evaluation and remaining checkpoint work

A NEW 15-conversation / 60-turn holdout was frozen before execution, with timestamp and SHA-256 manifest in evals/citation_iteration/holdout_freeze.json. The old holdout is diagnostic only. Complete templates and ongoing paced Gemini/Groq passes are kept separately. scripts/report_citation_iteration.py regenerates the aggregate table and every saved transcript without provider calls. Its topic and response-kind counts are proxies, not full semantic continuity or verified helpfulness.

Running-app acceptance uses fresh session clones and separate SQLite/video directories, with COACH_CORE selected only in each test process. The intended comparison is 10 identical multi-turn chains per old/new core, with a synthetic 429 before new L10-T3. Do not call this comparison complete until both runs and per-chain naturalness reviews exist. No default flip is warranted from the current diagnostic evidence. Recommend retaining the currently shipped old core pending a completed live comparison and human review; this is not a measured claim that old reads better.

Groq API references: https://console.groq.com/docs/api-reference and https://console.groq.com/docs/rate-limits . No billing was enabled. No key is included in artifacts.

## Stopped status

Stopped before the final checkpoint at the standing weekly 20%-remaining wrap-up instruction (five-hour allowance 6% remaining). All task evaluation and isolated acceptance-server processes were stopped; main app processes were not targeted. Diagnostic Gemini completed 56/56; local templates completed 60/60 unseen turns. Gemini unseen completed 30/60 and Groq 11/60. Live old/new comparison: 0 turns; final manual review, unsupported-verdict/bait counts for the new holdout and per-chain naturalness ratings remain incomplete. Do not interpret provisional table rows as completed passes. Resume partial chains only with their saved history/state and the source snapshot/provenance; never mix isolated turn reruns into a coherent chain.

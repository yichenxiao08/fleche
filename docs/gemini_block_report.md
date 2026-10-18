# Gemini block diagnosis

Saved-artifact audit completed before any new generation request: 2026-10-16T23:08:42.836427+00:00.

The immediate v5 blocker is local: the runner counted requests by UTC date and inherited a local cap status as a provider cooldown. The latest actual provider failures for the four chains are HTTP 503 high-demand outages. They are not 429 quota errors.

## C01: latest saved provider failure

Turn 3; request started 2026-10-16T06:26:22.875567+00:00 UTC; Toronto 2026-10-16T02:26:22.875567-04:00. Timestamps are request start times; exact HTTP response arrival times were not separately saved.
Source: `evals/conversational_kb/model_review/fewshot-v4-frozen-pass/gemini/requests/C01-T3-1.json`.

HTTP 503 / UNAVAILABLE. Category (b), outage. No quota name or retry delay was reported (`retry_after_seconds=0`). Exact saved error:

```text
503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}
```

## C03: latest saved provider failure

Turn 3; request started 2026-10-16T06:27:22.879343+00:00 UTC; Toronto 2026-10-16T02:27:22.879343-04:00. Timestamps are request start times; exact HTTP response arrival times were not separately saved.
Source: `evals/conversational_kb/model_review/fewshot-v4-frozen-pass/gemini/requests/C03-T3-1.json`.

HTTP 503 / UNAVAILABLE. Category (b), outage. No quota name or retry delay was reported (`retry_after_seconds=0`). Exact saved error:

```text
503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}
```

## C13: latest saved provider failure

Turn 4; request started 2026-10-16T06:28:37.883482+00:00 UTC; Toronto 2026-10-16T02:28:37.883482-04:00. Timestamps are request start times; exact HTTP response arrival times were not separately saved.
Source: `evals/conversational_kb/model_review/fewshot-v4-frozen-pass/gemini/requests/C13-T4-1.json`.

HTTP 503 / UNAVAILABLE. Category (b), outage. No quota name or retry delay was reported (`retry_after_seconds=0`). Exact saved error:

```text
503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}
```

## C19: latest saved provider failure

Turn 2; request started 2026-10-16T06:29:07.884874+00:00 UTC; Toronto 2026-10-16T02:29:07.884874-04:00. Timestamps are request start times; exact HTTP response arrival times were not separately saved.
Source: `evals/conversational_kb/model_review/fewshot-v4-frozen-pass/gemini/requests/C19-T2-1.json`.

HTTP 503 / UNAVAILABLE. Category (b), outage. No quota name or retry delay was reported (`retry_after_seconds=0`). Exact saved error:

```text
503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}
```

## Counts before the authorized probe

Across ALL model-review revisions, the canonical request ledgers contain 20 Gemini generation attempts dated October 16 UTC: v1 3, v2 2, v3 1, v4-frozen-pass 14. All 20 have saved Google responses or Google 503 errors: 5 successful replies and 15 HTTP 503 outages. All 20 reached Google. None of those 20 were locally refused. They fall on October 15 Pacific; the current October 16 Pacific count is zero. Do not count copied inspection artifacts, input-only captures or countTokens calls as generations. Individual records and timestamps are in `../evals/conversational_kb/model_review/fewshot-v5-history-clean/block_audit/before_probe.json`.

Local refusals have no HTTP status and are NOT generation attempts. The saved status snapshots show three cap-related blocked states: v4-frozen-pass (20-attempt UTC cap), v5 (inherited cap), and v5-history-clean (inherited cap). These are three persisted states, not a complete invocation log; repeated refused invocations may overwrite status.json, so their exact historical count cannot be recovered. No v5 Gemini requests were sent before this audit. The paired-history runner also refuses to advance past a missing earlier assistant reply: C01-T2 onward, C03-T2 onward, C13-T2 onward and C19-T2 onward are ineligible until their prefixes exist. This is category (c), with no HTTP response.

## Quota origin and reset

The hard-coded 20-attempt cap is our runner setting. Separately, the older real Google 429 in `evals/conversational_kb/model_review/gemini/requests/C01-T1-2.json` explicitly names `generativelanguage.googleapis.com/generate_content_free_tier_requests`, limit 20, model `gemini-3.8-flash`, and `GenerateRequestsPerDayPerProjectPerModel-FreeTier`. It reports `Please retry in 3h27m53.943387422s.` This is category (a); it is not one of the four latest failures above. Its raw request/error record is preserved.

Google documents that RPD resets at midnight Pacific, and quotas are per project, not per API key. Interactive limits depend on project/tier and are shown in AI Studio; the current public page does not publish an interactive free-tier RPD number for this model. There is no evidence here that the documented applicable allowance is higher than 20. [Official Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), checked October 16, 2026. Batch-token tables are not an interactive request allowance.

The current Pacific day is October 16; its next reset is October 17 00:00 PDT = October 17 07:00 UTC = October 17 03:00 EDT in Toronto. The old local cap used October 17 00:00 UTC / October 16 20:00 Toronto, seven hours too early as a daily reset, while wrongly blocking this new Pacific day. Harness-only correction uses America/Los_Angeles calendar dates and timezone-aware next midnight. Provider Retry-After/RetryInfo or reported textual duration takes precedence for error cooldown; without a hint, a daily-quota error waits until Pacific reset. No prompt, packet, resolver, KB or example changes.

## Other consumers and limits of the audit

Read-only process/task inventory found zero running Python/Uvicorn/FenceCoach/Gemini processes and zero matching Windows scheduled tasks. There is one Codex Gemini continuation automation (this pass), and zero other Codex automations mentioning Gemini/FenceCoach. The old app is configured for gemini-3.5-flash-lite, with gemini-3.8-flash as conversational fallback, using the same settings.gemini_api_key from the ignored .env; it could share this project quota when running. The SQLite app records have zero runs/coaching_jobs/coaching_jobs_v2 dated October 16 UTC, with newest records October 14. Thus recorded app generations today: zero, and recorded concurrently running evaluation consumers: zero. No external key consumers can be ruled out from local artifacts; project-wide actual Google usage is not independently available here.

26 repository scripts mention Gemini (including the new continuation harness), including evaluators, review runners, configuration and reporting utilities; a mention is not a running consumer or a generation. Historical review runners use the same configured key/model and are included in the cross-revision ledger counts above. No keys were printed or changed.

## Qwen independence

Qwen has its own ledger/status and no dependency on Gemini readiness. At audit time its 31 saved UTC-day attempts across revisions reached the existing local daily attempt budget (27 successful, 4 quota failures); v5 has 15 successful replies. C03 and C13 are already complete; C19-T4 is next. Its saved cap resume_after is October 17 00:00 UTC (October 16 20:00 Toronto). This budget remains respected; expanded continuation order is prepared without regenerating saved replies.

## Authorized live C01 probe and continuation

Finished 2026-10-16T23:11:43.151507+00:00. C01-T1 succeeded, then T2, T3 and T4 succeeded once each. No retry, no error and no other Gemini chain requested in this diagnostic run. C01-T2/T3/T4 were sent only after all earlier stored replies existed.

Status for each: successful SDK GenerateContent response with a stored reply. The existing adapter does not retain the numeric HTTP success status or raw HTTP envelope, so an exact numeric HTTP code cannot be recovered from these records; it would be incorrect to present an unrecorded 200 as captured evidence. Full SDK response objects, request messages and provider metadata are preserved in the request ledgers. No generation was sent to discover an HTTP status.

### C01-T1

Request start UTC 2026-10-16T23:09:52.027866+00:00; Toronto 2026-10-16T19:09:52.027866-04:00. Provider gemini; model gemini-3.8-flash; prompt fewshot-v5; latency 26.002s. Actual tokens 6210 input + 104 output = 6314 total; cache-read 0.
Record: `evals/conversational_kb/model_review/fewshot-v5-history-clean/gemini/requests/C01-T1-1.json`.

Verbatim coach reply:

Your weapon elbow shows an extended finish across your lunges, though it varies from a slight bend around 146 degrees to a straighter finish near 174 degrees. Coaching guidance emphasizes extending the weapon arm toward the target without locking the elbow, and your finish angles reflect that pattern rather than a fully locked joint. Keep in mind that these finish measurements reflect the final position rather than whether the arm initiated the motion before the feet, and fixed side-view pose tracking cannot verify point drop or blade aim.

### C01-T2

Request start UTC 2026-10-16T23:10:18.052909+00:00; Toronto 2026-10-16T19:10:18.052909-04:00. Provider gemini; model gemini-3.8-flash; prompt fewshot-v5; latency 13.494s. Actual tokens 6321 input + 63 output = 6384 total; cache-read 0.
Record: `evals/conversational_kb/model_review/fewshot-v5-history-clean/gemini/requests/C01-T2-1.json`.

Verbatim coach reply:

It cannot be called fully good because the degree of extension fluctuates considerably across your attacks rather than remaining reliably consistent. While coaching principles call for reaching toward the opponent without locking the joint, your finishes range from noticeably bent to almost fully straight, and this side view cannot determine whether your point stayed on target throughout the motion.

### C01-T3

Request start UTC 2026-10-16T23:10:33.053843+00:00; Toronto 2026-10-16T19:10:33.053843-04:00. Provider gemini; model gemini-3.8-flash; prompt fewshot-v5; latency 10.038s. Actual tokens 6392 input + 53 output = 6445 total; cache-read 0.
Record: `evals/conversational_kb/model_review/fewshot-v5-history-clean/gemini/requests/C01-T3-1.json`.

Verbatim coach reply:

Aim for a consistent, relaxed finish by extending fully toward the target without letting the elbow stay overly bent or snap rigid. You can work on this using the slow-motion lunge drill, where you practice the complete extension at a controlled pace before introducing maximum speed.

### C01-T4

Request start UTC 2026-10-16T23:10:48.054732+00:00; Toronto 2026-10-16T19:10:48.054732-04:00. Provider gemini; model gemini-3.8-flash; prompt fewshot-v5; latency 17.458s. Actual tokens 6483 input + 119 output = 6602 total; cache-read 0.
Record: `evals/conversational_kb/model_review/fewshot-v5-history-clean/gemini/requests/C01-T4-1.json`.

Verbatim coach reply:

Your active return to guard ranged from under a tenth of a second up to around two tenths, showing a quick backward pull once your hips began retreating. Many coaches teach that a proper backward recovery requires unlocking the rear knee, driving with both legs, and keeping the weapon arm extended until the body has pulled back. Because our side-view video tracks body positions rather than the precise sequence of arm retraction, it cannot confirm whether your blade remained out until your stance was re-established. Practicing slow-motion recoveries with an explicit focus on retracting the weapon arm last will help reinforce that balance.

After the run: October 16 UTC has 24 canonical Gemini attempts (9 successful SDK replies and 15 Google 503 errors), all reached Google. October 16 Pacific has 4 attempts, all successful. The earlier local refusals are not included as requests. Qwen made zero new generation calls in this run because its saved local budget cooldown is still active.

The existing daily 20:05 Toronto automation was updated to the expanded Qwen order and Pacific Gemini accounting. Targets are 80 successful Qwen replies and 16 successful Gemini replies. It will pause after those targets; this diagnostic run stops here for reading.

Validation: 9 targeted quota/history-runner tests and scoped Ruff checks passed. Original per-provider frozen source manifests and the separate new quota-harness source manifest matched after execution. No writer source or examples were changed. These are implementation checks, not quality ratings.

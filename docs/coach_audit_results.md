# Conversational coach results — 2026-10-13

The validated-phrasing workflow is enabled by default in source (`FENCECOACH_VERIFIED_DIALOGUE=true`). The user selected this design and requested a more natural voice. No existing application server was restarted. Restart the app to load the changed modules.

## Live before/after results

| Provider / path | Completed | Provider errors / skipped | Median complete reply | p95 | Median model TTFT | Median first visible text |
|---|---:|---:|---:|---:|---:|---:|
| Gemini, original working-tree baseline | 4 / 86 | 82 / 0 | 2.963 s | 3.332 s | not measured | 2.961 s |
| Gemini, validated phrasing | 20 / 100 | 2 / 78 | 0.994 s | 4.272 s | 0.983 s | 0.992 s |
| Qwen, original baseline | 0 / 12 recorded | 12 / run interrupted | not measured | not measured | not measured | not measured |
| Qwen, validated phrasing | 100 / 100 | 0 / 0 | 0.681 s | 0.959 s | 0.425 s | 0.664 s |

The original baseline predates the independent oracle and has unequal completed-case coverage. These are observed, unpaired totals; they do not establish a paired model-quality improvement. Baseline Qwen was initially unreachable; after starting the relocated portable runtime, a live turn took 103 seconds and returned an empty answer. Ollama reported 83.7 seconds processing a 13,554-token prompt and 9.0 seconds generating its 160-token allocation.

Gemini completed 20 turns before two real GoogleRateLimitError failures. The runner marked the remaining 78 turns skipped instead of repeatedly spending quota. It did not substitute Qwen into the isolated Gemini benchmark. Median latency is below the 2–3-second target, but the 4.272-second p95 misses it. There is no valid live Gemini fabrication-bait score because those cases were not reached.

## Independent evidence and continuity checks

| Metric | Gemini live | Qwen live | Offline protocol, each provider |
|---|---:|---:|---:|
| Follow-up topic/rep accuracy | 100% of 13 scored turns | 100% of 63 scored turns | 100% of 63 turns |
| Unsupported-claim flags | 0 / 20 replies | 0 / 100 replies | 0 / 100 replies |
| Fabrication flags on bait | not measured live | 0 / 10 bait turns | 0 / 10 bait turns |
| Content fallback correctness | 100% | 100% | 100% |
| Mean cited measurement records per reply | 0.90 | 0.73 | 0.73 |
| Additional semantic review needed | 0% of completed replies | 0% | 0% |

The oracle reads saved source measurements, units, phases, reps, timestamps, reference ranges and actual library text. It does not use production topic classification or renderer equality as its grounding oracle. It permits exact ms-to-seconds conversion and a narrow independently authored sword-arm-to-target paraphrase relation. Wrong roles, added doses, ideal angles, timing/force qualifiers, fake quotes and mismatched record coordinates have adversarial tests. These checks have bounded language coverage; zero flags is not proof of universal coaching correctness or usefulness.

## Step timings and local budget

| Median step | Gemini | Qwen |
|---|---:|---:|
| Retrieval/packet construction | 12.68 ms | 12.63 ms |
| Model streaming/selection | 730.78 ms | 504.31 ms |
| Final unit check/publication | 0.008 ms | 0.010 ms |

Timings cover a programmatic coaching request including client setup, evidence selection, model call and complete checked reply. Subprocess bootstrap is separately recorded as wall_clock_ms. HTTP queueing, the API request-builder cache miss and the browser polling/render loop were not included in this provider benchmark; complete browser message-to-reply latency is still unmeasured.

On this machine the runtime reported Intel Arc 140T integrated GPU (16 GB), Vulkan inference and Qwen2.5:3b. The new path uses a 4,096-token local context and 96 output tokens, with keep_alive=-1 and startup warming even when Gemini is primary. Adopt a **2-second warm coaching-turn budget**, with an **8-second provisional startup/context-reload budget** based on the earlier 6.6-second first-turn diagnostic. A fresh fully unloaded cold start and a busy queue have not been benchmarked. The local transport deadline is 20 seconds; provider failure is surfaced honestly. The model selects supported phrase variants, so these budgets do not apply to the retained unrestricted legacy writer.

## Provider-switch validation

The forced-429 five-turn conversation passes: turn 2 selects arm extension; turn 3 raises HTTP 429 with Retry-After=120 and answers through Qwen using the same application state/evidence; turn 4 uses the cooldown without calling Gemini; turn 5 advances the controlled clock, probes Gemini and closes the circuit. Traces preserve answered provider and fallback reason. Separate tests cover a single half-open probe, stale concurrent success after a newer rate-limit failure, nonretryable 400/401/403/404/422 errors and both providers timing out.

## Verification and deliverables

- 197 unit/integration tests pass in `work/coach-audit-final-suite.log`, including default dispatch, new-state serialization, legacy writer/Bedrock compatibility, cache invalidation and the independent eval oracle. Eight old model-protocol test classes explicitly exercise the retained legacy path; new tests exercise the verified default.
- Focused Ruff checks pass for changed coaching, cache, schema and eval/test files. The full repository lint run still reports eight pre-existing issues in `scripts/evaluate_coach_contract.py`; those unrelated import/simplification issues were not changed.
- Saved data snapshots: `current.json`, `unsupported.json`, `low_confidence.json`. No athlete measurements were fabricated. `conversations-v2.json` defines 37 conversations and 100 turns with independent per-turn expectations.
- Final live artifacts: `after-gemini-final-verified.json`, `after-local-final-verified.json`; offline artifacts and `forced-switch-final-verified.json` are separately labeled.
- `gemini-before-after.md` and `local-before-after.md` retain missing baseline metrics as not measured and warn about unequal coverage. JSON includes source/fixture hashes, model IDs, traces, TTFT and reply latency. Interrupted diagnostic runs are labeled and preserved.

## Remaining known limits

1. Full live Gemini coverage, especially bait cases, and a paired original-baseline quality benchmark remain unavailable because of quota and the earlier interrupted baseline. Do not claim an improvement those missing data cannot show.
2. Phrase coverage is finite. Unknown aliases, mixed measured/unmeasured requests and unusual technique questions can produce conservative gaps. Library guidance and metric explanations are grounded, but independent expert usefulness/tone ratings are still needed. All-rep and multi-feature replies can be longer than ordinary turns.
3. The circuit is process-local; distributed workers need shared cooldown state. HTTP Retry-After is supported; Google structured RetryInfo details are not yet parsed. The durable evidence cache fills on the first coaching request, rather than proactively at video processing time. Browser/queue latency, fresh cold starts and busy-hardware tail latency remain unmeasured.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/eval_coach.py --phase after --providers gemini local --run-id next-run --turn-timeout-seconds 20
.\.venv\Scripts\python.exe scripts/eval_coach.py --phase after --offline --run-id next-offline
.\.venv\Scripts\python.exe scripts/eval_coach.py --phase after --forced-switch --run-id next-switch
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Use unique run IDs; --resume requires matching code, fixture and expectation hashes. New --phase before runs exercise the retained legacy path at the current revision, not a reconstructed audit-start working tree.

All evaluation subprocesses completed or were joined after interruption. The Ollama service and llama-server process started for this audit were stopped; orphan evaluation transport files were removed. Existing application services were left in their original state.


## Live application queue incident (October 13)

The question `how was my torso throughout` repeatedly failed in the browser while direct replay of the exact saved request succeeded with both Gemini and local Qwen. Two uvicorn instances were running on ports 8000 and 8001, sharing the same SQLite coaching queue. Recent failures retained worker owner `bd8aa3a992dd4f0b89ddfae8561965cc` across restarts of the current server; successful jobs were claimed by other worker owners. After stopping the older port-8001 instance, the exact question completed via the production queue (job `f15ef94ba5eb4f3f8e1ef99c9fc4d290`). This identifies stale background-worker competition as the cause of the repeated generic failures, rather than the athlete question or unavailable torso data. The older worker's original exception was not retained, so its precise internal error is unknown.

New requests now use `coaching_jobs_v2`. Legacy workers only read `coaching_jobs`, and current workers only claim the new queue. Historical jobs remain readable and cancellable. Unexpected internal failures no longer blame the provider; their exception class/module is retained privately in the job record, without exception text or credentials. Four temporary-database regressions cover legacy/current isolation, old-job compatibility, production worker publication and persistence, and internal failure diagnosis. All four passed; the 27 focused dialogue/router checks and Ruff also passed. The exact live request completed on queue version 2 with Gemini (job `3012aeb80e7e41d3b6fa25aeec520c80`, run `90055e2806de408ba0417f9083192e88`). The older port-8001 server was stopped; the current app and Ollama remain running for user testing.

The archived 100-turn evaluations above predate the subsequent context-recovery, provider-error and queue-isolation changes and must not be represented as fresh evaluations of this revision. A remaining answer-quality gap is that the renderer selects one finish sample for `throughout`; this does not establish continuous whole-clip torso behavior. That scope/coverage problem remains to be addressed separately.

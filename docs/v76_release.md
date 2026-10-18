# Owner-approved v7.6 default and running-app smoke check

October 18, 2026 (Toronto). Owner accepted the reviewed live gate and authorized default promotion, scoped commits and push to codex/resume-demo. No schedules were created or reactivated.

## Clean application start and rollback

Port 8000 had no listener (HTTP connection refused). Started the normal app with `.venv\Scripts\python.exe -m uvicorn fencecoach.api:app --host 127.0.0.1 --port 8000`, PID 31264. No COACH_CORE process variable or .env override was present; a fresh Settings() resolved new. Each subsequent real app report records core=new and fewshot-v7.6. Storage is the normal data/fencecoach.sqlite3, not acceptance storage.

Rollback: put `COACH_CORE=old` in the ignored .env file and restart the app. The old implementation remains available. Remove the override or set COACH_CORE=new and restart to restore new.

## Normal chat UI transcript

Opened http://127.0.0.1:8000/#coach, selected the existing non-demo saved session Test 2 (f4bb32db2f4f4c4c9f18defc509e899f), and sent each exact question with the chat composer and Send button. These are three separate user turns, one submission each, with no harness, synthetic fault or retry loop. The saved session resolves tracking_unsupported and zero usable arm readings; the conversation tests normal UI routing, fallback and withholding, not personal-arm verdict quality. Older chat remains intact.

Queue wait below is worker-start minus persisted creation time. Core includes writer/provider processing; browser round-trip and separate provider-only latency were not instrumented. Failed-call token consumption is unknown.

### Turn 1

Athlete: how's my arm extension?

Coach (full verbatim):

> I don't have usable arm extension or direction readings for this session, so I can't judge that specific detail. The usual cue is to keep the elbow, forearm, and point in one line parallel to the floor, but without the measurements I can only describe that general principle rather than assess your actual finish.

Provider/model: groq / qwen/qwen3.8-27b. Core 1026.742 ms; queue wait 36.196 ms. Fallback: none. Actual reported tokens 6626 input / 63 output. Run f9d03a9c31ad40f4a06258f0272649db.

Provider attempts: [{"provider": "groq", "status": "ok"}].

### Turn 2

Athlete: is it good?

Coach (full verbatim):

> I cannot give you a verdict on your arm because those measurements are missing from this session. Many coaches teach extending the weapon arm toward the target without locking the elbow as the standard to aim for. Let me know if you would like to look at another reading from your lunges instead.

Provider/model: gemini / gemini-3.8-flash. Core 4032.050 ms; queue wait 57.662 ms. Fallback: groq:rate_limit. Actual reported tokens 6771 input / 57 output. Run c37f666374754702866b8424d50b87f7.

Provider attempts: [{"provider": "groq", "status": "error", "reason": "rate_limit", "error_type": "HostedError", "retry_after_seconds": 60.0}, {"provider": "gemini", "status": "ok"}].

### Turn 3

Athlete: what should I change?

Coach (full verbatim):

> Because that arm data is missing, I cannot point to a specific fault in your extension to correct. Many coaches teach focusing on a relaxed shoulder and extending the weapon arm toward the target without locking the elbow. A useful exercise for this is the slow-motion lunge, where you move through the entire sequence deliberately to check your arm line and extension.

Provider/model: gemini / gemini-3.8-flash. Core 11352.405 ms; queue wait 33.837 ms. Fallback: groq:cooldown:rate_limit. Actual reported tokens 6836 input / 70 output. Run a2c490f912dd4fa5ac16be21e139bc30.

Provider attempts: [{"provider": "groq", "status": "cooldown", "reason": "rate_limit"}, {"provider": "gemini", "status": "ok"}].

T1 real Groq success; T2 real Groq rate limit followed by real Gemini success; T3 skips cooling Groq and uses real Gemini. No paid provider, new key/account, local model, output checker, template or rewriting was introduced. The model repeats general cues and T2 offers an unasked topic switch; these are preserved observations, not additional quality claims.

## Verification

333 tests pass with COACH_CORE=old, exercising the retained legacy path and shared modules; 93 focused tests pass with COACH_CORE=new, covering the new writer and evaluation/acceptance transport. test_semantic_fallback_is_shared_and_cannot_invent_scope_keys passes (mocked, no provider request). Ruff check and format check cover all src, scripts and tests. Windows sandbox temp-directory ACL errors required rerunning tests outside that sandbox; final runs pass.

Test maintenance: archived v7 runner pins its mocked revision; forced-fallback test uses fresh circuit instances; legacy clarification tests require explicit rejection and no published draft instead of obsolete canned replacements; default assertion checks new and old rollback. Evaluation-only numeric attribution now keeps a recovery phase in one clause from relabeling a knee angle in another; wrong feature/value/unit tests still pass. None changes the frozen prompt, packet, resolver, KB, map or examples.

## Commit scope and private artifacts

Changes are grouped as artifact hygiene; knowledge and examples; packet/resolver and legacy support; new core/provider/default; evaluation and acceptance harness; documents and demo assets. Existing inactive research and legacy review modules are retained for reproducibility; the default v7.6 path reports output_checks=false. Raw ledgers, requests/responses, run databases and temporary outputs stay local and ignored. Existing runtime logs/databases are removed from the index without deleting local copies. The recorded demo is available without quota.

The live gate remains the owner-reviewed result: zero hard fails across 13 reviewed retest replies, eleven soft-slip turns; criterion7 input-only evidence. This UI smoke check is separate and does not expand that quality claim.

## Source freeze and secret audit

The accepted prompt, packet, resolver, KB, measurement map and examples still match both frozen v7.6 manifests byte for byte. Two other manifest entries differ: the owner-approved settings default and formatting-only changes to the archived v7 evaluation runner. The original manifests are preserved without edits.

Scanned all 44 existing commits (669 unique blobs) for current .env secret literals, whole-file .env content, provider key patterns and private-key markers: zero hits. Scanned 2,805 readable working-tree text/artifact files: only the expected ignored .env matched; no other secret hit. Sandbox-inaccessible temporary test directories remain ignored and are not staged. Each proposed index and each new commit is also scanned before push. This is a literal/pattern scan, not a guarantee against unknown secret formats.

The pre-existing history contains runtime logs and two local timing-test databases. They are untracked at the new tip and preserved locally; existing history was not rewritten. Provider request ledgers and isolated acceptance databases are not staged. Curated transcripts/rating sheets remain in documentation as requested; raw transport records stay local.

| Purpose | Changed/new files | Scope |
|---|---:|---|
| hygiene | 1 | Ignore private runtime artifacts; untrack 12 existing logs/databases |
| knowledge | 5 | Authored teaching, measurement map, style examples and explicitly unapproved research references |
| packet | 17 | Topic/rep/phase state, evidence packets, resolver and legacy support tests |
| core | 17 | New writer, provider routing/default, retained legacy/research modules and tests |
| evaluation | 42 | Offline evaluation/reporting and live acceptance harnesses with transport/history tests |
| documents | 69 | README, full acceptance, rating sheets, pass notes, historical reports and recorded demo web assets |

Verbatim historical transcripts retain their original trailing whitespace and blank lines. Code whitespace checks pass; the documentation commit permits those transcript-only whitespace findings rather than editing recorded model text.

## CI correction after default promotion — October 18, 2026

The earlier 333-test full-suite run explicitly selected COACH_CORE=old. It did not establish that the ordinary CI command passed under the newly shipped default. CI exposed legacy writer/repair/tool tests implicitly selecting that default, plus a quota test that read an ignored local provider ledger absent from checkout.

Legacy-only test classes now explicitly patch coach_core=old within each test and restore it afterward. The workflow still runs its ordinary unittest discovery command without a global COACH_CORE override. The quota test supplies an in-memory saved-status fixture. Existing assertions and test cases remain enabled. No application source, default, prompt, packet, resolver, KB, map, examples or runtime checks changed.

A new regression exercises the actual default through direct HTTP and a durable queued chat. Mocked providers verify Groq success, Groq429-to-Gemini fallback, unchanged model-authored text, preserved arm/rep2 focus, and zero rejected measurements in both provider packets. It makes no live provider calls.

Verification: 334 tests PASS from a fresh tracked-file checkout plus this patch, with no .env, ignored provider ledgers or COACH_CORE override. Provider credentials are empty and test storage is separate. The semantic fallback test also passes. Ruff check and format check pass over src/tests/scripts. This was Windows/Python3.14 local reproduction; GitHub's Linux/Python3.12 result must be reported separately when available.

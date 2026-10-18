# Frozen fewshot-v4 pass notes

2026-10-16: section map rejected and remains disabled. The frozen writer sends the full KB. Prompt, packet code, authored KB, examples and resolver are unchanged. Fresh pass artifacts are separate from archived readings.

No new-pass model replies have been read yet. Record observed bugs below without fixing frozen application code or prompt. No pre-rating.

Gemini outage context: each turn has one attempt. Later distinct questions after an outage may refer to an unanswered question. The runner preserves prior user text and resolved input scope, inserting no assistant reply. Rating-sheet reply cells stay blank for failures/unrun turns; raw transcripts identify status. Outages are saved failed outcomes, not successful model replies.

## 2026-10-16 02:29 AM Toronto — first fresh run

Qwen saved C01-T1/T2 on frozen v4, then stopped at its first 429 on C01-T3. Groq reported TPD limit200000,used199183,requested7137; saved resume_after is 2026-10-16T03:13:33.481500-04:00. No inline retry.

Gemini attempted14distinct turns exactly once each: C01,C03,C13 and C19-T1/T2. Two replies completed(C01-T4,C03-T4);12attempts returned503outages. C19-T3/T4 remain unrun because the20savedattemptUTCdaycap includes6earlierpassattempts. Failed turns remain blank in the rating sheet and are not regenerated on later days. Later questions after outages have no preceding assistant reply for the failed turn; interpret that context accordingly.

The96rating rows retain blank Acceptable,reason,Invented columns. No ratings assigned and no quality metrics table. Raw replies are untouched. Frozen source hashes and exact prompt identity verified; no application code,prompt,packet,KB,examples,resolver or COACH_CORE changes. No newly identified application bug was fixed. Section map stays rejected. Dailyautomation ACTIVE until80Qwenreplies and16savedGeminioutcomes,thenpauseforratings.

## fewshot-v5 — owner-authorized two changes

V4 C01-T4 and C03-T4 falsely described missing previous-topic data even though both original packets explicitly listed arm and torso as available, current requested_statement=null. Exact evidence and the unanswered-user-message history are in docs/v5_packet_review.md. Replaced overlapping examples with6style-only non-evaluation scenarios; packet now emits gaps only for requested actually-missing topics, carries current_question and identifies earlier questions as history. Persona/reminder/resolver/KB unchanged. No output processing.34tests pass; no generated v5 reply yet, so behavior improvement unproven.

Both v5 reruns were blocked before invocation by saved earlier cooldowns. Only C01,C03,C13,C19 on each model are authorized; old80turnv4continuation superseded. Rating sheet preserves v4 in separate comparison section; no pre-rating. Daily automation now targets only v5 subset and pauses when done for owner ratings.

Harness display note left visible: prepare-only console message retains the inherited text frozen-v4; saved manifest,prompt files,raw transcript labels and rating section correctly identify fewshot-v5. No provider request was affected.

## History hygiene correction — prompt version remains fewshot-v5

Gemini v4 C01-T4 and C03-T4 are INVALID EVALUATION INPUTS after three unanswered user questions in history, not quality evidence. Their archived rows and transcript carry an explicit input-validity annotation, outside the blank quality-rating columns; raw records remain untouched.

Product history now sends only completed pairs from stored writer replies. It no longer bootstraps unanswered user-only history and cannot split a pair at the input budget boundary. Original messages remain in the saved trace/record. Runner history-clean artifacts are separate; a contiguous successful prefix is required, every outage stops the provider run, and only the same failed turn can resume in a later eligible run. No later question is attempted after a missing reply. Completion now requires 32 successful replies, not replies plus outages.

Six pending style examples remain. The two generic Athlete strings “Why does that matter?” and “Thanks.” overlapped evaluation questions; they are now “Why should I update the venue note?” and “Thanks for untangling the diary.” Contexts and Coach wording are unchanged. All six contexts/topics are outside the evaluated fencing questions. No persona, reminder, packet, resolver, measurement-map or authored-KB change.

38 focused tests and Ruff pass. These validate input hygiene and sequencing, not coaching quality. No rating assigned. Section map stays rejected; no output checkers/guards/templates/sentence deletion, billing, extra keys/accounts, commit/push or COACH_CORE flip.

## Clean v5 run result — 2026-10-16T19:00:40.739219-04:00

Qwen15/16successfulreplies, no outages. C19-T4unrun at the31saved dailyGroqattemptcap acrosspasses. Gemini0/16, no request because prior dailycapcooldown still active. Both reset 2026-10-16 08:00 PM Toronto; daily8:05pmToronto continuation remainsactive. All15actual model inputs contain completed history pairs only; no unanswered questions sent as pending. All32ratingrows present, all ratingcolumns blank; no prerating. Source hashes, unchanged packet/resolver/KB and exact prompt identity verified. Completion requires32successfulreplies; failed attempts never count as completion or permit a later turn.


## Owner observations received October 16, 2026 — record only

- Several v5 Qwen replies run a full paragraph with more than two numbers: C01-T1, C01-T4, C19-T1.
- C13-T3 speculates "might be related to how you're driving that leg" without evidence.
- The received C01-T2 observation ends at "says"; its remainder was not supplied. No completion inferred.

No prompt, packet, resolver, KB, example or output edits were made in response to these observations.


Gemini diagnostic run: all four C01 turns succeeded. Raw T4 adds an arm-retraction sequence and "arm last" practice cue; record only for owner reading, no tuning performed. Quota harness fixes Pacific daily accounting and provider retry-delay handling only. All original source hashes matched. Nine quota/history-runner tests and scoped Ruff passed; no quality inference from checks.


## Fewshot-v6: authorized scope and baseline telemetry

See [coach_fewshot_v6_review.md](coach_fewshot_v6_review.md) for the exact authorized scope and cited thinking/cache findings. V5 Gemini C01 latencies: T1 26.002s, T2 13.494s, T3 10.038s, T4 17.458s. Thought-token counts are unknown for each; the saved response fields are absent. Cache-read tokens are explicitly zero for each. Gemini 3.8 Flash minimal/off thinking is unsupported; existing low retained without an unsupported probe. V6 C01-T1 3.148s is a new prompt/provider observation, not a reduced-thinking experiment.

Owner ratings are retained as comments: short replies C13-T1/T2/T4, C03-T2/T4 and C19-T2 good; reference-material naming bad; long multi-number paragraphs C01-T1/T4 and C19-T1 bad; contextual verdicts apply to any topic. No rating-sheet values were inferred.


## V6 Gemini manual reading — first run

13 replies saved; C19-T2 is a real429quota error, not a503 high-demand outage. Limit20 and reportedretry38m48.207246655s were retained. Resume_after1792195199.5416937 (Oct17 00UTC/Oct16 20Toronto) follows the provider hint; documented normal dailyreset remains midnightPacific. C19-T3/T4 unrun; no retry this run.

Requested observations (manual reading; no output checker or editing):

- C01-T4 contains four numbers:0.07,0.17,0.27,0.57. It also appends an arm-retraction sequence to a recovery-time question.
- C13-T4 says "recover smoothly", a prohibited smoothness adjective/adverb.
- C13-T3 says no rear-leg-extension change is needed, then offers a downward-versus-backward push cue without a measured drive problem or an explicit force/direction question. The athlete did ask what to change, so this is recorded as potential unmeasured overreach rather than falsely labeled an entirely unasked change request.
- C03-T3 likewise says nothing needs changing, then adds a balance-lunge suggestion. A change was requested; the concern is adding practice despite the declared absence of a gap.
- No saved Gemini v6 reply so far names the knowledge base/the KB/coaching guidance/reference. None exceeds four sentences. No declined measured-topic verdict was observed; C13-T1 has no established topic and asks for clarification. C03/C13 straight-leg and torso verdicts use cues met across reps; their numeric ranges vary within the stated cue, which is different from mixed cue compliance. These observations are not owner ratings.

Gemini per-turn latency; thought tokens unknown for every saved turn (reasoning field absent, not zero):
- C01-T1: 3.148s; thought tokens unknown; cache-read 0.
- C01-T2: 1.969s; thought tokens unknown; cache-read 0.
- C01-T3: 2.987s; thought tokens unknown; cache-read 0.
- C01-T4: 2.688s; thought tokens unknown; cache-read 0.
- C03-T1: 5.175s; thought tokens unknown; cache-read 0.
- C03-T2: 6.492s; thought tokens unknown; cache-read 0.
- C03-T3: 9.050s; thought tokens unknown; cache-read 0.
- C03-T4: 11.017s; thought tokens unknown; cache-read 0.
- C13-T1: 5.711s; thought tokens unknown; cache-read 0.
- C13-T2: 4.699s; thought tokens unknown; cache-read 0.
- C13-T3: 5.052s; thought tokens unknown; cache-read 0.
- C13-T4: 7.488s; thought tokens unknown; cache-read 0.
- C19-T1: 6.115s; thought tokens unknown; cache-read 0.
- C19-T2: quota failure after 0.195s; thought tokens and usage unknown; T3/T4 unrun.


## V6 Qwen manual reading — first run

Six replies saved: complete C19 under v6, then C01-T1/T2. First actual429 stopped C01-T3; totalproviderlimit200000tokens, used193552, requested6839. Retry-After169seconds was used; bodytext says2m48.912s. Resume_after2026-10-16T23:27:15.000026UTC /19:27:15Toronto. No retry even if that short delay elapses during reporting. C01-T4 and the later chains remain unrun.

No saved Qwen v6 reply in this run mentions the knowledge base/the KB/coaching guidance/reference, uses the listed speed adjectives, exceeds four sentences or two numbers, adds an unasked practice suggestion, or declines a verdict when cue+readings exist. No good verdict over mixed cue compliance was observed. These are manual observations, not owner ratings. Additional repetition: C01-T2 repeats145.7–174.4fromT1. C19-T4 names both knee-position consistency and varying depth; it does not infer an invented angle target. No output was revised.

Qwen per-turn latency:
- C19-T1: 1.041s.
- C19-T2: 0.787s.
- C19-T3: 2.247s.
- C19-T4: 0.956s.
- C01-T1: 0.927s.
- C01-T2: 0.803s.
- C01-T3: quota failure after 0.125s; tokens unknown. Remaining turns unrun.

Gemini delay precision: saved Retry-After2328seconds took precedence over bodytext38m48.207246655s. The resulting resume_after23:59:59.541694UTC is the precise saved value. Thought counts remain unknown, not inferred by subtracting displayed output from totals. Inherited error logging truncates detail at1000characters; the saved Gemini error ends inside quotaDimensions. The quota name, limit, status and retry text before that boundary are retained. No further request was made to recover missing metadata.


## Frozen v6 continuation — October 16, 2026, 20:04 Toronto

Codex usage checked before continuation: 100% five-hour and 59% weekly remaining. Both provider manifests passed the frozen source checks; prior actual cooldowns had elapsed and neither status was recently running. Existing successful replies were retained. No frozen writer or provider source was edited.

Gemini completed C19-T2/T3/T4, reaching 16/16 successful replies. Manual reading: C19-T4 contains four numbers (0.44, 0.64, 117, 144), exceeding the two-number instruction. Its front-knee position stays behind the toe across the stated range; the positive wording does not establish a verdict over mixed cue compliance. No new reply names the knowledge base/the KB/coaching guidance/reference, uses a speed adjective, exceeds four sentences, adds unasked practice advice, or declines a measured verdict despite cue+data. C19-T2 resets and offers a topic choice; T3 asks the athlete to choose a topic. These observations are not ratings.

New Gemini per-turn telemetry:
- C19-T2: 1.921s; 6397 input + 48 output = 6445 tokens; thought tokens unknown (field absent); cache-read 0.
- C19-T3: 1.859s; 6934 input + 41 output = 6975 tokens; thought tokens unknown (field absent); cache-read 0.
- C19-T4: 3.230s; 6794 input + 77 output = 6871 tokens; thought tokens unknown (field absent); cache-read 0.

Qwen C01-T3: 1.308s; 6783 input + 63 output = 6846 tokens. Manual reading: it answers the requested change with an arm-extension cue, but adds that the arm may lag, which is not established by elbow-angle variation alone. No listed style violation observed in this reply; practice advice was asked for.

Qwen C01-T4 stopped on the first real HTTP429 after 0.114s. Groq TPD limit200000, used194718, requested7057; Retry-After767seconds takes precedence over body text12m46.8s. Saved resume_after1792196286.3225715 is October17 00:18:06.322572UTC / October16 20:18:06.322572Toronto. Failed token usage unknown. No later turn was attempted, and no retry will occur in this run.

Final progress: Qwen7/32, Gemini16/16. Raw numbered per-model transcripts and48v6rating rows rendered; all owner columns remain blank, v5 archived comparison retained exactly, v4 archive preserved. Frozen hashes and contiguous stored prefixes verified after both runners exited. Automation remains active for Qwen C01-T4 in a later eligible daily run; completed Gemini replies must never be regenerated. No automatic reply inspection, prompt tuning, application changes, tests, commit/push/default flip or demo regeneration. Final Codex remaining97%five-hour/59%weekly.


## V7 first run — repeated-number review

Only QwenC01-T1 is saved: its145.7–174.4°range is introduced here for the first time, so no within-chain numeric repetition is assessable yet. C01-T2failed429 and laterturnsareunrun. GeminiC01-T1failed429; no Gemini v7 replies yet. No failed turn was skipped or retried. No response was fixed or rated.

- qwen C01-T1: 1.182s; rawreplysaved.
- qwen C01-T2: 0.178s; 429quotaerror,usageunknown.
- gemini C01-T1: 0.385s; 429quotaerror,usageunknown.

Reference research is separate from the writer:knowledge/reference_ranges.md has11owner-editableunapprovedrows,noactivevalues. Knownlimitations include lab3Dphaseaverages versus2Dbookmarks,different interval definitions, CMversuship speed, generalstrength-lungeprescriptions, and inaccessible/changedcitedURLs. No missing values inferred. See the file for exact source/table/population/method details. No coaching rules or thresholds were added from this research.

## Owner shipping decision — v7 preparation, October 16 Toronto

The owner selected qualitative v7 without integrating reference ranges. The frozen prompt/packet/resolver/KB/map/examples and both source manifests are unchanged. Shipping scope is Qwen C01,C03,C13,C19,C15,C17,C12,C14 (32 replies), Gemini C01,C03,C13,C19 (16). Existing successes stay saved; older prompt replies remain archived. No new reply was generated in this preparation run, so there are no new reply-quality observations to add.

Saved actual 429 cooldowns still apply: Qwen C01-T2 may resume after October 17 01:08:08.377370 UTC / October 16 21:08:08.377370 Toronto; Gemini C01-T1 after October 17 23:59:58.880428 UTC / 19:59:58.880428 Toronto. No request was sent before either deadline. The active automation checks every 30 minutes, continues each provider independently, and stops on the first real error without retrying inside that run.

Ten separate test sessions copy a saved supported session and its result into work/live_acceptance_v7. Original SQLite access was read-only and source/copy result hashes match. The isolated app starts and serves its copied session through HTTP with process-only COACH_CORE=new, separate database/video storage, no training/video worker or external storage writes. Input preflight exposes fourteen usable arm readings; this is not a new generated reply. HTTP preflight made zero generation requests and left zero chat runs/jobs.

The new acceptance harness only records raw input/output and injects the two requested provider failures; it does not inspect, repair or shorten replies. A real provider error interrupts the test before spending tokens on automatic fallback; only L10's explicitly synthetic faults test the unchanged production fallback. Those synthetic faults are labeled and do not enter actual quota cooldown accounting. App-committed replies are reconciled after interruptions rather than regenerated. Any rate-limited turn remains pending. The ten real conversations and all eight manual acceptance decisions are still unrun/pending, not passed or failed on setup tests.

Sixty-six distinct focused protocol tests passed (65-test core/history/tracking/technique/harness run, then the updated five-test transport module including one new recovery test); scoped Ruff passed. No quality inference follows from these tests. Existing provider error text truncation at 1000 characters remains a recorded limitation, unchanged. No blocking product bug was found during preparation. Default remains old; no commit, push, real-session write, demo regeneration or range integration.

Preparation correction: the new recovery test initially patched its work/ledger directories but missed its cases-file constant, overwriting only the unrun local acceptance plan with a fixture. No real session or provider call was involved. The erroneous fixture was retained separately, all ten unrun plans were restored, and the test now isolates the cases path as well. All five transport tests then passed with an external before/after hash proving the actual acceptance plan was unchanged. The live-run entry point correctly exited because the prerequisite readings are incomplete. This was a test-fixture error in the new harness, not a change to the frozen coach.

## Owner reorder — live acceptance first

The latest owner request removes the reading prerequisite. Live L01–L10 run first through normal Groq-to-Gemini routing; a Groq quota fallback is not a quality failure. The test recorder now preserves the original provider exception for that router. Saved real cooldowns and providers stopped during the same execution are restored into the child process's circuits. Each invocation attempts one pending conversation turn for manual reading; one execution ID spans the entire owner/scheduled run, so restarting a child does not retry a failed provider inside that run. No frozen product/prompt source was changed.

The reduced post-acceptance reading scope is Qwen C15,C17,C12,C14 plus C01, and Gemini C01 only. The existing v7 C01-T1 remains saved; C03,C13,C19 are dropped from active scope while their artifacts/unrun plan rows remain preserved. No reading generation occurred during the reorder preparation. The 30-minute automation is updated to prioritize live acceptance and normal fallback.

BF01-T1 is a separate completed both-providers-failed probe, not an out-of-order L10 turn. Two explicitly forced HTTP503 exceptions yielded exactly “I couldn't reach the model, try again shortly.” Both records say reached_provider:false. Zero generation calls; core0.332s and HTTP+queue0.755s. Never regenerate this probe. L10 retains its three ordered real turns and must still demonstrate real Gemini state/topic/rep carry-over after the forced Groq failure between T2/T3.

INPUT-R01 copied an actual rejected session into the isolated storage. The normal app coaching_request and frozen packet yielded zero metrics, zero packet measurements and tracking_unsupported. TRACK-A01 called the existing selected-athlete tracker with two ambiguous poses and no selected athlete; it abstained. These are input-only protocol PASS evidence for criterion7, not model-prose quality evidence. A one-off input inspection initially omitted JSON decoding of the existing snapshot serializer; only that inspection script was corrected. No product code or evidence was changed. Other criteria remain pending until live replies support assessment.

Seven focused harness/rating tests passed after the reorder, including original provider error propagation and stops isolated by execution ID. Scoped Ruff passed; actual plan-file isolation was checked. No default flip, commit, push, real-session write, prompt change or range integration. Applicable actual provider cooldowns remain honored.

### Live-first actual run — L01

After the saved Groq deadline elapsed, L01-T1 succeeded through the isolated app's normal queue on Groq qwen/qwen3.8-27b. Core latency1.140s; HTTP+queue1.608s; actual6724input+73output=6797tokens. No fallback; cache-read and thought counts unknown because absent. Manual reading: three sentences, two numbers, no KB/reference/coaching-guidance naming, no speed/smoothness adjective, no unasked practice advice or invented cutoff. Its146–174degree range rounds the actual145.7–174.4readings. The inconsistent verdict matches varying arm extension, rather than calling mixed readings good. This is a manual observation, not an owner rating. The raw reply is unchanged and appended to rating_sheet's separate live section with blank owner columns.

L01-T2 was attempted once after the existing65second pacing. It returned actual HTTP429: Groq TPDlimit200000, used199399, requested6892. Header Retry-After2718seconds takes precedence over body45m17.711999999s. Saved resume_after1792202090.0966842 = October17 01:54:50.096684UTC / October16 21:54:50.096684Toronto. Provider-error latency0.113s; app core0.172s; queue latency unknown. The normal router then skipped Gemini because its actual saved cooldown remains October17 23:59:58.880428UTC. No Gemini generation call occurred. The plain connection reply and full run/trace remain saved as a pending attempt, not a successful model turn. L01-T3/T4 and L02–L10 were not sent. No provider was retried inside this run.

The T2 writer input contains exactly the completed T1 user/assistant pair, with current question “is it good?” and arm/lunge_finish scope. There is no unanswered question in its history. There is no T2 model verdict or repeated-number behavior to assess yet. This quota interruption is not a quality FAIL. Criterion7 has input-only protocol PASS evidence; the other seven remain PENDING with observed-turn details in live_acceptance.md. No proposed prompt/packet/resolver/provider fix is warranted from a provider quota error.

Eight focused harness/rating tests now pass, including a regression that a recovered stored reply cannot lead to a duplicate question or forced failure on the wrong turn; scoped Ruff passed. Frozen manifests still match, default remains old. Two real live-provider attempts in this owner run (one success, one429), zero real Gemini calls, plus the two explicitly synthetic no-generation BF01 failures. Automation remains ACTIVE at30minutes, live-first, preserving normal fallback and actual cooldowns. No reading calls, tuning, default flip, commit or push.


## Frozen v7 live continuation — October 17, 2026, 02:22 UTC

Run-id scheduled-live-v7-20261017T022243Z spans this entire scheduled check. All20 revision provider statuses/mtime plus live status and118 request records (73Groq/45Gemini,9/19real errors) were inspected before starting. No recent running process; Groq deadline elapsed, Gemini actual cooldown retained. Both frozen manifests match.

L01-T2 stored once on Groq qwen/qwen3.8-27b, run54cc179c48114fc8b3271518352aab54. Raw reply: “It is inconsistent. Your arm extension varies across the reps, with some finishing much straighter than others, so it does not yet match the cue of keeping the arm in a consistent line.” Core0.860s; HTTP+queue1.307s;6848input+39output=6887tokens; no fallback. Thought/cache counts unknown (absent fields). Manual reading: plain first-sentence contextual verdict, two sentences, zero numbers, no repeated T1 range, no reference naming, invented threshold/drill/reading, speed/smoothness adjective or unasked practice advice. Arm/lunge_finish remains scoped correctly. The actual conversation_input contains the completed T1 pair and the earlier is-it-good/plain-connection-response pair; no unanswered history. The failed exchange remains visible but is not counted as a successful model turn. Writer packet has actual arm readings and no requested missing topics; no numeric pass/fail threshold was added. No global criterion pass from partial coverage; criterion7 input-only PASS remains, other7 PENDING. Raw reply appended to live rating section with blank owner columns; v6 comparison preserved.


L01-T3 attempted once under the same scheduled run-id, after the harness’s normal65second pacing. Actual Groq429: TPDlimit200000,used195949,requested7217; Retry-After1368seconds takes precedence over body22m47.712s. Saved resume_after1792205205.7407315 = 2026-10-17T02:46:45.740731+00:00 UTC. Provider error0.115s; core0.161s; queue latency unknown. Gemini skipped its actual saved cooldown until2026-10-17T23:59:58.880428UTC; zero Gemini generation calls. Raw report9ffbf5c43ac841a7934429e44deda040 and full request/error retained as pending failed attempt, never counted as T3 completion. Its actual conversation_input retains arm/lunge_finish and three complete user/assistant pairs (T1, prior failed connection exchange, successfulT2); current change request is separate. No T3 practice advice or model-quality conclusion exists. T4/L02–L10 unrun. Stop Groq for the entire check, even after its deadline elapses; no inline retry.

Check stopped 2026-10-17T02:24:27.925001+00:00:2actualGroq requests (1reply/1quotaerror),0Gemini; total main live replies2. Criterion7 input-only PASS, other7PENDING; no criterionFAIL. Both-failed probe untouched, no readings or source/manifest changes. Defaultold, no commit/push; automation remains ACTIVE every30minutes. Raw reply/provider/model/fallback/latency and all8criteria recorded in live_acceptance.md; no owner rating assigned.


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


## Owner approval and default promotion — October 18, 2026

Owner reviewed and accepted the v7.6 hard-fail gate: zero hard failures, all eight criteria PASS including real forced Groq-to-Gemini state carry-over. Owner approved COACH_CORE=new as default with COACH_CORE=old retained for rollback. The existing automation remains paused. No frozen prompt/packet/resolver/KB/map/example change. See [running-app transcript and release verification](v76_release.md). This later authorization supersedes the historical no-default-flip/no-commit/no-push hold above.

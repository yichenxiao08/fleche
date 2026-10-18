# fewshot-v7.2 capacity review — revised 6,700 ceiling

Latest owner request supersedes the previous6200target. Exactly the five approved writer-copy candidates are now omitted. Authored KB is byte-identical to the v7.1manifest; persona/reminder, examples, map, packet and resolver unchanged. Last-two-completed-exchange history and single static reminder remain. No output checker, guard, reply template, sentence deletion or reply rewrite. No default edit, commit, push, schedule creation/change or generation request.

## Recount

Same endpoint: gemini-3.8-flash countTokens, zero generation and no retries. Exact text-token counts below exclude message framing and are not Qwen-tokenizer counts. The prior observation of approximately1%higher counts is empirical, not a guaranteed conversion. This review made11new count-only calls:5recounts and6packet-candidate counts, preserving each raw response/request text/hash in work/live_acceptance_v7/capacity_v72/gemini_counts.json. No Groq tokens spent.

| Checked input | Before five cuts | After five cuts | At or below6,700? |
|---|---:|---:|---|
| L01T4 | 7074 | 6790 | NO |
| L02T3 | 6750 | 6466 | Yes for this constructed input |
| L04T4 | 6773 | 6489 | Yes for this constructed input |
| L06T3 | 6870 | 6586 | Yes for this constructed input |

L01-T4 uses actual archived v7 completed replies/state on the saved supported-session snapshot. L02-T3/L04-T4/L06-T3 have no saved live reply prefixes; their prior question state was deterministically replayed on that snapshot, with empty history. Those three counts remain LOWER BOUNDS, not confirmation that unknown later actual inputs fit. All packet scope/measurements are unchanged: L01recovery/allreps16readings; L02rearleg/allreps7; L04arm/rep2two; L06torso/resetrep/allreps14. No fabricated model reply was saved as completed.

### Realistic-history estimate

Using the actual v7.1L01-T1reply as the model for each prior assistant response gives6790Gemini text tokens, also above6700. This is an ESTIMATE, not an actual v7.2conversation. Reusing identical reply text causes existing already_said deduplication, so it is optimistic relative to unique future replies. The savedT1 is itself three sentences/78Groq output tokens; it does not establish that future replies will be shorter. The generated capacity inputs and estimate are in approved5_recount.json; no provider generation occurred.

## Packet-side proposals — measured, not applied

Baseline is6790 for the checked archived-state L01-T4 request. All candidates keep every per-rep display value, its unit and measurement definition, topic/phase/rep scope, and all safety/coaching text. They affect only a projected writer packet; the complete original packet stays in the saved trace/state. Candidate packet JSON is saved under work/live_acceptance_v7/capacity_v72/packet_proposals_6700.json.

| Candidate | Saving | Result |
|---|---:|---:|
| Omit derived session_comparison ranges | 73 | 6717 |
| Factor repeated unit strings once per feature | 8 | 6782 |
| Ranges + factored units | 81 | 6709 |
| Shorten descriptive packet field names | 6 | 6784 |
| Omit redundant session_overview | 38 | 6752 |
| Omit derived ranges + redundant overview (recommended) | 111 | 6679 |

**Recommended smallest sufficient measured combination: omit only session_comparison and session_overview from the writer projection.** Savings111; result6679, which is21below6700 for this checked request. Neither omission is applied. The underlying full packet/trace/state would remain intact. This is not yet proof that every later actual history fits.

- session_comparison duplicates per-feature minimum/maximum endpoints already present verbatim in rep_readings. Offline inspection confirmed each endpoint and its unit occurs in the retained readings. Definitions, every rep mapping/value and phase remain unchanged. No external target or comparison to another session is discarded.
- session_overview exactly reconstructs as "This session has {len(available_reps)} recorded reps; usable measurements cover {available_session_topics joined}." For this input, it reconstructs byte-for-byte from retained scope.available_reps and availability.available_session_topics. overview_then_clarify and every availability/scope instruction remain.
- Factored units retain display strings including trailing zero precision and an explicit per-feature unit; reverse reconstruction reproduces every original reading exactly. This is a separate proposal, not part of the recommendation.
- Short field names proposal is only measurements→readings, measurement_meanings→meanings, session_comparison→ranges, rep_readings→by_rep. Offline reverse renaming reconstructs the original packet exactly. No instruction text changed.

## Validation, manifests and acceptance state

45focused unittest tests PASS (writer, packet core, citation iteration); Ruff check/format PASS on edited source/tests. Writer-source comparison confirms precisely the five approved excerpts disappeared and no other writer-reference string changed. Protected knee safety, pain referral, power/force and complete drill catalog remain verbatim. All other v7.1frozen file hashes match. v7.2manifest now records the authorized source hash and remains explicitly BLOCKED, not READY; previous candidate manifest preserved. Originalv7/v7.1manifests unchanged.

Per owner step3, stop because L01-T4 remains above6700. No live turns attempted; no chain reset or regenerated reply; v7.1T1remains archived and saved. No actual Groq-vs-Gemini comparison can be added without a new Groq reply. Existing comparison remains actual GroqT1input6929 versus GeminiT2text7096/admission7029forT2, which are not same-request pairs and must not be used to claim a measured offset. Future authorized live replies must each receive same-request countTokens measurement.

Global criteria1–6and8remainPENDING;7retains INPUT-R01/TRACK-A01input-onlyPASS. No new qualityFAIL or globalPASS. L01what-should-I-change remains UNRUN forv7.1/v7.2: no reply to quote or new timing/locked result. Oldv7FAILand owner-acceptedv7.1T1preserved. L10T4remains"why does that matter?". No Gemini generation even though saved eligibility has elapsed; first twoGroqprefix replies are still required. Stop and wait for owner approval of the packet proposal.

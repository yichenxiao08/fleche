# Semantic fallback diagnosis before L05

The failing test was a stale unit-test fixture, not a live quota test. Its request `that bit at the end` passes through the current deterministic resolve_scope as topics=[], resolution_confidence=high, open_clarifying_question=None. resolve_semantic_scope returns immediately unless confidence is low, so the already-mocked _lookup was called ZERO times and the test received no topics. No live request was made by this test. The earlier unresolved diagnosis is now resolved at the test level.

Only the test was changed: construct the low-confidence state the helper actually accepts, mock the lookup, supply a fake in-process credential precondition (not a real key), and explicitly prohibit HostedFallback.invoke. Both accepted ontology and rejected invented-key branches now run offline. All44 tests in test_citation_iteration, test_conversational_writer and test_packet_core pass. Scoped Ruff check/format pass. No product prompt, KB, map, packet, resolver or example changed in this diagnosis.

## Does the app spend Groq tokens resolving scope?

The current new core enters core_packet.run_packet_core, which calls turn_packet.resolve_scope and then build_packet. A repository-wide source search found NO app/script call sites or imports of resolve_semantic_scope/_lookup outside semantic_scope.py itself; the unit test imports it directly. The default old conversation path also has no semantic_scope call. The helper's docstring/test name saying shared is not evidence it is active. Current v7.1 acceptance therefore spends exactly ZERO Groq tokens per turn on this helper, including L05. The writer itself still uses Groq normally.

If directly invoked on eligible low-confidence state with a key, the dormant helper sends one HostedFallback request on a cache miss. This is the SAME settings.groq_api_key, settings.groq_chat_model (qwen/qwen3.8-27b) and Groq completions endpoint as the writer, so it would share that key/model's quota. Its request contains one fixed ontology system message plus JSON of question and previous_topic; it contains no athlete measurements or KB. max_completion_tokens is384; that is an output ceiling, NOT measured consumption. Exact input/output tokens per uncached helper call are UNKNOWN: they vary with input and output, and _lookup discards AIMessage usage metadata. There are no saved actual helper calls from this live acceptance to quote. A cache hit uses0tokens. No live probe was made to fabricate a count.

## What happens on429?

HostedFallback raises HostedError with status and Retry-After. _lookup catches Exception and returns only {error_type: HostedError}; resolve_semantic_scope returns the original unresolved state and trace status clarification_preserved. It preserves an existing clarification; it does not invent a topic. There is no inline retry or Gemini substitution in this helper. It neither consults nor updates the writer's router circuits and does not persist resume_after. The @lru_cache also caches error results for the exact question/previous_topic pair: the same pair remains cached until eviction, cache clearing or process exit, rather than recovering merely because quota resets. Different uncached pairs would make new attempts if someone invoked this helper; changing this behavior or wiring it into production requires separate approval.

An offline mocked429 experiment confirmed two identical lookups caused one mocked provider invocation, two clarification_preserved results, empty topics and the original clarification. ZERO real provider calls or billed tokens. This is protocol diagnosis, not model-quality evidence.

## Is the app currently returning no scope because of rate limiting?

Not on the semantic path: the helper is not called in this app version. The saved v7.1 L01-T1 attempt f247de54154140448de59bcae76cbf5c proves the distinction. Actual conversation_input has question how's my arm extension?, topics=[arm], phase=[lunge_finish], high confidence, no clarification, empty writer history, and14 real finish measurements (seven direction and seven elbow readings). The writer was sent that resolved packet. Groq then returned429; Gemini was skipped for its actual saved cooldown. The app stored the plain connection reply as a pending failed attempt. It did NOT lose the arm topic and did NOT send an empty packet due to a semantic failure. There are no successful v7.1 replies yet.

For a genuinely unresolved subject the writer receives the original question and full writer reference plus scope.topics=[], requested_scope=unresolved_subject, the available-session overview, and no selected measurements. A generic unknown phrase such as that bit at the end currently has high confidence, no structured clarification and overview_then_clarify=false. That is an existing unresolved-scope limitation; no rate-limit cause is demonstrated. For the specific no-topic evaluation is it good? (L05-T1), the packet instead has low confidence, overview_then_clarify=true and actual structured weapon-arm/front-leg/recovery options, with overview measurements. This offline packet comparison is not generated-quality evidence.

## Live-chain impact and approval boundary

L05-T2's my weapon arm resolves deterministically to arm with high confidence, including after the L05-T1 clarification state. It does not need this semantic helper and is not blocked by a Groq semantic lookup. An offline check confirmed that exact wording; the actual chosen L05-T2 option must still come from the live T1 reply. No required live chain has a demonstrated defect from the test failure. Unknown paraphrases without explicit anatomy may retain empty scope; the unused helper would not rescue them in this version. No resolver fix or helper integration is proposed as a prerequisite for the approved exact-question chains. If the owner wants unknown-subject confidence/clarification or semantic integration changed, that requires a separately approved change; it has not been applied.

## Continuation

The approved v7.1 order and30minute ACTIVE schedule remain. Both saved provider cooldowns are still active at this diagnosis: Groq until October16 23:37:47.613789Toronto, Gemini until October17 19:59:58.880428Toronto. No new live request, no turn advancement, no retry. Next turn remains fresh L01-T1. Keep first successful provider per chain except L10's required switch, manual review after each reply, no L05 until reading this diagnosis and choosing a real offered option. Defaultold; gateclosed; no commit/push.

Recorded 2026-10-17T03:17:48.221757+00:00 UTC.

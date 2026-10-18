# Fewshot-v6 reading pass

Owner-authorized prompt changes only: contextual verdicts, coach voice, two-to-four-sentence single-paragraph length, two-number limit, no unasked drills/next steps, no speed adjectives, and six neutral examples pending review. The earlier every-rep/consistent-with verdict instruction was replaced. No authored KB, measurement map, packet, resolver or history changes. Full writer KB retained.

The six examples are shown in [coach_style_examples.txt](../knowledge/coach_style_examples.txt). V5 rating rows are archived as a separate section in [rating_sheet.md](rating_sheet.md), and preserved independently in [rating_sheet_v5_archive.md](rating_sheet_v5_archive.md). No ratings are inferred from owner comments.

Both local per-day attempt caps have been removed from the active v6 harness. Real provider errors and saved actual provider cooldowns govern continuation. Each turn requires a contiguous stored reply prefix; no cross-version replies are imported. Qwen starts C19 from T1 to reach the formerly unrun T4 entirely under v6, then C01,C03,C13, the already-complete C19 is skipped, then C15,C17,C12,C14. Gemini is limited to C01,C03,C13,C19.

## Gemini thinking and latency

The pinned gemini-3.8-flash supports low, medium and high; minimal is unsupported and returns an error. Gemini 3 thinking cannot be fully disabled; budget zero is not a supported thinking-off alternative here. Existing writer requests already use low. No provider parameter was changed and no additional isolated minimal/budget-zero request was sent. [Official model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [GenerateContent thinking documentation](https://ai.google.dev/gemini-api/docs/generate-content/thinking.md).

Saved v5 C01 response inspection:
- C01-T1: 26.002s; 6210 input, 104 reported output, 6314 total; thought tokens unknown (field absent); cache-read tokens 0.
- C01-T2: 13.494s; 6321 input, 63 reported output, 6384 total; thought tokens unknown (field absent); cache-read tokens 0.
- C01-T3: 10.038s; 6392 input, 53 reported output, 6445 total; thought tokens unknown (field absent); cache-read tokens 0.
- C01-T4: 17.458s; 6483 input, 119 reported output, 6602 total; thought tokens unknown (field absent); cache-read tokens 0.

No thought-token count appears in those saved usage or response metadata objects. Absent means unknown, not zero. Thought summaries being disabled does not establish zero internal reasoning, and these artifacts cannot show how much of the delay was reasoning rather than service or network time.

V6 C01-T1 took 3.148s versus v5 26.002s. Both used low thinking. This is a latency observation after the v6 prompt change, not evidence that a thinking change helped; service conditions and prompt content also differ. All per-turn v6 latency and thought telemetry are recorded in the raw transcript and pass notes.

## Free-tier caching

Google lists context caching as free of charge for the Standard free tier of Gemini 3.8 Flash. Implicit caching is automatic for supported models; the documented minimum for 3.8 Flash is 4,096 input tokens. Availability is not a cache-hit guarantee. The saved v5 C01 replies all report zero cache-read tokens. No explicit cache object, paid cache or billing configuration was created. [Official pricing](https://ai.google.dev/gemini-api/docs/pricing), [Official caching documentation](https://ai.google.dev/gemini-api/docs/caching).

## Reading results

In progress. Raw replies are preserved verbatim; owner rating fields remain blank. Requested observations will be recorded by reading the replies, without adding an automatic output checker, gate or text rewriting.

Gemini first stop:13/16successful v6 replies; C19-T2 returned real Google429RESOURCE_EXHAUSTED, free-tier dailyrequestmetric limit20, reportedretry38m48.207246655s. Saved resume_after1792195199.5416937 is October17 00:00UTC / October16 20:00Toronto. This is the provider-reported delay, honored even though it differs from the general documented midnight-Pacific reset; no replacement account/key/model was used. C19-T3/T4 remain unrun because T2 has no stored reply. No retry this run. Raw request/error remains in fewshot-v6/gemini/requests/C19-T2-1.json.

Current first-run stop: Qwen6/32successful (C19complete,C01T1/T2), Gemini13/16successful (C01,C03,C13complete,C19T1). Both stopped independently on their first real429; no503occurred this run. QwenC01T3 andGeminiC19T2 have saved errors; later turns remain unrun. No retries within this run. See [pass_notes.md](pass_notes.md) for per-turn latency/thought telemetry and manual observations.

Qwen retry-after169seconds, resume23:27:15UTC/19:27:15Toronto. Gemini retry-after2328seconds, resume23:59:59.541694UTC/19:59:59.541694Toronto. Header delays take precedence over slightly different bodytextdurations. Provider hints are honored; no reset workaround. Existing daily20:05Toronto automation is updated to frozenv6 only and will resume pending prefixes in a later eligible run, pausing at32Qwen+16Geminisuccessfulreplies for ratings.

48focusedprotocol/producttests and scopedRuffpassed. These checks do not establish response quality. All authoredKB/map/packet/resolver/provider sources are unchanged; coaching functions have identical ASTs to v5. Only authorized prompt constants/examples changed; v6 sources are frozen for this pass. No prompt tuning after reading generated replies.

## Latest continuation — October 16, 2026, 20:06 Toronto

Current progress supersedes the first-run counts above: Qwen7/32successful and Gemini16/16successful. Gemini completed C19-T2/T3/T4. Qwen added C01-T3, then stopped on its first real429 at C01-T4 (TPD200000, used194718, requested7057). Retry-After767seconds gives resume_after1792196286.3225715, October16 20:18:06.322572Toronto. No inline retry or later Qwen turn. Daily continuation remains active until Qwen32/32 as well; no further Gemini generation is needed.

New manual observations and per-turn telemetry are in pass_notes.md. Gemini C19-T4 contains four numbers; no reply was edited or rated. Thought counts remain unknown where absent. Raw transcripts and48v6rating rows are current; blank owner columns and the v5/v4 archives are preserved. Final frozen-source hashes match for both models, with contiguous stored reply prefixes. No frozen writer/provider code or authored KB changed.

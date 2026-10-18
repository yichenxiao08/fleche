# Conversational coach: targeted-feedback reading checkpoint

Read [the numbered conversations](conversational_coach_transcripts.md). Every model reply is retained verbatim, including bad replies. The previous eight-conversation Gemini pass is preserved in `evals/conversational_kb/before_targeted_review`. Current raw transcripts, state and exact per-turn input/output traces are in `evals/conversational_kb/targeted_review`. This is a mixed-provider reading exercise, not evidence that the new prompt beats the old prompt on a controlled Gemini-only comparison.

All 20 conversations / 80 turns are complete: 15 Gemini replies and 65 Groq replies, with every original question preserved. Forty-five focused tests, scoped Ruff and compile checks pass. The authored KB is byte-identical to the supplied file, and the final artifact scan found no API-key literals. No quality acceptance claim follows from those checks.

## Changes made

The persona now asks for optional, relevant next steps; varied openings; a verdict or reason rather than a recap; whole-session ranges before praise; honest rounding; qualitative judgments tied to a named knowledge-base criterion; and exact confidence/source attribution. It explicitly forbids unsupported shoulder-height, smoothness, locking, tactical and speed descriptions. Conversation history and already-given replies are supplied with a repetition reminder. Prior reply numbers are reminders, never measurement evidence.

The packet explicitly lists missing measurement topics and unknown causes. Generic capture advice is no longer shown as an observed reason for missing data. C05 exercises that change. Input-side athlete-selection abstention and rejected/unsupported tracking withholding remain. An observed C13 input bug was also fixed: an unresolved topic had incorrectly generated a no-measurements assertion. The failed C13 chain is retained in the same readable file; its rerun still has a poor first answer, so the code correction alone is not a conversational success.

To fit free-provider limits, the writer packet groups same-feature rep readings, includes each measurement meaning once, avoids duplicate history/memory text and uses compact JSON. The measurement map was shortened without adding criteria; earlier copies are retained. The authored `knowledge/fencing_lunge_knowledge_base.md` is unchanged from the supplied Downloads file. The full knowledge base and full current map go to both providers. There is no retrieval, output checker, number gate, sentence deletion, canned coaching template or local conversational model. No output was rewritten to conceal failures.

## Provider execution and caching

Changing back to the old key did not restore Flash Lite quota. Its first real turn returned a project/model daily-limit error; no quota retry loop followed. The listed 2.5 Flash Lite was unavailable for new users; 3.5 Flash encountered high-demand errors. Gemini 3.8 Flash completed 15 replies, then hit daily quota. Remaining replies used Groq, with model/provider on every turn. GPT-OSS-20B was faster, but produced unsupported targets; GPT-OSS-120B also fabricated and nearly exhausted its free daily allowance. Hosted Qwen 3.8 27B finished remaining cases using its own allowance. This is hosted inference, not a local-model restart. No billing or paid cache was enabled.

Requests were paced, successful prefixes resumed from saved state/history, and errors saved. Input-size rejections led to smaller input packaging rather than unchanged repeated requests. Hosted Qwen initially returned an empty answer with a bounded hidden-reasoning budget; dialogue mode now disables reasoning and caps generation at 768 tokens, below the observed 1,000-output-token/minute allowance. All provider attempts and runtime differences are documented in saved artifacts. Groq's instruct-mode setting is documented in [its model guide](https://console.groq.com/docs/model/qwen/qwen3.8-27b).

The transcript starts with median/p95 latency per answering model. Evaluation scheduling waits are excluded; failed-primary overhead remains included when fallback answered. Groq was spaced 65 seconds apart, so generation times do not represent unlimited back-to-back throughput. Gemini reported zero cache reads. Some Groq replies reported positive cached-token counts, confirming reuse of part of the common prefix; absent fields remain unknown. Exact cache counts are in the transcript and raw replies. No explicit cache resource was created.

## Failures that still need your reading

- C01-T2 invents a high-160-to-170-degree target. C12-T2 invents an above-160 target and uses headers, excessive numbers and unsupported causal interpretation.
- C09-T1 invents an elaborate Dragonfly drill; the following Gemini turn correctly says it is absent from the knowledge base. This is a serious grounding failure, not a successful bait answer.
- C05 states missing measurements and unknown cause correctly, but T4 invents metronome/counting practice and adds unsupported speed/smoothness language.
- C10 gives detailed, ungrounded fleche mechanics, including problematic no-crossing advice. C11 infers arm-first sequence from finish angles, then repeats an invented elbow target.
- C13's first rerun reply still declines rather than resolving the ambiguous question. Its rear-leg follow-up now uses available measurements; the earlier chain incorrectly kept claiming there were none.
- C14 overstates front-knee and recovery quality. C15-T2 answers the toe question directly, but T3 wrongly suggests a side-view video to assess inward collapse.
- C16 exceeds the two-number request. C17 repeats timing values, calls recovery quick/good without a standard, and adds tactical effects. These are unchanged model outputs.
- C18 resolves invalid rep 99 to the requested second rep, and T3 gives a limited verdict without repeating numbers, though T2 is verbose and adds unsolicited drill advice. C19 acknowledges reset, but T3 falls back to general guidance: the unresolved post-reset question receives no measurement rows. Correcting the false missing-data assertion did not fix this remaining packet/resolver gap.
- C20-T2/T3 correctly distinguish missing foot/point evidence from general KB guidance. T1 still exceeds two numbers; T4 treats a small rear-knee spread as a reason to prioritize more extension without establishing that this is the session's most useful focus.

Writer history is also bounded for the free input allowance (last ten messages within 1,800 characters, long assistant replies shortened). The state retains fuller replies than this compact writer view. The repetition instruction therefore does not guarantee that every earlier sentence/advice is still in the model's context; exact retained history is in each trace.

The data-gap packet improvement is visible in C05, but repetition, natural brevity and grounded judgments are not reliable across the fallback models. Unit checks establish the input/routing contract; they do not establish live coaching quality. I do not recommend promoting this core based on these transcripts.

COACH_CORE remains old. No commit, push or default flip. Further quality changes wait for your reading; afterward, change only the observed issue and rerun affected conversations.

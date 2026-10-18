# Conversational coach

The default conversational coach uses the existing LangGraph model/tool loop. The
LLM chooses read-only evidence tools and authors the answer. It can explain,
clarify, compare or continue a coaching discussion in its own words. Tools return
records and library text; they do not supply a required sequence of sentences.

The previous default made the model choose IDs for prewritten sentences. That
gave a strong publication allow-list but constrained conversation and could repeat
the same observation when the athlete asked a different follow-up. It remains
available through `FENCECOACH_VERIFIED_DIALOGUE=true` for explicit protocol
diagnostics. The default and `.env.example` now select the model/tool writer.

## Context and evidence

The original athlete message and recent exchanges go to the model. Persistent
application state supplies a contextual subject, phase, arm role and rep scope.
Rep selectors and phase qualifiers share parsing across state and retrieval.
Changing coverage from one rep to all reps preserves the active subject; narrowing
again replaces the all-rep scope. Explicit named phases take precedence over
movement-implied defaults. A held interval cannot stand in for a finish sample.

The model starts with relevant current-session evidence and can call the available
tools for more measurements, reference comparisons, library guidance and history.
Tool results retain provenance and survive answer repair. The model writes the
reply after using the evidence; it does not select the reply from templates.

## Accuracy tradeoff

Free prose has more potential for unsupported claims than an exact sentence
allow-list. Local checks verify known attribution, scope, numerical evidence and
conversation problems. Gemini additionally uses a separate structured evidence
review. A failed draft can be repaired against the same conversation and retrieved
records; unchecked model prose is not published as streaming text.

These mechanisms reduce known errors. They do not prove semantic correctness,
expert usefulness, or universal natural-language grounding. Local Qwen uses the
local checks without the same Gemini semantic reviewer. Existing provider timeout,
cooldown and fallback behavior remains relevant to completion and latency.

## Evaluation

`scripts/eval_coach.py` distinguishes the natural writer from selector diagnostics:

```powershell
.\.venv\Scripts\python.exe scripts/eval_coach.py --phase after --engine natural --providers gemini --run-id natural-review
.\.venv\Scripts\python.exe scripts/eval_coach.py --phase after --engine verified --offline --suite scope --providers local --run-id scope-protocol
```

Offline selector runs do not establish conversational LLM quality or latency.
The scope suite checks independent raw measurement attribution, phase and role,
persisted rep scope, and visible coverage of eligible requested reps. Available
matching records determine its denominator; it does not count missing measurements
as successful observations. Provider errors and skipped turns receive no quality
credit. Scripted tool-model tests verify wiring and authoring freedom, rather than
pretending to measure a live model's judgment.

Historical results in `coach_audit_results.md` describe the earlier selector
architecture and must not be presented as current natural-writer measurements.

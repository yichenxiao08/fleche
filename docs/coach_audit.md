# Conversational coach audit — 2026-10-13

Baseline is the working tree at audit start, including pre-existing uncommitted
changes. References below are **baseline line numbers**, not claims about the
subsequently edited files. No behavior changes preceded this inspection.

## Workflow and evidence

`coach/conversation.py:106-113` defines messages, accumulated traces, rounds,
calls and token counters. It has no persistent topic, phase, rep or cited-evidence
state. `896-908` builds START → respond → tools → respond, ending on a model
answer; after three rounds or eight calls it forces a plain final answer.
Recursion is limited to 12 (`1020`). Unknown/invalid tool inputs become tool
messages, so they can consume the budget without supplying evidence (`877-894`).

The nominal fast path is no longer fast: `needs_tools = True` at `675` advertises
all tools on every turn. Deterministic question-scoped session evidence is loaded
first (`950-1010`), but library, previous-session comparison and practice history
still depend on model tool selection (`392-667`). A missing feature can lead to
an unnecessary second fetch. Tools can return all matching raw measurements;
there is no aggregate input-token bound. Library fetches return three chunks of
up to 1,000 characters; history is eight practice logs, five sessions with twelve
matching measurements, and six previous reviews. Session notes allow 1,500 chars.
Local context is explicitly expanded to 32,768 tokens (`692`), even for routine
questions; generation is 160 or 240 tokens. Gemini has a 2,048-token ceiling.

`technique_evidence.py:244-376` maps topics to features and phases, but an unknown
topic produces empty filters, meaning **all evidence**, not “nothing relevant.”
Broad snapshots include reference comparisons, benchmark details, phases and
reviews. `latency.py:coaching_session_context` removes wrappers but not records.
Retrieval can therefore overwhelm a small model with irrelevant numbers.

The structured-report graph remains separate (`graph.py:910-948`): gather_metrics
→ retrieve → optional agent/tools → format_report → validate. Its tool loop also
has three rounds/eight calls. Non-demo calls dispatch to conversation (`952-966`),
including Bedrock. Keep its existing validation and demo behavior intact.

## Continuity, prompts and grounding

Repository context (`repository.py:193-236`) stores six complete exchanges as
plain user/assistant text. Conversation construction (`conversation.py:911-948`)
further limits these to 1,600/2,600/6,000 characters; oversized last exchanges keep
the **ends** of the question and answer. Topic qualifiers can disappear.
`turns.py:71-193` resolves selected verdict/numerical patterns and some immediate
rep references; “why does that matter?”, ordinal reps and multi-hop elliptical
follow-ups are not a general state machine. No state survives history truncation.

The session policy asks for session evidence first, but repeatedly permits
general guidance to “fill gaps” without requiring library retrieval (`policy.py`).
The conversation prompt (`714`) discourages library retrieval by default.
`grounding.py:177-197` can require a cue and drill, even without a supported
correction. These instructions compete with the prohibition on invented advice.

Gemini writes structured AnswerDraft then calls a second model as reviewer
(`1030-1129`). A failed review permits a writer repair and another review
(`1147-1245`): up to four model calls before tools. Qwen uses text and regex
checks, not the same semantic contract. `grounding.py:66-175` checks selected
numeric units only when raw metrics exist, using up to 1% tolerance; it excludes
drill doses, checks known phrases, and skips whole negated sentences. It cannot
prove arbitrary advice, numeric attribution, causes or unseen events. Citation
IDs can be valid while the prose changes their meaning. Both paths can throw
CoachAnswerError after repair rather than returning a useful evidence-limited
answer. These are enforcement defects, not simply weak prompting.

## Providers and responsiveness

Settings and ReportRequest default to local although this machine's environment
selects Gemini (`settings.py:17`, `schemas.py:ReportRequest`). Outer failover
(`conversation.py:136-170`) catches ModelAPIError broadly, potentially masking
invalid requests, and probes Ollama synchronously. Inner retry (`755-808`) may
try another Gemini model. Neither has cooldown, Retry-After handling or a
half-open probe. Context is replayed from the request on fallback, so no hidden
provider chat session is required, but unresolved topic/rep state stays unresolved.
Failure reasons are collapsed to “unavailable.” Local failure after cloud failure
can escape as a different exception.

Despite old README claims, generation uses `.invoke` (`759`, `808`) and calls
on_text only after all checks (`1298`). This is a complete-response callback,
not token streaming. The queue has visible stages and a partial-reply field
(`coaching_jobs.py:149+`), but receives nothing early. Startup warms Ollama only
when **local is primary** (`providers.py:56-60`); its warm context is 4,096 while
chat requests 32,768, inviting reloads. Provider timeout is 180 seconds locally.

## Reproduction protocol

`evals/coach_audit/*.json` contains snapshots obtained through the existing API
request builder from saved `data/fencecoach.sqlite3` sessions and cached video
results. Current session has eight evaluated reps and 135 raw observations;
unsupported archival footage has no usable measurements; the imported confidence
review retains its saved single measurement. No numerical measurements were
authored for this evaluation. Fixture hashes and source-code hashes accompany runs.
Each conversation starts with empty chat history. Baseline and after runs use
the identical snapshots and question set. Provider errors are counted separately
from completed-answer quality; unavailable runs never count as correct abstentions.

Detailed timings and reproduction results are in the associated evaluation JSON
and results summary. At initial inspection Gemini was configured; Ollama was not
reachable and no installed executable was found in the known runtime locations.
An unavailable local provider cannot supply an honest hardware latency budget.

## Root causes and proposed tradeoff

1. Retrieval: unknown-topic empty filters broaden evidence; tool selection remains
   model-dependent, including guidance and comparison evidence.
2. Context loss: text-pattern patches and bounded history lack explicit durable state.
3. Prompt/tool design: pressure to always produce advice conflicts with provenance.
4. Grounding: regex denial lists and an LLM reviewer cannot verify all free prose.
5. Provider: broad catches, no circuit breaker, no warm standby, no true streaming.
6. Latency: large packets, tool rounds, mandatory cloud review and possible repairs.

Strict deterministic grounding and unrestricted streamed model prose conflict:
once an invented token is shown it cannot be unshown. Proposed implementation uses
small, provenance-bound answer units and model selection, streaming only completed,
validated units. This sacrifices unrestricted paraphrasing (especially on Qwen)
to make the same enforcement apply to both providers. Measure responsiveness and
report this limitation rather than calling buffered final text token streaming.

## Implemented replacement

The user chose validated phrasings and requested a natural coaching voice. The
replacement is enabled by default (`settings.py:20`). The original LangGraph
writer remains explicitly selectable for rollback and Bedrock compatibility;
its protocol tests pin that legacy path rather than pretending to test the new
selector. The new path removes model-controlled evidence/tool loops.

- `coach/dialogue_state.py:58` resolves topic, role, phase, ordinal/last reps and
  general/history/session scope before retrieval. Typed state is persisted in
  RunRecord and restored by `repository.py:232`; no provider chat session owns it.
- `coach/evidence_packet.py:344` selects exact scoped records, submitted review
  text, matched reference cues and relevant library excerpts. Rep/feature/phase
  attribution stays attached to every value; actual measurement timestamps no
  longer borrow unrelated finish bookmarks. Duration questions use interval
  records. Multi-rep and separate arm-role requests retain each requested scope.
- `coach/verified_dialogue.py:27` builds the packet once, calls one provider and
  publishes only complete validated units. Models choose approved phrase variants;
  raw model prose, invented IDs, measurements and drills cannot be published.
  On a malformed selection the bounded renderer uses supported units without
  another model repair call. Natural variants are authored against source facts.
- `coach/router.py:15` classifies retryable failures; a locked generation lease
  prevents stale concurrent successes from clearing a newer quota cooldown.
  One half-open probe is permitted. Same state and evidence feed Qwen on failover.
  Request/auth errors are surfaced; dual provider failure has a clear message.
- `coaching_evidence_cache.py:128` persists evaluated geometry/reference output,
  invalidating for result content/mtime, capture/windows/review revisions,
  reference inputs and evaluator implementation. Cache hits retain abstentions.
- `scripts/eval_coach.py` and `scripts/coach_eval_oracle.py` independently score
  37 conversations/100 turns using saved raw fixtures. Live, offline, interrupted
  and forced-provider runs are distinct; bounded workers are terminated/joined.

See [measured results and remaining limits](coach_audit_results.md). Baseline
quality coverage is incomplete and live Gemini quota prevented the entire set.
Those unavailable measurements are reported as unavailable, not as successes.

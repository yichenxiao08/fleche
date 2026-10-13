# Establishing reliable coaching

The pipeline and the coach need separate validation. Recognizing a lunge is not evidence that it was performed well. Existing reviewed action intervals support movement regression work; they do not provide expert answers about technique.

## 1. Verify the observation

Use modern solo sport-fencing footage with a fixed side camera, full body visible throughout the action, declared weapon and lead side, and sufficient resolution. Inspect overlays against the actual joints and check complete onset/peak/return sequences. Discard ambiguous identity, occlusion, camera motion, and truncated actions.

The current QA thresholds are conservative engineering rules, not calibrated accuracy probabilities. Validate accepted **and rejected** clips, so the gate is not made to look good by rejecting everything. The original eight golden clips were unsuitable for technique evaluation. Since then, the submitted solo recording and reviewed reference reps 1 and 4 have been connected to phase-specific comparisons. Additional footage is not required to fix chat relevance or use those accepted examples in a focused demo; independent recordings are needed to evaluate how broadly the measurements and corrections transfer.

## 2. Define what each observation can establish

| Evidence | Permitted interpretation | Evidence still missing |
|---|---|---|
| Visible elbow shape at a timestamp | Describe and compare that tracked arm shape | Whether extension began before the attack; continuous arm and foot onset sequence |
| Proposed peak-to-return interval | Compare return intervals under matching conditions | Whether the return was balanced or tactically appropriate |
| Visible knee geometry | Describe the image-plane position | A universal ideal angle, force, pain, or an automatic instruction to bend deeper |
| Foot crossing and forward image motion | Propose a flèche drill interval | Validated action identity, physical speed, end balance, or bout intent |

Coach feedback should connect **observation → interpretation → one cue → one drill → why**. A comparison or practice experiment is useful when a technique fault cannot yet be established. It should be described as an experiment rather than asserted as a correction.

## 3. Build a small expert reference set

Start with a practical pilot of roughly 20–30 clean clips from several athletes and camera setups, including examples with no clear fault. This is a starting collection target, not enough evidence to claim broad reliability.

For each case, a qualified fencing coach records:

- The visible issue, or “no supported correction.”
- The interval and visual evidence supporting that judgment.
- The most useful correction and drill, with the reason.
- What would change the judgment: weapon, drill intent, view, or missing context.

Use disagreements to refine the rubric. A second reviewer on a subset checks that the labels are reproducible. Public licensed footage can supply cases; the user's own footage is not mandatory. Relevant footage and an expert reference are necessary for claims about correctness.

## 4. Test on independent recordings

Separate development and evaluation by athlete, original recording, and camera setup. Adjacent excerpts from one bout are not independent examples. Lock an unseen set before tuning thresholds or prompts.

Report correct-athlete tracking, event precision/recall, timing error, supported versus unsupported clip decisions, and expert-rated feedback separately. For coaching, count unsupported corrections, missed visible faults, specificity, relevance, and usefulness. Include confidence intervals and failure cases when the sample size permits; do not turn citation coverage into coaching accuracy.

## 5. Expand only what passes

Ship narrowly validated solo feedback first. Add flèche quality judgments, varied views, and bout context after they pass their own evaluations. Prompting, RAG, and more automatic labels cannot independently establish that a fencing correction is right.

## What can be automated now

Clip preparation, QA, contact sheets, proposed intervals, evidence extraction, question generation, model comparisons, tracing, regression checks, and review forms are automated. Expert judgment and independent correctness references remain the essential external input. Automatic output checks and model review reduce errors; passing them is not a substitute for independent technique validation.

## General session-evidence workflow

`src/fencecoach/coach/policy.py` defines the shared generation and answer-review contract. These are system-prompt instructions applied to each turn. The workflow resolves the question in the current session, inventories relevant features and phases, retrieves exact evidence, compares matching approved references, and distinguishes an observation from a supported correction. Movement benchmarks live in the session evidence, with their event definitions and provenance; numeric targets are not hardcoded in the motion policy.

The canonical packet retains all reps, measured phases, units, sample information, reference identity, reviewer corrections and benchmark results. Cloud context uses a reversible table encoding; the local model starts with a smaller inventory of all reps/features and calls the same exact-evidence tools for detailed phase or reference rows. Tool filters use feature names, phase names and rep identities chosen by the agent, rather than a question-category gate. `compare_to_baseline` returns approved reference-rep comparisons as well as separately scoped scalar baseline deltas.

Answer repair retains the complete conversation and retrieved tool results. Structured draft citations can be corrected by independent review before publication; checked final citations must refer to actual records. A new test verifies that a failed answer does not lose the evidence its tools retrieved. Tests also exercise unfamiliar feature names, more than 36 reps, phase/unit attribution, reviewer provenance and lossless packet reconstruction.

Live validation on October 12, 2026 produced a reference-based correction for an eight-rep session using Gemini in 3.9 seconds. Further cloud requests reached the API quota. The local mixed-feature check did not pass answer validation during this pass; broad live quality and local latency remain unproven. This result is recorded in `evals/results/coach-general-workflow-2026-10-12.json` and the corresponding local diagnostic file.

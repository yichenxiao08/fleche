# Establishing reliable coaching

The pipeline and the coach need separate validation. Recognizing a lunge is not evidence that it was performed well. Existing reviewed action intervals support movement regression work; they do not provide expert answers about technique.

## 1. Verify the observation

Use modern solo sport-fencing footage with a fixed side camera, full body visible throughout the action, declared weapon and lead side, and sufficient resolution. Inspect overlays against the actual joints and check complete onset/peak/return sequences. Discard ambiguous identity, occlusion, camera motion, and truncated actions.

The current QA thresholds are conservative engineering rules, not calibrated accuracy probabilities. Validate accepted **and rejected** clips, so the gate is not made to look good by rejecting everything. Today, none of the eight golden clips passes. Clean supported footage is the first missing acceptance criterion.

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

Clip preparation, QA, contact sheets, proposed intervals, evidence extraction, question generation, model comparisons, tracing, regression checks, and review forms are automated. Expert judgment and independent correctness references remain the essential external input. The current automatic output guards catch known failure patterns; they are not a complete semantic validator.

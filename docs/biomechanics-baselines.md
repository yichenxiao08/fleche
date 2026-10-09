# Movement references for coaching

Research collected on 2026-10-04. The structured catalog is
[biomechanics-baselines.json](../datasets/biomechanics-baselines.json): eight sources,
ten reference entries, and one action-dataset lead. Short source-backed notes in
`knowledge/` make the references available to the existing coaching retrieval tool.
An already-running process must reload its cached knowledge to see new notes.

## What the references support

| Topic | Useful coaching focus | Interpretation |
| --- | --- | --- |
| En garde | Foot orientation, knees following toes, comfortable starting stance and readiness to move | Teach the conventional position; assess alignment only from a suitable view. Individual stance measurements provide a repeatable personal baseline. |
| Simple foil lunge | Weapon-arm initiation, rear-leg drive, front-leg reception, return to guard | Assess the sequence over time. A single peak frame cannot establish whether the hand started before the foot. |
| Lunge speed | Coordinated propulsion and repeatable execution at a stated distance | Identify which speed is measured: blade, body center of mass, or hip proxy. These cannot be substituted for one another. |
| Advance-lunge | Separate the advance, launch, landing and recovery | Stationary and advance-lunge study values differ; do not combine them into one target. |
| Fleche | Movement-specific launch, crossing and completion events | Available quantitative samples are small and predominantly epee. Do not recommend a crossing-foot fleche for sabre. |

The catalog records study populations, phase definitions, units, source locations and
limitations alongside every number. A group's mean and standard deviation describe
that sample; they are not validated boundaries between good and bad technique.
The introductory approximately right-angle front-knee illustration is a teaching cue,
not a universal requirement for every competitive action.

## Translating this into useful feedback

Keep three statements distinct in the coach's answer:

1. **Observation:** what this clip supports, with the relevant repetition and timestamp.
2. **Interpretation:** how that observation relates to the intended action and a cited coaching principle.
3. **Next action:** one practical cue or comparison exercise, plus what improvement would look like.

When evidence is incomplete, explain the general principle and identify the particular
missing measurement. Do not replace the answer with a generic refusal, invent an
observed fault, or turn a possible practice experiment into a diagnosis.

For example, arm shape at maximum lunge depth can support a comparison between reps.
It cannot establish late arm initiation. To coach initiation timing, measure arm-motion
onset and foot launch separately, and confirm the athlete intended a simple attack.

## Measurement work before automatic grading

- Record weapon, intended action, target distance, handedness, and viewing direction.
- Label arm onset, foot launch, landing, touch where visible, and recovery completion.
- Keep anatomical flexion separate from the app's included joint angles. A straight
  joint is near zero in one convention and near 180 degrees in the other; subtraction
  alone does not fix camera projection or different measurement phases.
- Use calibrated spatial scale for meters per second. Preserve normalized movement
  rates as their own units when calibration is unavailable.
- Run reference footage through the same pipeline, then obtain qualified review of
  technique and event labels. Split evaluation by athlete and source video.
- Evaluate consistency and error before enabling any automatic correction threshold.

Current pose estimates cannot measure ground reaction force, diagnose a strength
deficit, determine spinal curvature, or establish blade contact and fencing priority.

## Data and evidence status

This addition supplies reference material, not a trained technique model or new
ground-truth video labels. The FenceNet paper's reported 652-video footwork dataset
is a lead for movement recognition; its action classes do not label technique quality.
Access and licensing still need to be checked before acquisition.

Two source issues are recorded explicitly in the catalog: conflicting discussion
wording in the Chida paper (use the specified table and methods), and inconsistent
time-unit formatting in the Borysiuk table (use the explicit discussion values).
The foil arm-sequence citation was corrected to FIE t.83; t.101 concerns sabre.

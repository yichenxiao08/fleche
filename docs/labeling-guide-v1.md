# Labeling modern fencing footage — version 1

Watch the selected athlete at normal speed, then inspect boundaries with slow playback.
Use a stable, pseudonymous athlete ID across recordings; use separate recording-session
and camera-setup IDs. The primary track must name the athlete measured by the prepared
crop. Labels on another track can be saved but are not exported against that crop.

## Movement intervals

Use half-open intervals: the start belongs to the action; the end begins the next state.
Adjacent labels can share a boundary. Do not overlap labels on the same track and layer.

| Class | What to label |
| --- | --- |
| En garde | A recognizable guard with no completed traveling step; small adjustments are allowed. Ordinary standing/waiting belongs to other. |
| Advance | A forward fencing step from the first initiating foot movement through the following foot's repositioning. Confirm facing. Split repeated steps when their boundaries are visible. |
| Retreat | A backward fencing step from the first initiating foot movement through the following foot's repositioning. Confirm facing. |
| Lunge | The leg-driven lunge from front-foot launch through arrival at the extended stance. A preceding advance and subsequent recovery receive their own labels. Arm preparation can start earlier: mark that as an event. |
| Fleche | A running attack with forward body commitment and crossing of the feet. Label the visible action only; stop when the athlete resumes ordinary locomotion or exits view. Mark unsure if indistinguishable from running. |
| Recovery | The return from a lunge toward recognizable en garde, ending once the recovery step and repositioning finish. |
| Other | Visible walking, turning or other movement outside the supported classes. Useful negatives. |
| Unknown | The action cannot be identified. Excluded from action training. |

Existing bounce, jump and shuffle classes remain available; do not substitute them for
unclear footage. These labels describe actions, never whether the technique was correct.

## Event markers and exercise context

Markers are independent timestamps, stored separately from action intervals:

- **Arm-motion onset:** first visible sustained weapon-arm extension toward the intended target.
- **Foot launch:** first frame where the front foot visibly leaves its support in the lunge. Do not infer from stance width alone.
- **Landing:** first visible front-foot contact after launch; record uncertainty when contact is obscured.
- **Stance peak:** maximum visible foot separation for this repetition. This can differ from landing.
- **Recovery complete:** arrival back in recognizable guard after recovery.

Use the activity layer for setup, exercise, between-reps, rest and exit. Setup covers
preparation before an exercise set; between-reps covers short resets within a set; rest
covers a deliberate break; exit covers leaving the exercise area. If the intent is
unclear, leave a draft. A bout stoppage is not automatically a between-reps interval.
Technique-quality labels are not part of this schema. Blade and tactical tracks remain
separate; confirmed tactical labels require coach review and visible opponent context.

## Review and exclusion

**Accept (confident)** only after watching the actual athlete and boundaries. **Mark unsure**
records a review but excludes it from training. Reject incorrect proposals; use the interval
editor to correct a label before accepting it. Record boundary uncertainty in milliseconds.
One-frame seeks are approximate timestamp seeks, especially for variable-frame-rate video.

Exclude occlusion, out-of-frame motion, ambiguous athlete identity, moving camera,
non-modern footage or otherwise unusable intervals. Exclusion does not erase the record.
For an event you cannot verify, leave it provisional, mark unsure or reject it.
Never promote an assistant or heuristic suggestion by changing its origin to human.
The system preserves `suggested_by` and adds `reviewed_by` and the server review time.
Reviewer names are local attribution; they are not authenticated accounts.

## Fast workflow

N/P selects a draft in review priority order; Space plays/pauses; arrows step; I/O marks
interval boundaries; C selects the class. Apply interval edits, then use A to accept or
R to reject. Buttons mark events at the playhead. Save persists labels and revision history.
Unsaved interval edits must be applied or cleared before switching clips or saving.

Schema: `label_schema_v1`, defined in `src/fencecoach/dataset_labels.py` and exported as
`datasets/label-schema-v1.json`. Legacy records keep their source and stable IDs, but
their certainty defaults to unsure until explicitly reviewed. Re-run preparation after
review to refresh the trainer export; stale exports are rejected by the training path.

Collect across athletes, recording sessions and camera setups. The initial phone-video
readiness protocol asks for 150 usable windows per common class (50 for the rarer fleche
class), six training athletes, two held-out athletes, three camera setups, and at least
three independent source groups per class. It also asks each athlete to contribute at
least three original videos across two sessions. These are conservative collection and
evaluation targets chosen for this project; they are not published fencing standards,
proof of model quality, or minimums validated by an empirical learning curve. The dataset
page and `scripts/train_gestures.py` share this gate. Candidate training only begins once
the report passes, then promotion separately checks athlete-held-out per-class recall,
macro F1, a majority-class baseline and confidence calibration. A second reviewer should
independently review an overlap sample before labels are treated as reliable.

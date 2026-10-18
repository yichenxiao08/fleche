# v7.6.1 evidence regression fixes

Owner feedback exposed two regressions beyond the reviewed v7.6 acceptance replies:
usable local geometry was suppressed by a whole-clip quality flag, and saved
reference-lunge comparisons were absent from the conversational writer input.
The reach follow-up also lost its knee topic because `kinee` was not recognized.

The new input path retains usable local reps while excluding unsupported or
unavailable reps and those without geometry. An explicit evidence rejection still
withholds all measurements and comparisons. The normal HTTP request no longer
requires a torso reading to preserve usable local knee geometry. Whole-clip
metrics remain excluded when that clip is rejected. Generic camera advice is
never treated as proof of a missing measurement's cause.

Unqualified finish questions include the producer's finish and held-finish
readings with their original phase labels. Explicit phase questions stay exact.
Reference comparisons are separate records, joined by rep, feature, phase and
unit; reviewer corrections and camera-comparison limitations accompany them.
They are examples, not universal numerical pass/fail boundaries. No unapproved
reference_ranges.md is loaded. The writer is instructed to use an available
comparison rather than reduce every assessment to consistency, and not to infer
distance travelled from knee bend. Output is still authored once by the provider
without checking or rewriting it.

Saved-data verification (no provider requests): the first reported session has
local hold geometry despite whole-clip rejection. The second has actual front
knee readings 116.6–144.3 degrees and saved finish references 88.6–98.5 degrees.
Those ranges describe this athlete's examples, not calibrated physical targets.
The typo-containing knee/reach question now selects front-leg and distance topics;
the knee evidence remains available while distance is reported unmeasured.

Seven focused regression tests cover the HTTP request, actual writer input,
reference scope and corrections, rejection boundaries, mixed finish phases and
the typo-containing follow-up. All 341 tests pass with the new default and mocked
providers; Ruff check passes across src, tests and scripts.
All model replies in those tests are mocked. No new live model quality claim is
made. Frozen v7.6 transcripts, rating sheets and manifests remain historical;
the runtime prompt revision is v7.6.1. Provider order and rollback remain unchanged:
set COACH_CORE=old and restart for the legacy core.

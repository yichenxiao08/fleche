# Core app implementation — 0.5

Authentication remains the final product stage. The local app is a single-athlete workspace.

## Implemented flows

1. Record silently with browser camera APIs or upload a clip (2 minutes / 200 MB).
2. Draft clips persist in IndexedDB across reloads. Analyze uploads a draft to the server.
3. A durable queue leases the clip to an independent, supervised pose worker. Multiple workers
   claim different jobs; heartbeats prevent another live worker’s job from being reclaimed.
4. Pose sampling and smooth video encoding run separately. The review includes landmark overlays,
   knee/arm/torso charts, recovery proposals, and editable onset/peak/return timestamps.
5. Save visible measurements even if no complete lunge/recovery is proposed. Each accepted interval
   includes recovery timing, knee and elbow angles at peak, front-knee flexion from movement onset
   to peak, torso tilt, normalized hip recovery speed, and arm-extension ratios at movement onset
   and peak when the necessary landmarks are visible.
6. Specify weapon arm, front leg, screen-facing direction and whether the first 1.5 seconds show
   stationary guard. Confirmed initial guard gets a separate measurement summary. Footwork
   translations near the stance baseline are proposals, not validated gesture classifications.
7. Ask the local or cloud LLM a question. Live coaching is a normal LangGraph conversation with
   recent user/assistant turns persisted per session. Tools can read current measurements, inspect
   grouped reviewed intervals and timestamps, compare baselines/sessions, retrieve notes, and read
   practice history. Plain explanations need no tools or report-formatting call. A requested drill
   can create a cited draft card for the athlete to save. Tool use is bounded to three rounds and
   eight calls, followed by a final answer without tools if the budget is reached.
8. Coaching requests are queued with persistent status and stage updates. Reload reconnects to a
   pending request. Saved reviews provide context for follow-up questions.
9. Save a recommended drill to the training library and log its practice. Daily logs support date,
   minutes, effort, focus, notes and a linked video review; they can be edited or deleted. Progress
   uses practice dates and avoids counting the linked video review twice.

## Model training

Pose extraction uses the pinned pretrained MediaPipe model. The video pipeline searches the clip
for a stable en-garde baseline, then proposes stance expansion and return cycles. Nearby cycles are
grouped into suggested sets; setup, between-rep, rest and exit intervals are kept as separate phase
suggestions. Knee flexion and asymmetry provide simple lunge cues. These are review prompts, not
validated action classifications, and walk-in footage before the stable guard is excluded.

The review screen supports human gesture labels (en garde, advance, retreat, lunge, recovery and
other) and activity-phase labels (setup, exercise, between reps, rest and exit). An activity model
is separate from the gesture model and requires its own reviewed labels and independent videos.
Neither model is trained from an unreviewed proposal or the single public demo.

The coaching LLM is not fine-tuned on pose labels. A measurement-reading tool can prepare a
brief from repeated measurements and the confirmed capture profile. Direct athlete-specific
assessment questions read current evidence before the chat response; general explanations do
not. The local chat defaults to Qwen2.5 3B after live Qwen3 checks emitted deliberation instead
of final answers under this runtime. Read tools do not need user confirmation. User/assistant
history stores the last six conversational exchanges for this session; old reports and sample
responses are not inserted as live conversational turns. Evidence disclosures describe which
sources were consulted, not proof that the model interpreted them correctly.

Live chat now separates supported observations, optional experiments, and conclusions that
the current measurements cannot establish. It bounds recent chat text and omits bulky metric
provenance from model input. Ordinary chat uses one short generation and streams checked
sentences to the UI. Unsupported advice is replaced without a second generation and its
draft practice card is discarded. Peak elbow comparisons include timestamps even in older
saved reviews. The model is warmed and kept loaded; complex requests retain the tool graph.
This is a narrow check for observed failure modes, not a guarantee of factual correctness.

`scripts/train_gestures.py --task gesture` trains a temporal logistic-regression classifier from reviewed pose
windows (750 ms by default, configurable). It requires at least two classes, twenty usable windows
per class and three independent source cohorts or events per class. Duplicate source bytes remain
in the same split. Related clips, crops and re-encoded copies must not be supplied as independent
groups. The trainer exports JSON weights and a model
card, including source licenses, per-class results and the held-out video hashes. It does not load
pickled models. `--promote` requires held-out macro F1 >= 0.75; otherwise the existing active model
is preserved. This threshold is a development gate, not a claim of general accuracy.

```powershell
.\.venv\Scripts\python.exe scripts/train_gestures.py --data data/videos --output models/gestures.json
# After reviewing the candidate’s held-out results and data quality:
.\.venv\Scripts\python.exe scripts/train_gestures.py --data data/videos --output models/gestures.json --promote
```

A promoted gesture model adds reviewable, timestamped movement predictions to future analyses. The
same trainer accepts `--task activity` and trains `models/activity.json` from reviewed phase labels.
Missing pose features cause abstention. Scores are uncalibrated; expert annotations and independent
recordings are still needed to establish generalization.

## Scaling and storage

Local development uses SQLite and one embedded worker per service. PostgreSQL is supported through
`FENCECOACH_DATABASE_URL`; short queue transactions use an advisory lock for claim/update integrity.
API replicas and `python -m fencecoach.worker` processes can run independently.

The Docker Compose stack contains PostgreSQL, an API, a separate worker and Ollama. Local Docker
volumes share video artifacts on one Docker host. For workers on separate machines, use an existing
private S3 bucket with standard AWS credentials. Sources are uploaded before queueing; workers
download sources into local caches and publish versioned analysis artifacts. The database stores the
active artifact version, so stale attempts do not replace an accepted result. The API serves cached
artifacts with range support. Labels are stored in the job record and exported with source credits.
No bucket or cloud account is created automatically.

```powershell
# Install the pose model on the host first; models is mounted read-only.
.\.venv\Scripts\python.exe scripts/setup_video.py
# Set FENCECOACH_POSTGRES_PASSWORD in .env to a URL-safe secret, then:
docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5:3b
docker compose up -d --scale worker=3
```

Cloud deployment and throughput/load evaluation have not been performed. Ollama throughput is
bounded by the model hardware; use a configured cloud model or adequate inference hardware for
larger workloads. PostgreSQL/S3 support and worker replicas are deployment building blocks, not an
established production capacity claim. Authentication, per-user isolation, quotas, retention and
public deployment remain subsequent work. The Compose API port stays bound to localhost.

## Measurement limits

Angles are image-plane estimates. Torso tilt cannot establish spinal straightness. Wrist landmarks
cannot locate the blade or check weapon contact. Recovery speed uses torso lengths per second,
not metres per second. Movement onset is a reviewed kinematic marker, not tactical attack intent.
Visibility/presence is a tracking-quality proxy, not a calibrated accuracy probability. Fencing is
asymmetric; equal left/right knee angles or arm extension are not a universal goal.

The public MIT clip retains its attribution and CC BY-NC-SA 3.0 license. It is development/demo
material and does not count toward the athlete’s practice goal.

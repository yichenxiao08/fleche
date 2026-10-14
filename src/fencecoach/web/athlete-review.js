import { formatCoachText } from "./coach-text.js";
import { e, icon, primary, secondary, heading, photo } from "./ui.js";
import { getClipURL } from "./media.js";
import {
  sessionPicker,
  emptySession,
  selectedMetrics,
  measurementTable,
} from "./components.js";
import { frameStepControls } from "./replay-player.js?v=20261012-startup-fix-v1";

const time = (ms) => {
  const seconds = Math.max(0, ms / 1000);
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
};
const phaseNames = {
  starting_guard: "Ready position",
  lunge_drive: "Moving into the lunge",
  lunge_hold: "Holding the lunge",
  lunge_finish: "Lunge finish",
  active_recovery: "Recovering",
  recovery_peak: "Deepest recovery bend",
  returned_guard: "Back in guard",
};
const metricNames = {
  front_knee_angle: "Front knee",
  rear_knee_angle: "Back knee",
  projected_torso_tilt: "Torso lean",
  weapon_arm_direction: "Sword arm",
};

function drillBenchmarks(rep, showHeading = true) {
  const benchmarks = rep.drill_benchmarks;
  if (!benchmarks || benchmarks.status === "unavailable") return "";
  const timing = benchmarks.timing || {},
    reach = benchmarks.reach || {},
    rear = benchmarks.rear_foot || {};
  const timingText =
    timing.status === "estimated"
      ? `${timing.duration_seconds.toFixed(1)} seconds · ${timing.category === "borderline" ? "Near a timing boundary" : timing.category}`
      : "Foot lift or stable finish not established";
  const reachText =
    reach.status === "estimated"
      ? `${reach.feet_separation_leg_lengths.toFixed(2)} leg lengths`
      : "Feet separation not established";
  return `<section class="athlete-benchmarks" aria-label="Lunge timing and reach checks">${showHeading ? "<h3>Movement checks</h3>" : ""}
    <dl><div><dt>Lift to stable finish</dt><dd>${e(timingText)}</dd></div>
    <div><dt>Feet separation · guide ≈ 2 leg lengths</dt><dd>${e(reachText)}</dd></div>
    <div><dt>Rear-foot travel · guide 12 inches</dt><dd>${rear.status === "relative_only" ? "Needs a distance scale" : "Not established"}</dd></div></dl>
    <details><summary>How estimates work ${icon("chevron")}</summary><p class="helper">Timing compares front-foot lift to a stable finish against your rough practice benchmarks: fast below 0.4 seconds, typical from 0.4 to 0.5, and slow above 0.5. Reach uses side-view foot positions and leg length. Rear-foot travel needs a known scale in the frame.</p>
    ${rear.status === "relative_only" ? `<p class="helper">Tracked rear-foot travel: ${rear.forward_torso_lengths.toFixed(2)} torso lengths forward. A known distance in the image is needed to compare it with 12 inches.</p>` : ""}
    ${timing.status === "estimated" ? `<button class="text-action" data-review-seek="${timing.front_foot_lift_ms}">Watch foot lift</button> <button class="text-action" data-review-seek="${timing.stable_finish_ms}">Watch stable finish</button>` : ""}</details></section>`;
}

function referenceComparison(rep) {
  const comparison = rep.reference_comparison;
  if (!comparison) return "";
  const refs = comparison.references || [];
  const priorities = comparison.coaching_priorities || [];
  const rows = (comparison.rows || []).filter((r) => r.phase === "finish");
  return `<section class="athlete-reference-comparison"><h3>Compare with your good reps</h3>
    ${comparison.status !== "available" ? `<p>${e(comparison.reason || "No matching measurements are available for this rep.")}</p>` : priorities.length ? `<ul class="movement-feedback-list">${priorities.map((p) => `<li><p>${e(p.what_to_try)} ${e(p.reason)}</p><button class="movement-feedback-play" data-review-seek="${p.watch_at_seconds * 1000}" aria-label="Jump to finish and pause at ${p.watch_at_seconds.toFixed(1)} seconds" title="Jump to finish and pause at ${p.watch_at_seconds.toFixed(1)} seconds"><span>${p.watch_at_seconds.toFixed(1)}s</span>${icon("play")}</button></li>`).join("")}</ul>` : "<p>No clear correction emerged from the supported reference comparisons. You can still compare the movement with your coach.</p>"}
    ${rows.length ? `<details class="athlete-measurements"><summary>Side-by-side measurements ${icon("chevron")}</summary><table><thead><tr><th>At the finish</th><th>This rep</th><th>Reference median</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${e(metricNames[r.metric] || r.metric.replaceAll("_", " "))}</td><td>${r.current.toFixed(1)} ${e(r.unit)}</td><td>${r.reference_median.toFixed(1)} ${e(r.unit)}</td></tr>`).join("")}</tbody></table><p class="helper">These describe the selected reference examples. A difference is not automatically a fault. Camera perspective can affect the comparison.</p></details>` : ""}
  </section>`;
}

function repDetail(rep) {
  if (!rep)
    return '<p class="helper">No per-rep breakdown is available for this session. You can still watch the recording and ask the coach a question.</p>';
  const phases = rep.phases || {};
  const phaseOptions = Object.entries(phases).filter(([, phase]) =>
    Number.isFinite(phase.representative_ms ?? phase.start_ms),
  );
  const finish = phases.lunge_hold || phases.lunge_finish;
  const readings = Object.entries(metricNames).flatMap(([key, name]) => {
    const metric = finish?.measurements?.[key];
    return metric && Number.isFinite(metric.value)
      ? [
          `<div><span>${e(name)}</span><strong>${metric.value.toFixed(1)}<small>°</small></strong></div>`,
        ]
      : [];
  });
  const comparisonMode = Boolean(rep.reference_comparison);
  const hasBenchmarks = Boolean(
    rep.drill_benchmarks && rep.drill_benchmarks.status !== "unavailable",
  );
  const findings = comparisonMode ? [] : rep.findings || [];
  return `<section class="athlete-rep-detail" aria-label="Selected repetition">
    <div class="athlete-section-heading"><div><p class="eyebrow">YOUR MOVEMENT</p><h2>Rep ${rep.rep_number}</h2></div></div>
    ${
      phaseOptions.length
        ? `<div class="athlete-phase-control"><label for="review-phase-picker">Jump within this rep</label><select id="review-phase-picker" data-review-phase-picker><option value="">Choose a moment</option>${phaseOptions
            .map(([key, phase]) => {
              const at = phase.representative_ms ?? phase.start_ms;
              return `<option value="${at}">${e(phaseNames[key] || key)}${Number.isFinite(at) ? ` · ${time(at)}` : ""}</option>`;
            })
            .join("")}</select></div>`
        : ""
    }
    ${referenceComparison(rep)}
    ${comparisonMode && hasBenchmarks ? `<details class="athlete-measurements athlete-extra-checks"><summary>Lunge checks · timing, reach & rear-foot travel ${icon("chevron")}</summary>${drillBenchmarks(rep, false)}</details>` : comparisonMode ? "" : drillBenchmarks(rep)}
    <div class="athlete-findings">${comparisonMode ? "" : findings.length ? findings.map((f) => `<article><h3>${e(f.observation)}</h3><p>${e(f.cue)}</p>${Number.isFinite(f.evidence_ms) ? `<button class="text-action" data-review-seek="${f.evidence_ms}">See this moment · ${time(f.evidence_ms)} ${icon("arrow")}</button>` : ""}</article>`).join("") : `<p>${rep.status === "unavailable" ? "There isn't enough clear body detail to assess this rep. Watch it yourself or try a clearer recording." : "The automatic checks did not flag an issue in this rep. This does not confirm that every part of the technique is correct."}</p>`}</div>
    ${readings.length ? `<details class="athlete-measurements"><summary>Measurements at the lunge finish ${icon("chevron")}</summary><div class="athlete-readings">${readings.join("")}</div><p class="helper">${phases.lunge_hold ? "Values summarize the visible hold." : "No steady hold was detected; these values use a short window around the lunge finish."} Angles are estimates from this camera view.</p></details>` : ""}
    ${rep.unavailable?.length ? `<details class="athlete-measurements"><summary>What couldn't be assessed ${icon("chevron")}</summary><ul>${rep.unavailable.map((note) => `<li>${e(note)}</li>`).join("")}</ul></details>` : ""}
  </section>`;
}

export function updateReviewedRep(state) {
  const reps = state.reviewResult?.technique_evaluation?.reps || [];
  const index = Math.min(
    Math.max(state.reviewRepIndex || 0, 0),
    Math.max(0, reps.length - 1),
  );
  const rep = reps[index];
  if (!rep) return;
  const detail = document.querySelector(".athlete-rep-detail");
  if (detail) detail.outerHTML = repDetail(rep);
  const picker = document.querySelector("[data-review-rep-picker]");
  if (picker) picker.value = String(index);
  const video = document.getElementById("replay-video");
  if (video && Number.isFinite(video.duration)) {
    video.pause();
    video.currentTime = Math.min(
      (rep.action_start_ms ?? rep.lunge_ms) / 1000,
      video.duration,
    );
  }
}

export function athleteReview(state) {
  if (!state.session)
    return `${heading("REVIEW YOUR PRACTICE", "Watch. Understand. Improve.")}${emptySession()}`;
  const session = state.session;
  const result = state.reviewResult;
  const reps = result?.technique_evaluation?.reps || [];
  const index = Math.min(
    Math.max(state.reviewRepIndex || 0, 0),
    Math.max(0, reps.length - 1),
  );
  const rep = reps[index];
  const clip = session.video_job_id || getClipURL();
  let footage = clip
    ? `<video id="replay-video" data-session-id="${e(session.session_id)}" controls playsinline preload="metadata"></video>${session.video_job_id ? '<canvas id="review-overlay" aria-hidden="true"></canvas>' : ""}`
    : session.is_demo
      ? photo(
          "sample-replay",
          '<span class="image-badge">SAMPLE IMAGE · NOT YOUR FOOTAGE</span>',
        )
      : '<div class="no-footage"><h2>No video attached</h2><p>Upload a practice clip to see your movement here.</p><button class="secondary-action" data-go="record">Upload a video</button></div>';
  const metrics = selectedMetrics(state);
  const fallback =
    !reps.length && metrics.group.length
      ? `<div class="athlete-rep-select"><label for="review-moment-picker">Jump to moment</label><select id="review-moment-picker" data-review-metric-picker>${metrics.group.map((m, i) => `<option value="${i}" ${state.metricIndex === i ? "selected" : ""}>Moment ${i + 1}${Number.isFinite(m.start_ms) ? ` - ${(m.start_ms / 1000).toFixed(1)}s` : ""}</option>`).join("")}</select></div>`
      : "";
  const latest = state.runs.find((run) => run.response_kind !== "conversation") || null;
  const saveConfirmation =
    state.reviewSavedSessionId === session.session_id
      ? `<div class="saved-practice-confirmation" role="status"><strong>Practice saved</strong><span>${e(session.title)} is in your practice log. Your reviewed rep intervals and video measurements are attached to this session.</span></div>`
      : "";
  return `${heading("REVIEW YOUR PRACTICE", "See what to work on.", '<button class="secondary-action" data-go="record">' + icon("upload") + "New video</button>")}

    ${saveConfirmation}
    <div class="athlete-review-layout"><section class="athlete-video-column">
    <div>
    ${sessionPicker(state)}
    <div class="replay-view">${footage}</div></div>

      ${clip ? frameStepControls("replay-frame-controls", result?.preview?.fps_hint || 30) : ""}
      ${session.video_job_id ? `<div class="athlete-video-tools"><button class="text-action" data-video-overlay aria-pressed="${state.videoOverlay}">${icon("target")}Body overlay ${state.videoOverlay ? "on" : "off"}</button><a class="text-action" download href="/api/videos/${e(session.video_job_id)}/preview">${icon("download")}Download video</a></div>` : ""}
      <details class="athlete-session-details"><summary>Session notes & detailed measurements ${icon("chevron")}</summary>${session.notes ? `<p>${e(session.notes)}</p>` : '<p class="helper">No practice note was added.</p>'}${measurementTable(session)}${result?.source_credit ? `<p class="helper">${e(result.source_credit)}</p>` : ""}</details>
    </section><aside class="athlete-review-aside"><div class="athlete-rep-review-pane">
      ${reps.length ? `<div class="athlete-section-heading rep-picker-heading"></div><div class="athlete-rep-select"><label for="review-rep-picker">Jump to rep</label><select id="review-rep-picker" data-review-rep-picker>${reps.map((item, i) => `<option value="${i}" ${i === index ? "selected" : ""}>Rep ${item.rep_number} · ${((item.action_start_ms ?? item.lunge_ms) / 1000).toFixed(1)}s</option>`).join("")}</select></div>` : fallback}
      ${repDetail(rep)}
    </div>
      <section class="athlete-coach-card"><p class="eyebrow">YOUR NEXT STEP</p><h2>${latest ? "From your coach" : "Talk it through"}</h2><p>${e(formatCoachText(latest?.report?.summary || "Ask about this rep, compare your recoveries, or choose one thing to practice next."))}</p><div class="athlete-coach-actions">${primary("Ask the coach", 'data-go="coach"')}${secondary("Practice another set", 'data-drill="lunge"')}</div>${latest?.report?.next_drill ? `<details class="athlete-measurements"><summary>Next practice ${icon("chevron")}</summary><h3>${e(latest.report.next_drill.name)}</h3><ol>${latest.report.next_drill.steps.map((step) => `<li>${e(step)}</li>`).join("")}</ol></details>` : ""}</section>
      ${session.video_job_id ? `<a class="text-action" href="/coach-review/${e(session.video_job_id)}">Have a coach review these reps ${icon("arrow")}</a>` : ""}
    </aside></div>`;
}

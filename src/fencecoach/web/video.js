import { motionPanel, repDetails } from "./motion.js";
import { api, downloadJSON } from "./api-client.js";
import { e, icon, heading, primary, secondary, label } from "./ui.js";
import { refreshSessions } from "./store.js";

const videoPath = (id) => `/api/videos/${encodeURIComponent(id)}`;
export const previewURL = (id, result) =>
  `${videoPath(id)}/preview?v=${encodeURIComponent(result?.preview?.revision || "legacy")}`;
export const posterURL = (id, result) =>
  result?.preview
    ? `${videoPath(id)}/poster?v=${encodeURIComponent(result.preview.revision)}`
    : "";
let controls,
  pollTimer,
  jobEpoch = 0;
export function analysis(state) {
  const job = state.videoJob,
    result = state.videoResult;
  if (!job)
    return `${heading("MOVEMENT ANALYSIS", "Bring your practice.<br>See your return.")}<div class="empty-session"><p>Start with a short side-view clip or MIT’s public fencing demonstration.</p>${primary("Choose a clip", 'data-go="record"')}${secondary("Analyze public demo", "data-video-demo")}</div>`;
  if (!result)
    return `${heading("MOVEMENT ANALYSIS", "One rep at a time.")}<section class="analysis-status side-card"><p class="eyebrow">${e(job.title)}</p><h2 id="analysis-stage">${e(job.stage)}</h2><progress id="analysis-progress" max="100" value="${job.progress}"></progress><p id="analysis-detail" role="status">${job.status === "failed" ? e(job.error) : `${job.progress}% · You can leave this screen while analysis runs.`}</p>${job.status === "cancelled" ? secondary("Choose another clip", 'data-go="record"') : job.status === "failed" ? secondary("Retry analysis", "data-video-retry") : '<span class="spinner"></span><button class="text-action" data-video-cancel>Cancel analysis</button>'}${secondary("Back to practice", 'data-go="record"')}</section>`;
  const finished = job.status === "completed";
  const qa = result.quality_gate;
  const unsupported = qa && !qa.coaching_allowed;
  const coachReviewLink = `<p><a class="secondary-action" href="/coach-review/${encodeURIComponent(job.job_id)}">Coach feedback · review frame by frame</a></p>`;
  const qualityPanel = (qa ? `<section class="side-card" role="status"><p class="eyebrow">AUTOMATIC CLIP CHECK</p><h2>${e(qa.verdict.replaceAll("_", " "))}</h2>${qa.issues.map(i => `<p>${e(i.tip)}</p>`).join("")}${unsupported ? '<a href="#record" data-go="record">Film another clip</a>' : ""}</section>` : "") + coachReviewLink;
  return `${heading("MOVEMENT REVIEW", "See each rep.<br>Compare your sets.")}${qualityPanel}<div class="analysis-topline"><span>${e(job.title)}</span><span>${job.source === "mit_ocw" ? "PUBLIC DEMONSTRATION" : "YOUR FOOTAGE"}</span></div><div class="analysis-layout"><section><div class="analysis-player" style="aspect-ratio:${result.width}/${result.height}"><video id="analysis-video" src="${previewURL(job.job_id, result)}" poster="${posterURL(job.job_id, result)}" controls playsinline preload="auto"></video><canvas id="analysis-overlay" aria-hidden="true"></canvas></div><div class="analysis-tools"><button class="secondary-action" data-video-overlay aria-pressed="${state.videoOverlay}">${icon("target")}Landmarks ${state.videoOverlay ? "on" : "off"}</button><span>${result.preview ? `${Math.round(result.preview.fps_hint)} fps preview · ` : ""}${result.tracked_frames} / ${result.sampled_frames} pose samples usable</span></div><p class="helper">Landmarks follow the displayed video frame. Display interpolation smooths short valid gaps; measurements use the original samples.</p>${job.source === "mit_ocw" ? `<p class="video-credit">${e(result.source_credit)}. <a href="https://ocw.mit.edu/courses/pe-740-fencing-spring-2007/pages/video/" target="_blank" rel="noreferrer">Source</a> · <a href="https://creativecommons.org/licenses/by-nc-sa/3.0/" target="_blank" rel="noreferrer">CC BY-NC-SA 3.0</a>. Preview is resized and silent; source timing is preserved up to 30 fps. This demo doesn’t count toward your practice goal.</p>` : '<p class="helper">Uploaded video and analysis are saved on your local FenceCoach server. This step makes no LLM calls.</p>'}<details class="disclosure"><summary>How the video was segmented ${icon("chevron")}</summary><ul>${result.warnings.map((w) => `<li>${e(w)}</li>`).join("")}</ul><p>We find a steady en-garde stance in the clip, then propose a rep when stance expands and returns. Each set groups nearby complete cycles. The setup and exit spans are suggestions based on what falls outside those cycles. Knee changes help flag lunge-like reps; review every suggestion before saving.</p><button class="text-action" data-video-export>Export landmarks & analysis ${icon("arrow")}</button></details><details class="disclosure"><summary>Overlay contact sheet</summary><a href="${videoPath(job.job_id)}/contact-sheet" target="_blank" rel="noreferrer">Open 12-frame contact sheet</a><img loading="lazy" style="max-width:100%" src="${videoPath(job.job_id)}/contact-sheet" alt="Twelve video frames with tracked skeletons and timestamps"></details>${motionPanel(result)}${flechePanel(result)}</section><aside class="analysis-review side-card"><p class="eyebrow">${finished ? "SAVED REVIEW" : "YOUR EYES COME FIRST"}</p><h2>${finished ? "Ready for the coach." : "Review the exercise."}</h2><p>${finished ? "Your reviewed timings and visible joint measurements are attached to the session." : "The walk-in is outside the detected reps. Use the set timeline and numbered rep jumps to check each lunge and recovery."}</p>${activityBlock(result)}<div id="window-list">${state.videoWindows.map((w, i) => windowRow(w, i, result.duration_ms, finished, result)).join("") || '<p class="empty-note">No complete movement cycle was proposed. Mark an interval yourself.</p>'}</div>${finished ? primary("Open saved session", `data-session="${e(job.session_id)}"`) : `${secondary("Add a manual interval", "data-window-add")}<label class="field"><span>Practice date</span><input type="date" id="video-practiced-on" value="${localDateISO()}" required></label><label class="field"><span>Practice note</span><textarea id="video-notes" maxlength="2000" rows="2" placeholder="One thing you noticed…"></textarea></label><button class="primary-action" data-video-accept ${unsupported || (!state.videoWindows.length && !result.clip_measurements?.length) ? "disabled" : ""}>Save reviewed practice ${icon("arrow")}</button>`}<p class="subtle-note">Proposed repetitions and timestamps need your review. Editing the timestamps updates the measurements when you save.</p></aside></div>`;
}
function playInterval(startMs, endMs) {
  const video = document.getElementById("analysis-video");
  if (!video) return;
  video.currentTime = startMs / 1000;
  video.ontimeupdate = () => {
    if (video.currentTime >= endMs / 1000) {
      video.pause();
      video.ontimeupdate = null;
    }
  };
  video.play().catch(() => {});
}
function flechePanel(result) {
  return `<details class="disclosure"><summary>Flèche drill · beta</summary><p class="helper">Fixed side-view rules. Precision and recall are not measured yet. Whole run-up must stay in frame; balance is not directly measured.</p>${(result.fleche_events || []).map((event) => `<article><button data-activity-seek="${event.start_ms}" data-activity-end="${event.end_ms}">Watch proposal · ${(event.start_ms / 1000).toFixed(2)}–${(event.end_ms / 1000).toFixed(2)}s</button>${event.measurements.map(m => `<p>${e(m.name.replaceAll("_", " "))}: ${m.value} ${e(m.unit)}</p>`).join("")}</article>`).join("") || "<p>No flèche proposal. Set facing, use a fixed camera, and show the full action.</p>"}</details>`;
}
function localDateISO() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}
function movementBlock(result) {
  const timeline = result.movement_timeline;
  if (!timeline) return "";
  const entries = timeline.movements || [];
  const phases = timeline.phases || [];
  const button = (item) => `<button class="activity-phase" data-activity-seek="${item.start_ms}" data-activity-end="${item.end_ms}"><span>${e(label(item.label))} · ${item.source === "trained_temporal_classifier" ? "model suggestion" : "pose suggestion"}</span><small>${(item.start_ms / 1000).toFixed(2)}–${(item.end_ms / 1000).toFixed(2)} s</small></button>`;
  const conflicts = (timeline.cycles || []).filter((cycle) => cycle.recognition_conflict).length;
  return `<section class="activity-detection"><p class="eyebrow">MOVEMENTS & PHASES</p><p class="helper">${timeline.model_ready ? "Movement model active. Check its suggestions in the footage." : "Using pose suggestions. The movement classifier still needs reviewed training examples."}</p>${entries.length ? entries.map(button).join("") : '<p class="helper">No supported movement intervals. You can still mark reps manually.</p>'}${conflicts ? `<p class="helper">${conflicts} movement cycles have conflicting pose and model suggestions. Review before labeling.</p>` : ""}${phases.length ? `<details class="disclosure"><summary>See expansion and recovery phases</summary>${phases.map(button).join("")}</details>` : ""}<p class="helper">Expansion ends at the measured stance peak; this does not identify landing or blade contact. All intervals need review.</p></section>`;
}
function activityBlock(result) {
  const sets = result.exercise_sets || [];
  const phases = result.activity_segments || [];
  const movementCount = sets.reduce((total, set) => total + set.movement_count, 0);
  const lungeCount = sets.reduce((total, set) => total + set.lunge_count, 0);
  return `${movementBlock(result)}<section class="activity-detection"><p class="eyebrow">VIDEO TIMELINE</p><strong>${sets.length ? `${sets.length} suggested ${sets.length === 1 ? "set" : "sets"} · ${movementCount} complete movement ${movementCount === 1 ? "cycle" : "cycles"}` : "No complete reps detected"}</strong><p class="helper">${sets.length ? `${lungeCount} look lunge-like from knee movement. Check each one in the footage.` : "Try clearer side-view footage with a short pause in en garde before the exercise."}</p>${phases.map((phase) => `<button class="activity-phase" data-activity-seek="${phase.start_ms}" data-activity-end="${phase.end_ms}"><span>${e(label(phase.label))}</span><small>${(phase.start_ms / 1000).toFixed(2)}–${(phase.end_ms / 1000).toFixed(2)} s</small></button>`).join("")}${result.activity_model?.ready ? `<p class="helper">Phase model ${e(result.activity_model.version)} · suggestions need review</p>` : '<p class="helper">Timeline suggestions use pose movement cues. Reviewed labels help train the phase model.</p>'}</section>`;
}
function windowRow(window, i, duration, finished, result) {
  const candidate = result?.candidates.find((item) => item.candidate_id === window.candidate_id);
  const repName = candidate?.movement_label === "lunge" ? `LUNGE-LIKE REP ${String(candidate.rep_number || i + 1).padStart(2, "0")}` : candidate ? `CHECK MOVEMENT ${String(candidate.rep_number || i + 1).padStart(2, "0")}` : `MANUAL INTERVAL ${String(i + 1).padStart(2, "0")}`;
  return `<div class="recovery-window" data-window-row="${i}"><div class="window-heading"><strong>${repName}</strong><button class="text-action" data-window-seek="${i}">Watch rep ${icon("play")}</button></div>${candidate ? `<p class="helper">Set ${candidate.set_number} · ${candidate.lunge_cue_count || 0}/3 lunge cues · starts ${((window.onset_ms ?? window.start_ms) / 1000).toFixed(2)} s${candidate.return_observed_through_tracking_gap ? " · check return (tracking gap)" : ""}</p>` : ""}<label class="field"><span>Movement onset / seconds (optional)</span><input type="number" min="0" max="${window.start_ms / 1000}" step="0.001" value="${window.onset_ms == null ? "" : window.onset_ms / 1000}" data-window-field="onset_ms" data-window-index="${i}" ${finished ? "disabled" : ""}></label><div class="form-row"><label class="field"><span>Peak / seconds</span><input type="number" min="0" max="${duration / 1000}" step="0.001" value="${window.start_ms / 1000}" data-window-field="start_ms" data-window-index="${i}" ${finished ? "disabled" : ""}></label><label class="field"><span>Return / seconds</span><input type="number" min="0" max="${duration / 1000}" step="0.001" value="${window.end_ms / 1000}" data-window-field="end_ms" data-window-index="${i}" ${finished ? "disabled" : ""}></label></div><div class="window-footer"><span id="window-duration-${i}">${((window.end_ms - window.start_ms) / 1000).toFixed(3)} s</span>${finished ? "" : `<button class="text-action" data-window-remove="${i}" aria-label="Remove interval ${i + 1}">Remove ${icon("close")}</button>`}</div>${result ? repDetails(window, result) : ""}${finished ? "" : `<div class="window-marks"><button data-window-mark="start_ms" data-window-index="${i}">Use playhead for peak</button><button data-window-mark="end_ms" data-window-index="${i}">Use playhead for return</button></div>`}</div>`;
}
export function videoSetup(state) {
  return `<div class="video-setup"><label class="field"><span>Session name</span><input id="video-title" maxlength="100" value="Lunge & recovery practice"></label><p class="helper">Use one fencer practicing alone. Bout analysis is experimental. Keep the full movement visible; avoid footage showing several simultaneous bouts.</p><label class="field"><span>Clip type</span><select id="scene-type"><option value="solo">Single-fencer practice</option><option value="bout">One bout · experimental</option></select></label><label class="field"><span>Fencer to analyze — starting side</span><select id="target-side"><option value="unknown">Only fencer in view</option><option value="left">Fencer starting on the left</option><option value="right">Fencer starting on the right</option></select></label><label class="field"><span>Camera setup name (for progress)</span><input id="camera-setup-id" maxlength="80" placeholder="Garage side view"><small>Reuse this name only with the same camera position, height, distance, and framing.</small></label><label class="field"><span>Weapon</span><select id="weapon"><option value="foil">Foil</option><option value="epee">Épée</option><option value="sabre">Sabre</option></select></label><div class="form-row"><label class="field"><span>Weapon arm</span><select id="weapon-arm"><option value="unknown">Not specified</option><option value="right">Right</option><option value="left">Left</option></select></label><label class="field"><span>Front leg</span><select id="front-leg"><option value="unknown">Not specified</option><option value="right">Right</option><option value="left">Left</option></select></label></div><label class="field"><span>Facing in the video</span><select id="facing"><option value="unknown">Not specified</option><option value="right">Right side of screen</option><option value="left">Left side of screen</option></select></label><label class="field"><span>Camera movement</span><select id="camera-motion"><option value="unknown">Not specified</option><option value="fixed">Fixed camera throughout</option><option value="moving">Panning, zooming or cuts</option></select></label><label class="helper"><input type="checkbox" id="initial-guard"> The first 1.5 seconds show my stationary en garde</label><details class="disclosure"><summary>Keep one athlete in view ${icon("chevron")}</summary><p>For a solo clip, use the whole frame. For a bout, choose the fencer’s starting side above, or crop the upright preview to that fencer’s entire movement. Values are percentages of the frame.</p><div class="crop-fields">${[
    ["x", "Left", 0],
    ["y", "Top", 0],
    ["width", "Width", 100],
    ["height", "Height", 100],
  ]
    .map(
      ([key, name, value]) =>
        `<label class="field"><span>${name} %</span><input id="crop-${key}" type="number" min="0" max="100" value="${value}"></label>`,
    )
    .join(
      "",
    )}</div></details>${primary("Analyze this clip", "data-video-upload")}</div>`;
}
export function videoHistory(state) {
  return state.videoJobs.length
    ? `<section class="video-history"><div class="section-heading"><h2>Movement analyses</h2></div><div class="practice-log">${state.videoJobs
        .slice(0, 5)
        .map(
          (j) =>
            `<button data-video-job="${e(j.job_id)}"><span class="log-icon">${icon("play")}</span><div><strong>${e(j.title)}</strong><small>${e(j.stage)}${j.source === "mit_ocw" ? " · Public demo" : ""}</small></div>${icon("chevron")}</button>`,
        )
        .join("")}</div></section>`
    : "";
}
export function setupVideoController(options) {
  controls = options;
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    const { state, render, go, notice } = controls;
    try {
      if (button.hasAttribute("data-video-demo")) {
        button.disabled = true;
        await openJob(await api("/api/videos/demo", { method: "POST" }));
        go("analysis");
      } else if (button.hasAttribute("data-video-upload")) {
        if (!state.draftClip) return;
        const data = new FormData(),
          crop = {};
        for (const key of ["x", "y", "width", "height"])
          crop[key] =
            Number(document.getElementById(`crop-${key}`).value) / 100;
        if (
          crop.width <= 0.1 ||
          crop.height <= 0.1 ||
          crop.x + crop.width > 1 ||
          crop.y + crop.height > 1
        )
          throw new Error(
            "Choose a crop inside the frame, at least 10% wide and high.",
          );
        data.append("file", state.draftClip, "practice.video");
        data.append(
          "title",
          document.getElementById("video-title").value.trim() ||
            "Lunge practice",
        );
        data.append("skill_level", state.preferences.skill);
        data.append("crop", JSON.stringify(crop));
        data.append(
          "capture_profile",
          JSON.stringify({
            camera_setup_id: document.getElementById("camera-setup-id").value.trim(),
            weapon: document.getElementById("weapon").value,
            weapon_arm: document.getElementById("weapon-arm").value,
            front_leg: document.getElementById("front-leg").value,
            scene_type: document.getElementById("scene-type").value,
            target_side: document.getElementById("target-side").value,
            facing: document.getElementById("facing").value,
            camera_motion: document.getElementById("camera-motion").value,
            initial_guard_confirmed:
              document.getElementById("initial-guard").checked,
          }),
        );
        button.disabled = true;
        const job = await upload(data, (percent) => {
          button.textContent = `Uploading ${percent}%`;
        });
        await openJob(job);
        controls.setDraft(null);
        go("analysis");
      } else if (button.dataset.videoJob) {
        await openJob(await api(videoPath(button.dataset.videoJob)));
        go("analysis");
      } else if (button.hasAttribute("data-video-cancel")) {
        await openJob(
          await api(`${videoPath(state.videoJob.job_id)}/cancel`, {
            method: "POST",
          }),
        );
        render({ keepScroll: true });
      } else if (button.hasAttribute("data-video-retry")) {
        button.disabled = true;
        await openJob(
          await api(`${videoPath(state.videoJob.job_id)}/retry`, {
            method: "POST",
          }),
        );
        render({ keepScroll: true });
      } else if (button.hasAttribute("data-video-overlay")) {
        state.videoOverlay = !state.videoOverlay;
        button.setAttribute("aria-pressed", state.videoOverlay);
        button.innerHTML = `${icon("target")}Landmarks ${state.videoOverlay ? "on" : "off"}`;
        const video =
          document.getElementById("analysis-video") ||
          document.getElementById("replay-video");
        video?.dispatchEvent(new Event("fencecoach:overlaychange"));
      } else if (button.hasAttribute("data-video-export")) {
        downloadJSON(
          state.videoResult,
          `analysis-${state.videoJob.job_id}.json`,
        );
      } else if (button.hasAttribute("data-window-seek")) {
        const w = state.videoWindows[Number(button.dataset.windowSeek)];
        playInterval(w.onset_ms ?? w.start_ms, w.end_ms);
      } else if (button.hasAttribute("data-activity-seek")) {
        playInterval(Number(button.dataset.activitySeek), Number(button.dataset.activityEnd));
      } else if (button.hasAttribute("data-window-add")) {
        state.videoWindows.push({
          start_ms: 0,
          end_ms: Math.min(1000, state.videoResult.duration_ms),
          candidate_id: null,
        });
        redrawWindows();
      } else if (button.hasAttribute("data-window-remove")) {
        state.videoWindows.splice(Number(button.dataset.windowRemove), 1);
        redrawWindows();
      } else if (button.dataset.windowMark) {
        const i = Number(button.dataset.windowIndex),
          key = button.dataset.windowMark;
        const value = Math.round(
          document.getElementById("analysis-video").currentTime * 1000,
        );
        state.videoWindows[i][key] = value;
        document.querySelector(
          `[data-window-index="${i}"][data-window-field="${key}"]`,
        ).value = value / 1000;
        updateDuration(i);
      } else if (button.hasAttribute("data-video-accept")) {
        if (state.videoResult?.quality_gate?.coaching_allowed === false) throw new Error("This clip failed the quality check. Follow the filming tips before coaching.");
        button.disabled = true;
        const session = await api(
          `${videoPath(state.videoJob.job_id)}/accept`,
          {
            method: "POST",
            body: JSON.stringify({
              windows: state.videoWindows,
              notes: document.getElementById("video-notes").value,
              practiced_on:
                document.getElementById("video-practiced-on").value || null,
            }),
          },
        );
        await refreshSessions();
        state.videoJob = await api(videoPath(state.videoJob.job_id));
        state.videoJobs = await api("/api/videos");
        await controls.select(session.session_id);
        go("review");
      }
    } catch (error) {
      notice(error.message);
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        if (button.hasAttribute("data-video-upload"))
          button.innerHTML = `Analyze this clip ${icon("arrow")}`;
      }
    }
  });
  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!target.dataset.windowField) return;
    const i = Number(target.dataset.windowIndex);
    controls.state.videoWindows[i][target.dataset.windowField] =
      target.value === "" && target.dataset.windowField === "onset_ms"
        ? null
        : Math.round(Number(target.value) * 1000);
    updateDuration(i);
  });
}
function updateDuration(i) {
  const w = controls.state.videoWindows[i];
  document.getElementById(`window-duration-${i}`).textContent =
    `${((w.end_ms - w.start_ms) / 1000).toFixed(3)} s`;
}
function redrawWindows() {
  const { state } = controls;
  document.getElementById("window-list").innerHTML = state.videoWindows
    .map((w, i) =>
      windowRow(w, i, state.videoResult.duration_ms, false, state.videoResult),
    )
    .join("");
  document.querySelector("[data-video-accept]").disabled =
    !state.videoWindows.length && !state.videoResult.clip_measurements?.length;
}
async function openJob(job) {
  const ticket = ++jobEpoch,
    { state } = controls;
  clearTimeout(pollTimer);
  state.videoJob = job;
  state.videoResult = null;
  try {
    localStorage.setItem("fencecoach.videoJob", job.job_id);
  } catch {
    /* Optional browser storage. */
  }
  if (["review_ready", "completed"].includes(job.status)) {
    const result = await api(`${videoPath(job.job_id)}/result`);
    if (ticket !== jobEpoch) return;
    state.videoResult = result;
    state.videoWindows = (job.reviewed_windows || result.candidates).map(
      (w) => ({
        start_ms: w.start_ms,
        end_ms: w.end_ms,
        candidate_id: w.candidate_id,
        onset_ms: w.onset_ms ?? null,
      }),
    );
  } else if (["queued", "running", "receiving"].includes(job.status))
    pollTimer = setTimeout(() => pollJob(ticket), 1500);
  state.videoJobs = await api("/api/videos");
}
async function pollJob(ticket) {
  if (ticket !== jobEpoch) return;
  const { state, render, notice } = controls;
  try {
    const job = await api(videoPath(state.videoJob.job_id));
    if (ticket !== jobEpoch) return;
    state.videoJob = job;
    if (
      ["review_ready", "completed", "failed", "cancelled"].includes(job.status)
    ) {
      await openJob(job);
      if (["analysis", "record"].includes(state.screen))
        render({ keepScroll: true });
    } else {
      const progress = document.getElementById("analysis-progress"),
        stage = document.getElementById("analysis-stage"),
        detail = document.getElementById("analysis-detail");
      if (progress) progress.value = job.progress;
      if (stage) stage.textContent = job.stage;
      if (detail)
        detail.textContent = `${job.progress}% · ${job.sampled_frames || 0} frames sampled. You can leave this screen.`;
      pollTimer = setTimeout(() => pollJob(ticket), 1500);
    }
  } catch (error) {
    notice(`${error.message} Reconnecting to the video worker…`);
    pollTimer = setTimeout(() => pollJob(ticket), 5000);
  }
}
export async function initVideo() {
  const { state } = controls;
  state.videoJobs = await api("/api/videos");
  let id;
  try {
    id = localStorage.getItem("fencecoach.videoJob");
  } catch {
    /* Optional storage. */
  }
  const job =
    state.videoJobs.find((j) => j.job_id === id) || state.videoJobs[0];
  if (job) await openJob(job);
}
export async function loadReviewPose(state) {
  state.reviewResult = state.session?.video_job_id
    ? await api(`${videoPath(state.session.video_job_id)}/result`)
    : null;
}
function upload(data, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos");
    xhr.timeout = 180000;
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable)
        onProgress(Math.round((100 * ev.loaded) / ev.total));
    };
    xhr.onload = () => {
      let response;
      try {
        response = JSON.parse(xhr.responseText);
      } catch {
        reject(new Error("The upload response was unreadable."));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(response);
      else
        reject(
          new Error(
            typeof response.detail === "string"
              ? response.detail
              : "The video upload failed. Check the file and crop.",
          ),
        );
    };
    xhr.onerror = () =>
      reject(
        new Error(
          "Couldn’t reach the local server. Your draft is still available.",
        ),
      );
    xhr.ontimeout = () =>
      reject(new Error("Upload timed out. Try a shorter clip."));
    xhr.send(data);
  });
}
const edges = [
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [11, 23],
  [12, 24],
  [23, 24],
  [23, 25],
  [25, 27],
  [24, 26],
  [26, 28],
  [27, 29],
  [29, 31],
  [28, 30],
  [30, 32],
];
const jointIndices = [...new Set(edges.flat())];
function displayLandmarks(frames, time) {
  if (!frames.length) return [];
  let lo = 0,
    hi = frames.length - 1;
  while (lo < hi) {
    const middle = Math.floor((lo + hi) / 2);
    if (frames[middle].time_ms < time) lo = middle + 1;
    else hi = middle;
  }
  const next = frames[lo],
    previous = frames[Math.max(0, lo - 1)];
  const nearest =
    Math.abs(next.time_ms - time) < Math.abs(previous.time_ms - time)
      ? next
      : previous;
  if (Math.abs(nearest.time_ms - time) > 120) return [];
  const gap = next.time_ms - previous.time_ms;
  if (
    gap > 0 &&
    gap <= 200 &&
    time >= previous.time_ms &&
    time <= next.time_ms &&
    previous.landmarks.length === 33 &&
    next.landmarks.length === 33
  ) {
    const center = (f) => [
      (f.landmarks[23][0] + f.landmarks[24][0]) / 2,
      (f.landmarks[23][1] + f.landmarks[24][1]) / 2,
    ];
    const a = center(previous),
      b = center(next);
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) <= 0.15) {
      const fraction = (time - previous.time_ms) / gap;
      return previous.landmarks.map((point, i) => {
        const other = next.landmarks[i];
        return [
          point[0] + (other[0] - point[0]) * fraction,
          point[1] + (other[1] - point[1]) * fraction,
          0,
          Math.min(point[3], other[3]),
          Math.min(point[4], other[4]),
        ];
      });
    }
  }
  return nearest.landmarks;
}
export function mountPose(video, canvas, result, state) {
  if (!video || !canvas || !result) return () => {};
  const context = canvas.getContext("2d");
  const scale = Math.min(1, 960 / Math.max(result.width, result.height));
  canvas.width =
    result.preview?.width || Math.max(2, Math.round(result.width * scale));
  canvas.height =
    result.preview?.height || Math.max(2, Math.round(result.height * scale));
  const hasFrameCallback =
    typeof video.requestVideoFrameCallback === "function";
  let frameHandle = null,
    animationHandle = null,
    stopped = false;
  function draw(time) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (!state.videoOverlay) return;
    const landmarks = displayLandmarks(result.frames, time * 1000);
    if (!landmarks.length) return;
    context.strokeStyle = "#ff3746";
    context.fillStyle = "#fff";
    context.lineWidth = Math.max(1.5, canvas.width / 180);
    const visible = (i) => landmarks[i][3] > 0.5 && landmarks[i][4] > 0.5;
    const point = (i) => [
      landmarks[i][0] * canvas.width,
      landmarks[i][1] * canvas.height,
    ];
    for (const [a, b] of edges)
      if (visible(a) && visible(b)) {
        context.beginPath();
        context.moveTo(...point(a));
        context.lineTo(...point(b));
        context.stroke();
      }
    for (const i of jointIndices)
      if (visible(i)) {
        context.beginPath();
        context.arc(
          ...point(i),
          Math.max(2, canvas.width / 130),
          0,
          Math.PI * 2,
        );
        context.fill();
      }
  }
  function scheduleVideoFrame() {
    if (stopped || frameHandle !== null) return;
    frameHandle = video.requestVideoFrameCallback((_now, metadata) => {
      frameHandle = null;
      if (stopped) return;
      draw(metadata.mediaTime);
      scheduleVideoFrame();
    });
  }
  function animateFallback() {
    animationHandle = null;
    if (stopped || video.paused || video.ended) return;
    if (video.readyState >= 2 && !video.seeking) draw(video.currentTime);
    animationHandle = requestAnimationFrame(animateFallback);
  }
  function invalidate() {
    if (stopped) return;
    draw(video.currentTime);
    if (hasFrameCallback) scheduleVideoFrame();
    else if (!video.paused && !video.ended && animationHandle === null)
      animateFallback();
  }
  const events = [
    "loadeddata",
    "seeked",
    "play",
    "pause",
    "ended",
    "fencecoach:overlaychange",
  ];
  for (const event of events) video.addEventListener(event, invalidate);
  invalidate();
  return () => {
    stopped = true;
    if (frameHandle !== null) video.cancelVideoFrameCallback(frameHandle);
    if (animationHandle !== null) cancelAnimationFrame(animationHandle);
    for (const event of events) video.removeEventListener(event, invalidate);
  };
}

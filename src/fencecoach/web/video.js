import { html } from "./html.js";
import { api, downloadJSON } from "./api-client.js";
import { e, icon, heading, primary, secondary } from "./ui.js";
import { frameStepControls } from "./replay-player.js?v=20261012-startup-fix-v1";
import { refreshSessions } from "./store.js?v=20261012-review-layout-v1";

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
    return html`${heading(
        "MOVEMENT ANALYSIS",
        "Bring your practice.<br>See your return.",
      )}
      <div class="empty-session">
        <p>Start with a short side-view clip or MIT’s public fencing demonstration.</p>
        ${primary("Choose a clip", 'data-go="record"')}${secondary(
          "Analyze public demo",
          "data-video-demo",
        )}
      </div>`;
  if (!result)
    return html`${heading("MOVEMENT ANALYSIS", "One rep at a time.")}
      <section class="analysis-status side-card">
        <p class="eyebrow">${e(job.title)}</p>
        <h2 id="analysis-stage">${e(job.stage)}</h2>
        <progress id="analysis-progress" max="100" value="${job.progress}"></progress>
        <p id="analysis-detail" role="status">
          ${job.status === "failed"
            ? e(job.error)
            : `${job.progress}% · You can leave this screen while analysis runs.`}
        </p>
        ${job.status === "cancelled"
          ? secondary("Choose another clip", 'data-go="record"')
          : job.status === "failed"
            ? secondary("Retry analysis", "data-video-retry")
            : ""}${secondary("Back to practice", 'data-go="record"')}
      </section>`;
  const finished = job.status === "completed";
  const editingSavedTimes = Boolean(state.editingSavedTimes);
  const qa = result.quality_gate;
  const localEvidence = result.technique_evaluation?.reps?.some(
    (rep) => rep.measurements?.projected_torso_tilt,
  );
  const unsupported = qa && !qa.coaching_allowed && !localEvidence;
  const qualityPanel = unsupported
    ? html`<p class="analysis-capture-tip" role="status">
        ${e(
          qa.issues?.[0]?.tip ||
            "Keep your full body visible to get more useful feedback.",
        )}
      </p>`
    : "";
  const savedSummary = `${e(job.title)} is saved in your practice log.`;
  return html`${heading("MOVEMENT REVIEW", "Review your practice.")}
    <div class="analysis-topline">
      <span>${e(job.title)}</span>${secondary(
        "Choose another clip",
        'data-go="record"',
      )}
    </div>
    ${qualityPanel}
    <div class="analysis-layout">
      <section class="analysis-video-column">
        <div
          class="analysis-player"
          style="aspect-ratio:${result.width}/${result.height}"
        >
          <video
            id="analysis-video"
            src="${previewURL(job.job_id, result)}"
            poster="${posterURL(job.job_id, result)}"
            controls
            playsinline
            preload="metadata"
          ></video
          ><canvas id="analysis-overlay" aria-hidden="true"></canvas>
        </div>
        ${frameStepControls("analysis-frame-controls", result.preview?.fps_hint || 30)}
        <div class="analysis-tools">
          <button
            class="secondary-action"
            data-video-overlay
            aria-pressed="${state.videoOverlay}"
          >
            ${icon("target")}Body overlay ${state.videoOverlay ? "on" : "off"}</button
          ><a class="text-action" href="/coach-review/${encodeURIComponent(job.job_id)}"
            >Get coach feedback ${icon("arrow")}</a
          >
        </div>
        ${job.source === "mit_ocw"
          ? html`<p class="video-credit">
              ${e(result.source_credit)}.
              <a
                href="https://ocw.mit.edu/courses/pe-740-fencing-spring-2007/pages/video/"
                target="_blank"
                rel="noreferrer"
                >Source</a
              >
              ·
              <a
                href="https://creativecommons.org/licenses/by-nc-sa/3.0/"
                target="_blank"
                rel="noreferrer"
                >CC BY-NC-SA 3.0</a
              >
            </p>`
          : ""}
      </section>
      <aside class="analysis-review side-card">
        <h2>${finished ? "Practice saved." : "One movement at a time."}</h2>
        <p>
          ${finished
            ? savedSummary
            : "Watch each movement, adjust its times, then choose Lunge or Step / reset."}
        </p>
        <div id="rep-review-list">${repReviewPanel(result, state)}</div>
        ${finished
          ? html`<div class="analysis-save" data-saved-timing-actions>
              <p class="helper" data-saved-timing-status>
                ${editingSavedTimes
                  ? "Adjust the times, then save them to update this practice."
                  : "Need to correct an interval? Edit its lunge and recovery times."}
              </p>
              <button
                class="secondary-action"
                data-video-edit-times
                ${editingSavedTimes ? "hidden" : ""}
              >
                Edit times
              </button>
              <div data-saved-time-controls ${editingSavedTimes ? "" : "hidden"}>
                <button class="primary-action" data-video-update-timings>
                  Save time changes
                </button>
                <button class="secondary-action" data-video-cancel-time-edits>
                  Cancel
                </button>
              </div>
              ${primary("Open saved session", `data-session="${e(job.session_id)}"`)}
            </div>`
          : html`<div class="analysis-save">
              <details class="analysis-practice-note">
                <summary>Practice date & note ${icon("chevron")}</summary>
                <label class="field"
                  ><span>Practice date</span
                  ><input
                    type="date"
                    id="video-practiced-on"
                    value="${localDateISO()}"
                    required /></label
                ><label class="field"
                  ><span>Practice note</span
                  ><textarea
                    id="video-notes"
                    maxlength="2000"
                    rows="2"
                    placeholder="One thing you noticed…"
                  ></textarea>
                </label>
              </details>
              <button
                class="primary-action"
                data-video-accept
                ${!state.videoWindows.length && !result.clip_measurements?.length
                  ? "disabled"
                  : ""}
              >
                Save reviewed practice ${icon("arrow")}
              </button>
              <p class="helper" data-save-help role="status">
                ${!state.videoWindows.length && !result.clip_measurements?.length
                  ? "Add a lunge to enable saving."
                  : "Save your timing changes to update the coaching session."}
              </p>
            </div>`}
      </aside>
    </div>`;
}

function repReviewPanel(result, state) {
  const reviewed = state.videoAnnotations?.rep_reviews || [];
  const candidates = result.candidates || [];
  const reviewedCount = candidates.filter((candidate) =>
    reviewed.some((item) => item.candidate_id === candidate.candidate_id),
  ).length;
  const clock = (ms) => `${(ms / 1000).toFixed(1)}s`;
  const manualWindows = state.videoWindows
    .map((window, index) => ({ window, index }))
    .filter(({ window }) => !window.candidate_id);
  const count = candidates.length + manualWindows.length;
  state.selectedVideoRep = Math.max(
    0,
    Math.min(state.selectedVideoRep || 0, Math.max(0, count - 1)),
  );
  const selected = state.selectedVideoRep;
  const entries = candidates
    .slice(selected, selected + 1)
    .map((candidate) => {
      const label = reviewed.find(
        (item) => item.candidate_id === candidate.candidate_id,
      )?.label;
      const timing = timingForCandidate(state, candidate.candidate_id);
      const start =
        timing.onset_ms ??
        candidate.onset_ms ??
        candidate.movement_onset_ms ??
        candidate.start_ms;
      return html`<article class="rep-verification">
        <div>
          <h2>Movement ${selected + 1} · ${clock(start)}–${clock(timing.end_ms)}</h2>
          <button
            class="text-action"
            data-rep-review-seek="${start}"
            data-rep-review-end="${timing.end_ms}"
          >
            Watch ${icon("play")}
          </button>
        </div>
        <div class="rep-time-editor">
          <h4>Lunge & recovery times</h4>
          <p class="helper">
            A rep includes the lunge and recovery. Pause and step through the video,
            then use its time below.
          </p>
          ${[
            ["onset_ms", "Lunge starts"],
            ["start_ms", "Lunge finish"],
            ["end_ms", "Return to guard"],
          ]
            .map(
              ([key, title]) =>
                html`<div class="rep-time-row">
                  <label class="field"
                    ><span>${title} · seconds</span
                    ><input
                      type="number"
                      min="0"
                      max="${(result.duration_ms / 1000).toFixed(3)}"
                      step="0.001"
                      value="${timing[key] == null
                        ? ""
                        : (timing[key] / 1000).toFixed(3)}"
                      data-rep-time-field="${key}"
                      data-candidate="${e(candidate.candidate_id)}"
                      ${state.videoJob.status === "completed" &&
                      !state.editingSavedTimes
                        ? "disabled"
                        : ""} /></label
                  ><button
                    class="text-action"
                    data-rep-time-mark="${key}"
                    data-candidate="${e(candidate.candidate_id)}"
                    ${state.videoJob.status === "completed" && !state.editingSavedTimes
                      ? "disabled"
                      : ""}
                  >
                    Use video time
                  </button>
                </div>`,
            )
            .join("")}
        </div>
        <div class="rep-verification-actions">
          <button
            class="secondary-action"
            data-cycle-review="lunge"
            data-candidate="${e(candidate.candidate_id)}"
            aria-pressed="${label === "lunge"}"
          >
            Lunge
          </button>
          <button
            class="secondary-action"
            data-cycle-review="step_or_reset"
            data-candidate="${e(candidate.candidate_id)}"
            aria-pressed="${label === "step_or_reset"}"
          >
            Step / reset
          </button>
        </div>
      </article>`;
    })
    .join("");
  const manual = manualWindows[selected - candidates.length];
  const manualEntries = manual
    ? windowRow(
        manual.window,
        manual.index,
        result.duration_ms,
        state.videoJob.status === "completed" && !state.editingSavedTimes,
        result,
        state.videoJob.status !== "completed",
      )
    : "";
  const picker = count
    ? html`<div class="analysis-rep-navigation">
        <button
          class="secondary-action"
          data-rep-select="${selected - 1}"
          ${selected === 0 ? "disabled" : ""}
          aria-label="Previous movement"
        >
          ${icon("chevron")}Previous</button
        ><label class="field"
          ><select data-rep-picker aria-label="Choose movement">
            ${Array.from({ length: count }, (_, i) => {
              const candidate = candidates[i];
              const verdict = candidate
                ? reviewed.find((item) => item.candidate_id === candidate.candidate_id)
                    ?.label
                : "lunge";
              return html`<option value="${i}" ${selected === i ? "selected" : ""}>
                ${i + 1} of ${count} ·
                ${verdict === "lunge"
                  ? "Lunge"
                  : verdict === "step_or_reset"
                    ? "Step / reset"
                    : "Not checked"}
              </option>`;
            }).join("")}
          </select></label
        ><button
          class="secondary-action"
          data-rep-select="${selected + 1}"
          ${selected >= count - 1 ? "disabled" : ""}
          aria-label="Next movement"
        >
          Next${icon("chevron")}
        </button>
      </div>`
    : "";
  const draft = state.pendingMissedRep;
  const steps = [
    ["start_ms", "Start movement"],
    ["peak_ms", "Lunge finish"],
    ["end_ms", "Return to guard"],
  ];
  return html`<section class="rep-verification-panel">
    <div class="section-heading">
      <h3>Your movements</h3>
      <span>${reviewedCount} of ${candidates.length} checked</span>
    </div>
    ${picker}
    ${entries}${manualEntries}${!count
      ? '<p class="empty-note">No movements found. Add a missed lunge below.</p>'
      : ""}
    <div class="rep-verification-panel" data-missed-rep-form>
      ${draft
        ? html`<h4>Add a missed lunge</h4>
            <p class="helper">
              Seek the video, then mark the start, lunge finish, and return to guard.
            </p>
            <div class="rep-review-markers">
              ${steps
                .map(
                  ([key, title]) =>
                    `<div><span>${e(title)}${draft[key] != null ? ` · ${clock(draft[key])}` : " · not marked"}</span><button class="text-action" data-missed-rep-mark="${key}">Use current video time</button></div>`,
                )
                .join("")}
            </div>
            <button
              class="primary-action"
              data-missed-rep-save
              ${steps.some(([key]) => draft[key] == null) ? "disabled" : ""}
            >
              Save missed lunge</button
            ><button class="text-action" data-missed-rep-cancel>Cancel</button>`
        : '<button class="secondary-action" data-missed-rep-add>Add a missed lunge</button>'}
    </div>
  </section>`;
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
function localDateISO() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}
function windowRow(window, i, duration, finished, result, allowRemove = true) {
  return html`<div class="recovery-window" data-window-row="${i}">
    <div class="window-heading">
      <strong>Added lunge</strong
      ><button class="text-action" data-window-seek="${i}">
        Watch rep ${icon("play")}
      </button>
    </div>
    ${[
      ["onset_ms", "Lunge starts"],
      ["start_ms", "Lunge finish"],
      ["end_ms", "Return to guard"],
    ]
      .map(
        ([key, title]) =>
          html`<div class="rep-time-row">
            <label class="field"
              ><span>${title} · seconds</span
              ><input
                type="number"
                min="0"
                max="${duration / 1000}"
                step="0.001"
                value="${window[key] == null ? "" : (window[key] / 1000).toFixed(3)}"
                data-window-field="${key}"
                data-window-index="${i}"
                ${finished ? "disabled" : ""} /></label
            >${finished
              ? ""
              : `<button class="text-action" data-window-mark="${key}" data-window-index="${i}">Use video time</button>`}
          </div>`,
      )
      .join("")}
    <div class="window-footer">
      <span id="window-duration-${i}"
        >${((window.end_ms - window.start_ms) / 1000).toFixed(1)} s recovery</span
      >${finished || !allowRemove
        ? ""
        : html`<button
            class="text-action"
            data-window-remove="${i}"
            aria-label="Remove added lunge"
          >
            Remove ${icon("close")}
          </button>`}
    </div>
  </div>`;
}
export function videoSetup(state) {
  return html`<div class="video-setup">
    <label class="field"
      ><span>Session name</span
      ><input id="video-title" maxlength="100" value="Lunge & recovery practice"
    /></label>
    <p class="helper">
      Use one fencer practicing alone. Bout analysis is experimental. Keep the full
      movement visible; avoid footage showing several simultaneous bouts.
    </p>
    <label class="field"
      ><span>Clip type</span
      ><select id="scene-type">
        <option value="solo">Single-fencer practice</option>
        <option value="bout">One bout · experimental</option>
      </select></label
    ><label class="field"
      ><span>Fencer to analyze — starting side</span
      ><select id="target-side">
        <option value="unknown">Only fencer in view</option>
        <option value="left">Fencer starting on the left</option>
        <option value="right">Fencer starting on the right</option>
      </select></label
    ><label class="field"
      ><span>Camera setup name (for progress)</span
      ><input
        id="camera-setup-id"
        maxlength="80"
        placeholder="Garage side view"
      /><small
        >Reuse this name only with the same camera position, height, distance, and
        framing.</small
      ></label
    ><label class="field"
      ><span>Weapon</span
      ><select id="weapon">
        <option value="foil">Foil</option>
        <option value="epee">Épée</option>
        <option value="sabre">Sabre</option>
      </select></label
    >
    <div class="form-row">
      <label class="field"
        ><span>Weapon arm</span
        ><select id="weapon-arm">
          <option value="unknown">Not specified</option>
          <option value="right">Right</option>
          <option value="left">Left</option>
        </select></label
      ><label class="field"
        ><span>Front leg</span
        ><select id="front-leg">
          <option value="unknown">Not specified</option>
          <option value="right">Right</option>
          <option value="left">Left</option>
        </select></label
      >
    </div>
    <label class="field"
      ><span>Facing in the video</span
      ><select id="facing">
        <option value="unknown">Not specified</option>
        <option value="right">Right side of screen</option>
        <option value="left">Left side of screen</option>
      </select></label
    ><label class="field"
      ><span>Camera view</span
      ><select id="camera-view">
        <option value="unknown">Not specified</option>
        <option value="side">Side view</option>
        <option value="front">Front view</option>
        <option value="oblique">Angled view</option>
      </select></label
    ><label class="field"
      ><span>Camera movement</span
      ><select id="camera-motion">
        <option value="unknown">Not specified</option>
        <option value="fixed">Fixed camera throughout</option>
        <option value="moving">Panning, zooming or cuts</option>
      </select></label
    ><label class="helper"
      ><input type="checkbox" id="initial-guard" /> The first 1.5 seconds show my
      stationary en garde</label
    >
    <details class="disclosure">
      <summary>Keep one athlete in view ${icon("chevron")}</summary>
      <p>
        For a solo clip, use the whole frame. For a bout, choose the fencer’s starting
        side above, or crop the upright preview to that fencer’s entire movement. Values
        are percentages of the frame.
      </p>
      <div class="crop-fields">
        ${[
          ["x", "Left", 0],
          ["y", "Top", 0],
          ["width", "Width", 100],
          ["height", "Height", 100],
        ]
          .map(
            ([key, name, value]) =>
              html`<label class="field"
                ><span>${name} %</span
                ><input
                  id="crop-${key}"
                  type="number"
                  min="0"
                  max="100"
                  value="${value}"
              /></label>`,
          )
          .join("")}
      </div>
    </details>
    ${primary("Analyze this clip", "data-video-upload")}
  </div>`;
}
export function videoHistory(state) {
  return state.videoJobs.length
    ? html`<section class="video-history">
        <div class="section-heading"><h2>Movement analyses</h2></div>
        <div class="practice-log">
          ${state.videoJobs
            .slice(0, 5)
            .map(
              (j) =>
                html`<button data-video-job="${e(j.job_id)}">
                  <span class="log-icon">${icon("play")}</span>
                  <div>
                    <strong>${e(j.title)}</strong
                    ><small
                      >${e(j.stage)}${j.source === "mit_ocw"
                        ? " · Public demo"
                        : ""}</small
                    >
                  </div>
                  ${icon("chevron")}
                </button>`,
            )
            .join("")}
        </div>
      </section>`
    : "";
}
export function setupVideoController(options) {
  controls = options;
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    const { state, render, go, notice } = controls;
    try {
      if (button.hasAttribute("data-rep-select")) {
        state.selectedVideoRep = Number(button.dataset.repSelect);
        redrawRepReviews();
        seekSelectedRep();
      } else if (button.hasAttribute("data-video-edit-times")) {
        state.savedTimingDraft = {
          windows: JSON.parse(JSON.stringify(state.videoWindows)),
          annotations: JSON.parse(JSON.stringify(state.videoAnnotations)),
        };
        state.editingSavedTimes = true;
        button.hidden = true;
        document.querySelector("[data-saved-time-controls]").hidden = false;
        document.querySelector("[data-saved-timing-status]").textContent =
          "Adjust the times, then save them to update this practice.";
        redrawRepReviews();
      } else if (button.hasAttribute("data-video-cancel-time-edits")) {
        if (state.savedTimingDraft) {
          state.videoWindows = state.savedTimingDraft.windows;
          state.videoAnnotations = state.savedTimingDraft.annotations;
        }
        state.savedTimingDraft = null;
        state.editingSavedTimes = false;
        redrawRepReviews();
        document.querySelector("[data-saved-time-controls]").hidden = true;
        document.querySelector("[data-video-edit-times]").hidden = false;
        document.querySelector("[data-saved-timing-status]").textContent =
          "Need to correct an interval? Edit its lunge and recovery times.";
      } else if (button.hasAttribute("data-video-update-timings")) {
        button.disabled = true;
        button.textContent = "Saving changes…";
        await saveRepReviews();
        await api(`${videoPath(state.videoJob.job_id)}/accept`, {
          method: "POST",
          body: JSON.stringify({
            update_existing: true,
            windows: state.videoWindows,
          }),
        });
        state.videoJob = await api(videoPath(state.videoJob.job_id));
        state.videoWindows = (state.videoJob.reviewed_windows || []).map((w) => ({
          start_ms: w.start_ms,
          end_ms: w.end_ms,
          onset_ms: w.onset_ms ?? null,
          candidate_id: w.candidate_id,
        }));
        state.editingSavedTimes = false;
        state.savedTimingDraft = null;
        await refreshSessions();
        redrawRepReviews();
        document.querySelector("[data-saved-time-controls]").hidden = true;
        document.querySelector("[data-video-edit-times]").hidden = false;
        document.querySelector("[data-saved-timing-status]").textContent =
          "Timing changes saved to this practice.";
      } else if (button.hasAttribute("data-video-demo")) {
        button.disabled = true;
        await openJob(await api("/api/videos/demo", { method: "POST" }));
        go("analysis");
      } else if (button.hasAttribute("data-video-upload")) {
        if (!state.draftClip) return;
        const data = new FormData(),
          crop = {};
        for (const key of ["x", "y", "width", "height"])
          crop[key] = Number(document.getElementById(`crop-${key}`).value) / 100;
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
          document.getElementById("video-title").value.trim() || "Lunge practice",
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
            camera_view: document.getElementById("camera-view")?.value || "unknown",
            initial_guard_confirmed: document.getElementById("initial-guard").checked,
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
        button.innerHTML = `${icon("target")}${"Body overlay"} ${state.videoOverlay ? "on" : "off"}`;
        const video =
          document.getElementById("analysis-video") ||
          document.getElementById("replay-video");
        video?.dispatchEvent(new Event("fencecoach:overlaychange"));
      } else if (button.hasAttribute("data-video-export")) {
        downloadJSON(state.videoResult, `analysis-${state.videoJob.job_id}.json`);
      } else if (button.hasAttribute("data-window-seek")) {
        const w = state.videoWindows[Number(button.dataset.windowSeek)];
        playInterval(w.onset_ms ?? w.start_ms, w.end_ms);
      } else if (button.hasAttribute("data-rep-review-seek")) {
        playInterval(
          Number(button.dataset.repReviewSeek),
          Number(button.dataset.repReviewEnd),
        );
      } else if (button.hasAttribute("data-rep-time-mark")) {
        const candidateId = button.dataset.candidate;
        const window = timingForCandidate(state, candidateId);
        if (!window)
          throw new Error(
            "This rep’s timing row is no longer available. Reopen the clip to refresh it.",
          );
        const field = button.dataset.repTimeMark;
        window[field] = Math.round(
          document.getElementById("analysis-video").currentTime * 1000,
        );
        syncReviewedRepTiming(candidateId, window);
        redrawRepReviews();
        redrawWindows();
      } else if (button.hasAttribute("data-cycle-review")) {
        const candidate = state.videoResult.candidates.find(
          (item) => item.candidate_id === button.dataset.candidate,
        );
        if (!candidate)
          throw new Error(
            "This suggestion is no longer available. Reopen the clip to refresh it.",
          );
        const label = button.dataset.cycleReview;
        state.videoAnnotations ||= {
          labels: [],
          activity_labels: [],
          rep_reviews: [],
          reviewer: "athlete",
          domain_verified: false,
        };
        const previousAnnotations = JSON.parse(JSON.stringify(state.videoAnnotations));
        const previousWindows = JSON.parse(JSON.stringify(state.videoWindows));
        const reviews = state.videoAnnotations.rep_reviews || [];
        const prior = reviews.findIndex(
          (item) => item.candidate_id === candidate.candidate_id,
        );
        const timing = timingForCandidate(state, candidate.candidate_id);
        const start =
          timing?.onset_ms ??
          candidate.onset_ms ??
          candidate.movement_onset_ms ??
          candidate.start_ms;
        const entry = {
          candidate_id: candidate.candidate_id,
          start_ms: start,
          peak_ms: timing?.start_ms ?? candidate.start_ms,
          end_ms: timing?.end_ms ?? candidate.end_ms,
          label,
        };
        if (prior >= 0) reviews.splice(prior, 1, entry);
        else reviews.push(entry);
        state.videoAnnotations.rep_reviews = reviews.sort(
          (a, b) => a.start_ms - b.start_ms,
        );
        if (state.videoJob.status !== "completed") {
          if (label === "step_or_reset")
            state.videoWindows = state.videoWindows.filter(
              (window) => window.candidate_id !== candidate.candidate_id,
            );
          else if (
            !state.videoWindows.some(
              (window) => window.candidate_id === candidate.candidate_id,
            )
          )
            state.videoWindows.push({
              candidate_id: candidate.candidate_id,
              onset_ms: start,
              start_ms: timing.start_ms,
              end_ms: timing.end_ms,
            });
          state.videoWindows.sort(
            (a, b) => (a.onset_ms ?? a.start_ms) - (b.onset_ms ?? b.start_ms),
          );
        }
        try {
          await saveRepReviews();
        } catch (error) {
          state.videoAnnotations = previousAnnotations;
          state.videoWindows = previousWindows;
          redrawRepReviews();
          if (state.videoJob.status !== "completed") redrawWindows();
          throw error;
        }
        redrawRepReviews();
        if (state.videoJob.status !== "completed") redrawWindows();
      } else if (button.hasAttribute("data-missed-rep-add")) {
        state.pendingMissedRep = {
          start_ms: null,
          peak_ms: null,
          end_ms: null,
        };
        redrawRepReviews();
      } else if (button.hasAttribute("data-missed-rep-cancel")) {
        state.pendingMissedRep = null;
        redrawRepReviews();
      } else if (button.hasAttribute("data-missed-rep-mark")) {
        const key = button.dataset.missedRepMark;
        state.pendingMissedRep[key] = Math.round(
          document.getElementById("analysis-video").currentTime * 1000,
        );
        redrawRepReviews();
      } else if (button.hasAttribute("data-missed-rep-save")) {
        const draft = state.pendingMissedRep;
        if (!(draft.start_ms < draft.peak_ms && draft.peak_ms < draft.end_ms))
          throw new Error(
            "Mark the movement start, lunge finish, and return in that order.",
          );
        const row = { ...draft, candidate_id: null, label: "lunge" };
        state.videoAnnotations ||= {
          labels: [],
          activity_labels: [],
          rep_reviews: [],
          reviewer: "athlete",
          domain_verified: false,
        };
        const previousAnnotations = JSON.parse(JSON.stringify(state.videoAnnotations));
        const previousWindows = JSON.parse(JSON.stringify(state.videoWindows));
        state.videoAnnotations.rep_reviews ||= [];
        state.videoAnnotations.rep_reviews.push(row);
        state.videoAnnotations.rep_reviews.sort((a, b) => a.start_ms - b.start_ms);
        if (state.videoJob.status !== "completed")
          state.videoWindows.push({
            onset_ms: draft.start_ms,
            start_ms: draft.peak_ms,
            end_ms: draft.end_ms,
            candidate_id: null,
          });
        state.videoWindows.sort(
          (a, b) => (a.onset_ms ?? a.start_ms) - (b.onset_ms ?? b.start_ms),
        );
        try {
          await saveRepReviews();
        } catch (error) {
          state.videoAnnotations = previousAnnotations;
          state.videoWindows = previousWindows;
          redrawRepReviews();
          if (state.videoJob.status !== "completed") redrawWindows();
          throw error;
        }
        state.pendingMissedRep = null;
        redrawRepReviews();
        if (state.videoJob.status !== "completed") redrawWindows();
      } else if (button.hasAttribute("data-activity-seek")) {
        playInterval(
          Number(button.dataset.activitySeek),
          Number(button.dataset.activityEnd),
        );
      } else if (button.hasAttribute("data-window-add")) {
        state.videoWindows.push({
          start_ms: 0,
          end_ms: Math.min(1000, state.videoResult.duration_ms),
          candidate_id: null,
        });
        redrawWindows();
      } else if (button.hasAttribute("data-window-remove")) {
        const index = Number(button.dataset.windowRemove);
        const manualIndex = state.videoWindows
          .slice(0, index)
          .filter((item) => !item.candidate_id).length;
        const reviews = state.videoAnnotations?.rep_reviews || [];
        const review = reviews.filter((item) => !item.candidate_id)[manualIndex];
        if (review) reviews.splice(reviews.indexOf(review), 1);
        state.videoWindows.splice(index, 1);
        redrawWindows();
        redrawRepReviews();
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
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.textContent = "Saving reviewed practice…";
        if (state.videoAnnotations?.rep_reviews?.length) await saveRepReviews();
        const session = await api(`${videoPath(state.videoJob.job_id)}/accept`, {
          method: "POST",
          body: JSON.stringify({
            windows: state.videoWindows,
            notes: document.getElementById("video-notes").value,
            practiced_on: document.getElementById("video-practiced-on").value || null,
          }),
        });
        await refreshSessions();
        state.videoJob = await api(videoPath(state.videoJob.job_id));
        state.videoJobs = await api("/api/videos");
        await controls.select(session.session_id);
        state.reviewSavedSessionId = session.session_id;
        go("review");
      }
    } catch (error) {
      notice(error.message);
      if (button.hasAttribute("data-video-accept")) {
        const help = document.querySelector("[data-save-help]");
        if (help) help.textContent = `Could not save: ${error.message}`;
      }
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        if (button.hasAttribute("data-video-accept")) {
          button.removeAttribute("aria-busy");
          button.innerHTML = `Save reviewed practice ${icon("arrow")}`;
          button.disabled =
            !controls.state.videoWindows.length &&
            !controls.state.videoResult?.clip_measurements?.length;
        }
        if (button.hasAttribute("data-video-upload"))
          button.innerHTML = `Analyze this clip ${icon("arrow")}`;
        if (button.hasAttribute("data-video-update-timings")) {
          button.textContent = "Save time changes";
          button.disabled = false;
        }
      }
    }
  });
  document.addEventListener("change", (event) => {
    if (!event.target.matches("[data-rep-picker]")) return;
    controls.state.selectedVideoRep = Number(event.target.value);
    redrawRepReviews();
    seekSelectedRep();
  });
  document.addEventListener("input", (event) => {
    const target = event.target;
    if (target.dataset.repTimeField) {
      const window = timingForCandidate(controls.state, target.dataset.candidate);
      if (!window) return;
      const key = target.dataset.repTimeField;
      window[key] =
        target.value === "" && key === "onset_ms"
          ? null
          : Math.round(Number(target.value) * 1000);
      syncReviewedRepTiming(target.dataset.candidate, window);
      const index = controls.state.videoWindows.indexOf(window);
      const editor = document.querySelector(
        `[data-window-index="${index}"][data-window-field="${key}"]`,
      );
      if (editor) editor.value = window[key] == null ? "" : window[key] / 1000;
      const duration = document.getElementById(`window-duration-${index}`);
      if (duration)
        duration.textContent = `${((window.end_ms - window.start_ms) / 1000).toFixed(3)} s`;
      return;
    }
    if (!target.dataset.windowField) return;
    const i = Number(target.dataset.windowIndex);
    controls.state.videoWindows[i][target.dataset.windowField] =
      target.value === "" && target.dataset.windowField === "onset_ms"
        ? null
        : Math.round(Number(target.value) * 1000);
    if (controls.state.videoWindows[i].candidate_id)
      syncReviewedRepTiming(
        controls.state.videoWindows[i].candidate_id,
        controls.state.videoWindows[i],
      );
    updateDuration(i);
  });
}
function updateDuration(i) {
  const state = controls.state;
  const w = state.videoWindows[i];
  if (!w.candidate_id) {
    const manualIndex = state.videoWindows
      .slice(0, i)
      .filter((item) => !item.candidate_id).length;
    const review = state.videoAnnotations?.rep_reviews?.filter(
      (item) => !item.candidate_id,
    )[manualIndex];
    if (review) {
      review.start_ms = w.onset_ms ?? w.start_ms;
      review.peak_ms = w.start_ms;
      review.end_ms = w.end_ms;
    }
  }
  const duration = document.getElementById(`window-duration-${i}`);
  if (duration)
    duration.textContent = `${((w.end_ms - w.start_ms) / 1000).toFixed(3)} s`;
}
function redrawWindows() {
  const { state } = controls;
  const accept = document.querySelector("[data-video-accept]");
  if (accept)
    accept.disabled =
      !state.videoWindows.length && !state.videoResult.clip_measurements?.length;
  const help = document.querySelector("[data-save-help]");
  if (help)
    help.textContent =
      !state.videoWindows.length && !state.videoResult.clip_measurements?.length
        ? "Add a rep interval to enable saving."
        : "Selected intervals are checked when you save; setup and exit footage do not automatically block a usable rep.";
}
async function openJob(job) {
  const ticket = ++jobEpoch,
    { state } = controls;
  clearTimeout(pollTimer);
  state.videoJob = job;
  state.selectedVideoRep = 0;
  state.editingSavedTimes = false;
  state.savedTimingDraft = null;
  state.videoRepTimings = {};
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
    state.videoAnnotations = await api(`${videoPath(job.job_id)}/annotations`);
    state.pendingMissedRep = null;
    // New jobs carry an empty review list; seed the editor from pose suggestions.
    const reviewedWindows = Array.isArray(job.reviewed_windows)
      ? job.reviewed_windows
      : [];
    const windows = reviewedWindows.length ? reviewedWindows : result.candidates || [];
    state.videoWindows = windows.map((w) => ({
      start_ms: w.start_ms,
      end_ms: w.end_ms,
      candidate_id: w.candidate_id,
      onset_ms: w.onset_ms ?? w.movement_onset_ms ?? null,
    }));
  } else if (["queued", "running", "receiving"].includes(job.status))
    pollTimer = setTimeout(() => pollJob(ticket), 1500);
  state.videoJobs = await api("/api/videos");
}

async function saveRepReviews() {
  const { state } = controls;
  state.videoAnnotations = await api(
    `${videoPath(state.videoJob.job_id)}/annotations`,
    {
      method: "PUT",
      body: JSON.stringify(state.videoAnnotations),
    },
  );
}

function syncReviewedRepTiming(candidateId, window) {
  const review = controls.state.videoAnnotations?.rep_reviews?.find(
    (item) => item.candidate_id === candidateId,
  );
  if (!review) return;
  const candidate = controls.state.videoResult?.candidates?.find(
    (item) => item.candidate_id === candidateId,
  );
  review.start_ms =
    window.onset_ms ??
    candidate?.onset_ms ??
    candidate?.movement_onset_ms ??
    candidate?.start_ms ??
    window.start_ms;
  review.peak_ms = window.start_ms;
  review.end_ms = window.end_ms;
}

function timingForCandidate(state, candidateId) {
  const window = state.videoWindows.find((item) => item.candidate_id === candidateId);
  if (window) return window;
  state.videoRepTimings ||= {};
  const candidate = state.videoResult?.candidates?.find(
    (item) => item.candidate_id === candidateId,
  );
  if (!candidate) return null;
  const review = state.videoAnnotations?.rep_reviews?.find(
    (item) => item.candidate_id === candidateId,
  );
  return (state.videoRepTimings[candidateId] ||= {
    candidate_id: candidateId,
    onset_ms:
      review?.start_ms ?? candidate.onset_ms ?? candidate.movement_onset_ms ?? null,
    start_ms: review?.peak_ms ?? candidate.start_ms,
    end_ms: review?.end_ms ?? candidate.end_ms,
  });
}
function seekSelectedRep() {
  const state = controls.state;
  const candidate = state.videoResult?.candidates?.[state.selectedVideoRep];
  const manual = state.videoWindows.filter((item) => !item.candidate_id)[
    state.selectedVideoRep - (state.videoResult?.candidates?.length || 0)
  ];
  const timing = candidate ? timingForCandidate(state, candidate.candidate_id) : manual;
  const video = document.getElementById("analysis-video");
  if (timing && video) {
    video.pause();
    video.ontimeupdate = null;
    video.currentTime = (timing.onset_ms ?? timing.start_ms) / 1000;
  }
}
function redrawRepReviews() {
  const panel = document.getElementById("rep-review-list");
  if (panel)
    panel.innerHTML = repReviewPanel(controls.state.videoResult, controls.state);
}
async function pollJob(ticket) {
  if (ticket !== jobEpoch) return;
  const { state, render, notice } = controls;
  try {
    const job = await api(videoPath(state.videoJob.job_id));
    if (ticket !== jobEpoch) return;
    state.videoJob = job;
    if (["review_ready", "completed", "failed", "cancelled"].includes(job.status)) {
      await openJob(job);
      if (["analysis", "record"].includes(state.screen)) render({ keepScroll: true });
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
  const job = state.videoJobs.find((j) => j.job_id === id) || state.videoJobs[0];
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
      if (ev.lengthComputable) onProgress(Math.round((100 * ev.loaded) / ev.total));
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
        new Error("Couldn’t reach the local server. Your draft is still available."),
      );
    xhr.ontimeout = () => reject(new Error("Upload timed out. Try a shorter clip."));
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
    Math.abs(next.time_ms - time) < Math.abs(previous.time_ms - time) ? next : previous;
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
  canvas.width = result.preview?.width || Math.max(2, Math.round(result.width * scale));
  canvas.height =
    result.preview?.height || Math.max(2, Math.round(result.height * scale));
  const hasFrameCallback = typeof video.requestVideoFrameCallback === "function";
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
        context.arc(...point(i), Math.max(2, canvas.width / 130), 0, Math.PI * 2);
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

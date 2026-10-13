import { html } from "./html.js";
import { e } from "./ui.js";

const timeLabel = (seconds) =>
  `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;

export function frameStepControls(id, fps = 30) {
  const frameRate =
    Number.isFinite(Number(fps)) && Number(fps) > 0 ? Number(fps) : 30;
  return html`<div
    class="video-frame-controls"
    id="${e(id)}"
    data-frame-fps="${frameRate}"
    role="group"
    aria-label="Frame by frame video controls"
  >
    <button
      type="button"
      data-frame-step="-1"
      aria-label="Previous frame"
      title="Previous frame"
      disabled
    >
      ‹ Frame</button
    ><output data-frame-readout aria-live="polite">Frame — · — s</output
    ><button
      type="button"
      data-frame-step="1"
      aria-label="Next frame"
      title="Next frame"
      disabled
    >
      Frame ›
    </button>
  </div>`;
}

export function mountFrameStepControls(video, root, fps = 30) {
  if (!video || !root) return () => {};
  const frameRate =
    Number.isFinite(Number(fps)) && Number(fps) > 0 ? Number(fps) : 30;
  const previous = root.querySelector('[data-frame-step="-1"]');
  const next = root.querySelector('[data-frame-step="1"]');
  const readout = root.querySelector("[data-frame-readout]");
  let requestedFrame = null;

  function lastFrame() {
    return Math.max(0, Math.ceil(video.duration * frameRate) - 1);
  }
  function currentFrame() {
    return requestedFrame ?? Math.round(video.currentTime * frameRate);
  }
  function update() {
    const ready = Number.isFinite(video.duration) && video.duration > 0;
    const frame = Math.max(
      0,
      Math.min(ready ? lastFrame() : 0, currentFrame()),
    );
    if (readout) {
      const seconds = frame / frameRate;
      readout.textContent = ready
        ? `Frame ${frame + 1} · ${seconds.toFixed(3)} s`
        : "Loading video…";
    }
    if (previous) previous.disabled = !ready || frame <= 0;
    if (next) next.disabled = !ready || frame >= lastFrame();
  }
  function step(direction) {
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    video.pause();
    const frame = Math.max(
      0,
      Math.min(lastFrame(), currentFrame() + direction),
    );
    requestedFrame = frame;
    // Aim inside the target frame so browser seek rounding does not land on
    // the adjacent frame at a frame boundary.
    video.currentTime = Math.min(
      frame / frameRate + 0.1 / frameRate,
      Math.max(0, video.duration - 0.001),
    );
    update();
  }
  function onPrevious() {
    step(-1);
  }
  function onNext() {
    step(1);
  }
  function onSeeked() {
    const displayedFrame = Math.max(
      0,
      Math.min(lastFrame(), Math.round(video.currentTime * frameRate)),
    );
    if (requestedFrame !== null && displayedFrame === requestedFrame)
      requestedFrame = null;
    update();
  }
  previous?.addEventListener("click", onPrevious);
  next?.addEventListener("click", onNext);
  const events = ["loadedmetadata", "durationchange", "timeupdate", "seeked"];
  for (const event of events)
    video.addEventListener(event, event === "seeked" ? onSeeked : update);
  update();
  return () => {
    previous?.removeEventListener("click", onPrevious);
    next?.removeEventListener("click", onNext);
    for (const event of events)
      video.removeEventListener(event, event === "seeked" ? onSeeked : update);
  };
}

export function replayControls(state) {
  const result = state.reviewResult;
  const reps = result?.technique_evaluation?.reps || [];
  let jumps = reps.map((rep) => ({
    time: (rep.action_start_ms ?? rep.lunge_ms) / 1000,
    number: rep.rep_number,
  }));
  if (!jumps.length)
    jumps = (result?.candidates || []).map((candidate, index) => ({
      time: (candidate.onset_ms ?? candidate.start_ms) / 1000,
      number: index + 1,
    }));
  if (!jumps.length) {
    const measurements = (state.session?.metrics || []).filter(
      (metric) => Number.isFinite(metric.start_ms) && metric.start_ms >= 0,
    );
    const recoveries = measurements.filter(
      (metric) => metric.name === "recovery_time",
    );
    jumps = [
      ...new Map(
        (recoveries.length ? recoveries : measurements).map((metric) => [
          metric.start_ms,
          { time: metric.start_ms / 1000 },
        ]),
      ).values(),
    ];
    jumps.sort((a, b) => a.time - b.time);
    jumps.forEach((jump, index) => {
      jump.number = index + 1;
    });
  }
  jumps = jumps.filter((jump) => Number.isFinite(jump.time) && jump.time >= 0);
  return jumps.length
    ? html`<div class="replay-rep-jumps" id="replay-controls">
        <label for="replay-rep-picker">Jump to rep</label
        ><select id="replay-rep-picker" data-replay-rep-picker disabled>
          <option value="">Choose a rep</option>
          ${jumps
            .map(
              (jump) =>
                html`<option value="${jump.time}">
                  Rep ${e(jump.number)} · ${jump.time.toFixed(1)}s
                </option>`,
            )
            .join("")}
        </select>
      </div>`
    : "";
}
export function mountReplayControls(video, root) {
  if (!video) return () => {};
  const picker = root?.querySelector("[data-replay-rep-picker]");
  function update() {
    const ready = Number.isFinite(video.duration) && video.duration > 0;
    if (picker) {
      picker.disabled = !ready;
      for (const option of picker.options)
        option.disabled =
          option.value !== "" &&
          (!ready || Number(option.value) > video.duration);
    }
    if (video.videoWidth && video.videoHeight)
      video.parentElement.style.setProperty(
        "--video-aspect",
        video.videoWidth / video.videoHeight,
      );
  }
  function jump() {
    if (!picker || picker.value === "" || !Number.isFinite(video.duration))
      return;
    video.pause();
    video.currentTime = Math.min(Number(picker.value), video.duration);
  }
  picker?.addEventListener("change", jump);
  const events = ["loadedmetadata", "durationchange"];
  for (const event of events) video.addEventListener(event, update);
  update();
  return () => {
    picker?.removeEventListener("change", jump);
    for (const event of events) video.removeEventListener(event, update);
  };
}

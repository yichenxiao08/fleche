import { e } from "./ui.js";

const timeLabel = (seconds) =>
  `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;

export function replayControls(state) {
  const measurements = (state.session?.metrics || []).filter(
    (metric) => Number.isFinite(metric.start_ms) && metric.start_ms >= 0,
  );
  const recoveries = measurements.filter((metric) => metric.name === "recovery_time");
  const items = recoveries.length ? recoveries : measurements;
  let jumps = [...new Map(items.map((metric) => [metric.start_ms, {
    time: metric.start_ms / 1000,
    name: recoveries.length ? "Rep peak" : "Measurement",
  }])).values()];
  if (!jumps.length) {
    jumps = (state.reviewResult?.candidates || []).map((candidate) => ({
      time: (candidate.onset_ms ?? candidate.start_ms) / 1000,
      name: "Suggested rep",
    })).filter((jump) => Number.isFinite(jump.time) && jump.time >= 0);
  }
  jumps.sort((a, b) => a.time - b.time);
  return jumps.length ? `<div class="replay-rep-jumps" id="replay-controls" role="group" aria-label="Jump to a movement in the video"><span>Jump to</span>${jumps.map((jump, index) => `<button type="button" data-replay-time-jump="${jump.time}" disabled>${e(jump.name)} ${index + 1} · ${e(timeLabel(jump.time))}</button>`).join("")}</div>` : "";
}

export function mountReplayControls(video, root) {
  if (!video) return () => {};
  const buttons = [...(root?.querySelectorAll("[data-replay-time-jump]") || [])];
  function update() {
    const ready = Number.isFinite(video.duration) && video.duration > 0;
    for (const button of buttons) {
      const time = Number(button.dataset.replayTimeJump);
      button.disabled = !ready || time > video.duration;
      button.setAttribute("aria-pressed", String(ready && Math.abs(video.currentTime - time) < 0.5));
    }
    if (video.videoWidth && video.videoHeight)
      video.parentElement.style.setProperty("--video-aspect", video.videoWidth / video.videoHeight);
  }
  const removers = [];
  for (const button of buttons) {
    const jump = () => { video.pause(); video.currentTime = Number(button.dataset.replayTimeJump); update(); };
    button.addEventListener("click", jump);
    removers.push(() => button.removeEventListener("click", jump));
  }
  const events = ["loadedmetadata", "durationchange", "timeupdate", "seeked"];
  for (const event of events) video.addEventListener(event, update);
  update();
  return () => {
    removers.forEach((remove) => remove());
    for (const event of events) video.removeEventListener(event, update);
  };
}

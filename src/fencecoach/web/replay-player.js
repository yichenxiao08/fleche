import { e } from "./ui.js";

function timeLabel(seconds) {
  if (!Number.isFinite(seconds)) return "0:00.0";
  const value = Math.max(0, seconds);
  const minutes = Math.floor(value / 60);
  return `${minutes}:${(value % 60).toFixed(1).padStart(4, "0")}`;
}

export function replayControls(state) {
  const measurements = (state.session?.metrics || []).filter(
    (metric) => Number.isFinite(metric.start_ms) && metric.start_ms >= 0,
  );
  const recoveries = measurements.filter((metric) => metric.name === "recovery_time");
  const items = recoveries.length ? recoveries : measurements;
  let jumps = [...new Map(items.map((metric) => [metric.start_ms, {
    time: metric.start_ms / 1000,
    name: recoveries.length ? "Rep" : "Measurement",
  }])).values()];
  if (!jumps.length) {
    jumps = (state.reviewResult?.candidates || []).map((candidate) => ({
      time: (candidate.onset_ms ?? candidate.start_ms) / 1000,
      name: "Suggested rep",
    })).filter((jump) => Number.isFinite(jump.time) && jump.time >= 0);
  }
  jumps.sort((a, b) => a.time - b.time);
  return `<div class="replay-controls" id="replay-controls" role="group" aria-label="Video playback controls">
    <div class="replay-timeline"><input type="range" data-replay-scrub min="0" max="0" step="0.01" value="0" aria-label="Seek through video" disabled><output data-replay-time aria-label="Playback time">0:00.0 / 0:00.0</output></div>
    <div class="replay-control-row"><button type="button" data-replay-play disabled>Play</button><button type="button" data-replay-offset="-5" aria-label="Back five seconds" disabled>−5 s</button><button type="button" data-replay-offset="5" aria-label="Forward five seconds" disabled>+5 s</button><label class="replay-speed">Speed<select data-replay-speed aria-label="Playback speed" disabled><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button type="button" data-replay-fullscreen disabled>Full screen</button></div>
    <div class="replay-jump-row"><label>Jump to time<input type="text" data-replay-jump placeholder="0:12.5 or 12.5" aria-label="Timestamp in seconds or minutes and seconds" disabled></label><button type="button" data-replay-go disabled>Go</button><span class="helper">Seconds, m:ss, or h:mm:ss</span></div>
    <p class="replay-control-status helper" data-replay-status role="status"></p>
    ${jumps.length ? `<div class="replay-timestamps" aria-label="Movement timestamps">${jumps.map((jump, index) => `<button type="button" data-replay-time-jump="${jump.time}" disabled>${e(jump.name)} ${index + 1} · ${e(timeLabel(jump.time))}</button>`).join("")}</div>` : ""}
  </div>`;
}

export function mountReplayControls(video, root) {
  if (!video || !root) return () => {};
  const scrub = root.querySelector("[data-replay-scrub]");
  const time = root.querySelector("[data-replay-time]");
  const play = root.querySelector("[data-replay-play]");
  const speed = root.querySelector("[data-replay-speed]");
  const jump = root.querySelector("[data-replay-jump]");
  const status = root.querySelector("[data-replay-status]");
  const listeners = [];
  const listen = (target, event, handler) => {
    target.addEventListener(event, handler);
    listeners.push(() => target.removeEventListener(event, handler));
  };
  const hasDuration = () => Number.isFinite(video.duration) && video.duration > 0;
  function update() {
    const ready = hasDuration();
    for (const control of root.querySelectorAll("button, input, select")) {
      control.disabled = !ready;
      if (control.hasAttribute("data-replay-time-jump") && ready)
        control.disabled = Number(control.dataset.replayTimeJump) > video.duration;
    }
    scrub.max = ready ? video.duration : 0;
    scrub.value = video.currentTime || 0;
    time.textContent = `${timeLabel(video.currentTime)} / ${timeLabel(video.duration)}`;
    play.textContent = video.paused || video.ended ? "Play" : "Pause";
    play.setAttribute("aria-label", video.paused || video.ended ? "Play video" : "Pause video");
    speed.value = String(video.playbackRate);
    const frame = video.parentElement;
    if (video.videoWidth && video.videoHeight)
      frame.style.setProperty("--video-aspect", video.videoWidth / video.videoHeight);
  }
  function seek(seconds) {
    if (!hasDuration()) return;
    video.currentTime = Math.max(0, Math.min(video.duration, seconds));
    status.textContent = "";
    update();
  }
  function jumpToInput() {
    const text = jump.value.trim();
    const parts = text.split(":");
    if (!/^\d+(?:\.\d+)?$/.test(text) && !/^\d+(?::\d{1,2}){0,1}:\d{1,2}(?:\.\d+)?$/.test(text)) {
      status.textContent = "Enter seconds (12.5), minutes and seconds (0:12.5), or hours, minutes and seconds (1:02:12).";
      return;
    }
    if (parts.slice(1).some((part) => Number(part) >= 60)) {
      status.textContent = "Minutes and seconds after a colon must be below 60.";
      return;
    }
    const seconds = parts.reduce((total, part) => total * 60 + Number(part), 0);
    if (!hasDuration() || seconds > video.duration) {
      status.textContent = "That timestamp is past the end of this video.";
      return;
    }
    seek(seconds);
  }
  listen(play, "click", async () => {
    if (!video.paused && !video.ended) video.pause();
    else {
      if (video.ended) seek(0);
      try { await video.play(); }
      catch { status.textContent = "Playback could not start. Try the video's built-in play button."; }
    }
  });
  listen(scrub, "input", () => seek(Number(scrub.value)));
  listen(speed, "change", () => { video.playbackRate = Number(speed.value); });
  listen(root.querySelector("[data-replay-go]"), "click", jumpToInput);
  listen(jump, "keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); jumpToInput(); }
  });
  for (const button of root.querySelectorAll("[data-replay-offset]"))
    listen(button, "click", () => seek(video.currentTime + Number(button.dataset.replayOffset)));
  for (const button of root.querySelectorAll("[data-replay-time-jump]"))
    listen(button, "click", () => { video.pause(); seek(Number(button.dataset.replayTimeJump)); });
  listen(root.querySelector("[data-replay-fullscreen]"), "click", async () => {
    try {
      if (video.requestFullscreen) await video.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
      else status.textContent = "Full screen isn't available in this browser.";
    } catch { status.textContent = "Full screen isn't available here. You can still use the playback controls below."; }
  });
  for (const event of ["loadedmetadata", "durationchange", "timeupdate", "play", "pause", "ended", "seeked", "ratechange"])
    listen(video, event, update);
  update();
  return () => listeners.forEach((remove) => remove());
}

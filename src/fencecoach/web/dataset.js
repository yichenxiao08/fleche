import { api } from "./api-client.js";
import { footworkPanel } from "./motion.js";
const $ = (id) => document.getElementById(id);
const escape = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const pretty = (s) => String(s).replaceAll("_", " ");
let inventory,
  current,
  labels,
  selection = 0,
  dirty = false,
  saving = false,
  draftDirty = false,
  activeSegment = -1;
const base = () => `/api/datasets/${current.collection}/${current.clip_id}`;
const form = $("segment-form"),
  video = $("dataset-video");
const status = (message) => {
  $("dataset-status").textContent = message;
  updateSaveButtons();
};
function editorStatus(message) {
  $("editor-mode").textContent = message;
  status(message);
}
function reviewerStatus(message) {
  $("review-feedback").textContent = message;
  status(message);
}
function sourceStatus(message) {
  $("source-status").textContent = message;
  status(message);
}
const sourceClassCount = (name) =>
  inventory.training_readiness.classes[name]?.reviewed_intervals || 0;
function sourceOrder() {
  return [...inventory.clips].sort((a, b) => {
    if ($("queue-order").value === "name")
      return a.clip_id.localeCompare(b.clip_id);
    const priority = (c) =>
      c.disagreements
        ? 0
        : c.draft_classes?.includes("fleche")
          ? 1
          : c.annotation_counts.provisional
            ? 2
            : 3;
    const rarity = (c) =>
      Math.min(...(c.draft_classes || []).map(sourceClassCount), Infinity);
    return (
      priority(a) - priority(b) ||
      rarity(a) - rarity(b) ||
      a.clip_id.localeCompare(b.clip_id)
    );
  });
}
function renderReadiness() {
  const r = inventory.training_readiness;
  $("readiness-summary").textContent =
    `Training readiness · ${r.reviewed_clips} / ${r.eligible_clips} clips reviewed`;
  const rows = Object.entries(r.classes).sort((a, b) =>
    a[0].localeCompare(b[0]),
  );
  const people = Object.entries(r.athletes || {});
  $("training-readiness").innerHTML =
    `<div class="readiness-heading"><div><span class="eyebrow">TRAINING DATA</span><h2 id="training-readiness-title">Reviewed movement labels</h2><p>${r.reviewed_clips} of ${r.eligible_clips} eligible clips have confident, usable reviews.</p></div><span class="readiness-badge">${people.length} identified athletes</span></div><p class="readiness-note">These counts show reviewed intervals, not usable training windows. Unsure labels and excluded intervals stay out. The strict training check also evaluates pose visibility, athlete diversity, recording sessions, camera setups, source integrity and held-out fencers. Collection targets are starting points, not fencing technique standards.</p><div class="readiness-grid">${rows.map(([name, c]) => `<div class="readiness-item"><strong>${escape(pretty(name))}</strong><span>${c.reviewed_intervals} usable reviewed intervals</span><small>${c.athletes || 0} athletes / ${c.clips} clips / ${c.independent_groups} source groups</small></div>`).join("")}</div><button id="check-training-readiness" type="button">Check training readiness</button><div id="strict-readiness-report" aria-live="polite"></div><details><summary>Progress by athlete</summary>${people.length ? `<div class="readiness-table"><table><thead><tr><th>Athlete</th><th>Intervals</th><th>Clips</th><th>Sessions</th><th>Camera setups</th></tr></thead><tbody>${people.map(([id, c]) => `<tr><td>${escape(id)}</td><td>${c.intervals}</td><td>${c.clips}</td><td>${c.sessions}</td><td>${c.camera_setups}</td></tr>`).join("")}</tbody></table></div>` : "<p>No confident labels have an athlete ID yet.</p>"}<p>${r.intervals_missing_athlete_id || 0} reviewed intervals still need an athlete ID or matching track. Reuse IDs for the same person across clips.</p></details>`;
}
function renderStrictReadiness(report) {
  const passed = report.checks.filter((item) => item.passed).length;
  const classes =
    Object.entries(report.usable_windows)
      .map(
        ([label, count]) =>
          `<li>${escape(pretty(label))}: ${count} usable windows</li>`,
      )
      .join("") || "<li>No usable reviewed windows yet.</li>";
  const blocked = report.checks
    .filter((item) => !item.passed)
    .map(
      (item) =>
        `<li>${escape(item.label)}: ${item.actual} / ${item.required}</li>`,
    )
    .join("");
  $("strict-readiness-report").innerHTML =
    `<div class="strict-readiness ${report.training_ready ? "ready" : "blocked"}"><strong>${report.training_ready ? "Ready for candidate training" : "Training blocked"}</strong><span>${passed} of ${report.checks.length} checks passed. The report does not claim that a trained model will be accurate.</span><p>Usable reviewed windows by class</p><ul>${classes}</ul>${blocked ? `<p>Still needed</p><ul>${blocked}</ul>` : ""}</div>`;
}
function renderSources() {
  renderReadiness();
  const query = $("source-filter").value.toLowerCase();
  const draftsOnly = $("drafts-only").checked;
  const clips = sourceOrder()
    .filter((c) =>
      `${c.clip_id} ${c.teaching_topic} ${c.description || ""} ${c.athlete_id || ""}`
        .toLowerCase()
        .includes(query),
    )
    .filter(
      (c) =>
        !draftsOnly ||
        (c.annotation_counts.provisional || 0) > 0 ||
        (current?.collection === c.collection &&
          current?.clip_id === c.clip_id),
    );
  $("source-list").innerHTML =
    clips
      .map(
        (c) =>
          `<button class="dataset-source ${current?.clip_id === c.clip_id && current?.collection === c.collection ? "active" : ""}" data-collection="${escape(c.collection)}" data-clip="${escape(c.clip_id)}">${escape(pretty(c.clip_id))}<small>${c.training_eligible ? "Modern sport fencing" : "Excluded: " + escape(c.training_domain)} / ${escape(c.collection)} / ${(c.duration_ms / 1000).toFixed(1)} s</small><small>${c.annotation_counts.provisional || 0} drafts / ${c.annotation_counts.reviewed || 0} reviewed${c.disagreements ? ` / ${c.disagreements} disagreements` : ""}</small></button>`,
      )
      .join("") ||
    `<p class="empty-note">No clips with draft labels match this view. Turn off the draft filter or clear your search to browse more footage.</p>`;
}
function recordSummary(item) {
  return `${escape(item.status)} / ${escape(item.certainty || "unsure")}${item.suggested_by ? ` / suggested by ${escape(item.suggested_by)}` : ""}${item.reviewed_by ? ` / reviewed by ${escape(item.reviewed_by)}` : ""}${item.exclusion_flags?.length ? ` / excluded: ${escape(item.exclusion_flags.map(pretty).join(", "))}` : ""}`;
}
function findIntervalOverlap(segments) {
  const ordered = segments
    .map((segment, index) => ({ ...segment, index }))
    .filter((segment) => segment.status !== "rejected")
    .sort(
      (a, b) =>
        a.track_id.localeCompare(b.track_id) ||
        a.layer.localeCompare(b.layer) ||
        a.start_ms - b.start_ms ||
        a.end_ms - b.end_ms,
    );
  let furthest = null;
  for (const segment of ordered) {
    const sameGroup =
      furthest &&
      furthest.track_id === segment.track_id &&
      furthest.layer === segment.layer;
    if (sameGroup && segment.start_ms < furthest.end_ms)
      return { first: furthest, second: segment };
    if (!sameGroup || !furthest || segment.end_ms > furthest.end_ms)
      furthest = segment;
  }
  return null;
}
function renderSegments() {
  const selected = labels.segments[activeSegment];
  $("draft-selection").textContent = selected
    ? `Selected: ${pretty(selected.label)} · ${(selected.start_ms / 1000).toFixed(2)}–${(selected.end_ms / 1000).toFixed(2)} s · ${selected.status}`
    : "Select a draft to begin review.";
  $("segment-list").innerHTML =
    labels.segments
      .map((s, i) => {
        const reviewState =
          s.status === "reviewed"
            ? s.reviewed_at
              ? "Reviewed and saved"
              : "Accepted · not saved"
            : s.status === "rejected"
              ? "Rejected · not saved"
              : "Draft · needs review";
        return `<div class="dataset-segment ${i === activeSegment ? "selected" : ""} ${s.status === "reviewed" ? "reviewed" : ""}" data-segment-index="${i}"><div class="segment-title"><strong>${escape(pretty(s.label))} / ${(s.start_ms / 1000).toFixed(3)}–${(s.end_ms / 1000).toFixed(3)} s</strong><span class="segment-review-state">${escape(reviewState)}</span></div><p>${escape(s.layer)} / ${escape(s.track_id)} / ${recordSummary(s)}</p><p>Boundary uncertainty: ${s.boundary_uncertainty_ms} ms${s.suggestion_disagreement ? " / model and pose disagree" : ""}</p><p>${escape(s.note)}</p><div class="segment-actions"><button type="button" data-edit="${i}">Edit interval</button><button type="button" data-confirm="${i}">Accept as correct</button><button type="button" data-unsure="${i}">Mark unsure</button><button type="button" data-reject="${i}">Reject</button><button type="button" data-remove="${i}">Remove</button></div></div>`;
      })
      .join("") ||
    "<p>No timestamped labels yet. Use Add pose suggestions to create drafts, or add an interval below.</p>";
  updateSaveButtons();
}
function updateSaveButtons() {
  const text = saving
    ? "Saving…"
    : dirty
      ? "Save review · changes pending"
      : "Save review";
  for (const id of ["save-labels"]) {
    const button = $(id);
    if (!button) continue;
    button.disabled = saving;
    button.textContent = text;
  }
}
function renderEvents() {
  $("event-list").innerHTML =
    labels.events
      .map(
        (event, i) =>
          `<div class="dataset-segment"><strong>${escape(pretty(event.kind))}</strong><p>${escape(event.track_id)} / ${recordSummary(event)}</p><label>Time (seconds)<input type="number" min="0" step="0.001" max="${current.duration_ms / 1000}" value="${event.time_ms / 1000}" data-event-time="${i}" /></label><button data-event-seek="${i}">View</button><button data-event-confirm="${i}">Accept (confident)</button><button data-event-unsure="${i}">Mark unsure</button><button data-event-reject="${i}">Reject</button><button data-event-remove="${i}">Remove</button></div>`,
      )
      .join("") || "<p>No event markers yet.</p>";
}
function movementOptions() {
  form.elements.label.innerHTML = inventory.ontology[form.elements.layer.value]
    .map((name) => `<option value="${name}">${escape(pretty(name))}</option>`)
    .join("");
}
function clearEditor() {
  form.reset();
  form.elements.track.value = $("primary-track-id").value || "primary";
  delete form.dataset.editIndex;
  draftDirty = false;
  movementOptions();
  $("interval-extras").open = false;
  $("editor-mode").textContent =
    "Choose Edit interval to load a label here, or fill out the form to add a new interval.";
  $("apply-interval").textContent = "Add interval";
}
function editSegment(index) {
  if (draftDirty) {
    editorStatus(
      "This editor has unapplied changes. Apply interval edits, or Clear to discard them, before selecting another interval.",
    );
    $("apply-interval").focus();
    return;
  }
  const s = labels.segments[index];
  if (!s) return;
  activeSegment = index;
  form.elements.start.value = s.start_ms / 1000;
  form.elements.end.value = s.end_ms / 1000;
  form.elements.layer.value = s.layer;
  movementOptions();
  form.elements.label.value = s.label;
  form.elements.track.value = s.track_id;
  form.elements.note.value = s.note;
  form.elements.boundary.value = s.boundary_uncertainty_ms;
  for (const box of form.querySelectorAll('[name="exclusion"]'))
    box.checked = (s.exclusion_flags || []).includes(box.value);
  $("interval-extras").open = Boolean(s.exclusion_flags?.length);
  form.dataset.editIndex = index;
  $("editor-mode").textContent =
    `Editing ${pretty(s.label)} · ${(s.start_ms / 1000).toFixed(2)}–${(s.end_ms / 1000).toFixed(2)} s. Make changes below, then Apply interval edits.`;
  $("apply-interval").textContent = "Apply interval edits";
  video.pause();
  video.currentTime = s.start_ms / 1000;
  renderSegments();
  $("editor-mode").textContent =
    `Editing ${pretty(s.label)} · ${(s.start_ms / 1000).toFixed(2)}–${(s.end_ms / 1000).toFixed(2)} s. Apply edits to update the clip.`;
  status(
    `Loaded ${pretty(s.label)} into the editor. The selected interval is paused in the video.`,
  );
  form.elements.start.focus({ preventScroll: true });
  $("segment-list")
    .querySelector(`[data-segment-index="${index}"]`)
    ?.scrollIntoView({ block: "nearest" });
}
function advanceDraft(direction) {
  if (!labels || draftDirty || saving) {
    if (draftDirty)
      editorStatus(
        "Apply interval edits, or Clear to discard them, before moving to another draft.",
      );
    return;
  }
  const queue = labels.segments
    .map((s, index) => ({ ...s, index }))
    .filter((s) => s.status === "provisional")
    .sort(
      (a, b) =>
        Number(b.suggestion_disagreement) - Number(a.suggestion_disagreement) ||
        Number(b.label === "fleche") - Number(a.label === "fleche") ||
        sourceClassCount(a.label) - sourceClassCount(b.label) ||
        { low: 0, medium: 1, high: 2 }[a.confidence] -
          { low: 0, medium: 1, high: 2 }[b.confidence] ||
        a.start_ms - b.start_ms,
    );
  if (!queue.length) {
    status("No pending draft intervals in this clip.");
    return;
  }
  const position = queue.findIndex((s) => s.index === activeSegment);
  const next =
    position < 0
      ? direction > 0
        ? 0
        : queue.length - 1
      : (position + direction + queue.length) % queue.length;
  editSegment(queue[next].index);
}
function setReview(item, certainty) {
  if (draftDirty) {
    editorStatus(
      "Apply interval edits, or Clear to discard them, before accepting or rejecting this label.",
    );
    return false;
  }
  const reviewer = $("reviewer").value.trim();
  if (!reviewer || reviewer.toLowerCase() === "unreviewed") {
    reviewerStatus(
      "Enter your name here, then click Accept as correct again. Your label has not changed yet.",
    );
    $("reviewer").focus();
    $("reviewer").scrollIntoView({ behavior: "smooth", block: "center" });
    return false;
  }
  if (
    item.layer === "tactics" &&
    ($("reviewer-role").value !== "coach" || !$("opponent-visible").checked)
  ) {
    reviewerStatus(
      "Tactical labels require coach review and visible opponent context.",
    );
    return false;
  }
  item.status = "reviewed";
  item.certainty = certainty;
  item.reviewed_by = reviewer;
  item.reviewed_at = null;
  dirty = true;
  reviewerStatus(
    certainty === "confident"
      ? "Accepted locally. Click Save review to keep this label."
      : "Marked unsure and excluded from training. Click Save review to keep this decision.",
  );
  return true;
}
function makeDraft(item) {
  item.status = "provisional";
  item.reviewed_by = "";
  item.reviewed_at = null;
  item.certainty = "unsure";
  dirty = true;
}
async function openClip(collection, id) {
  if (saving || dirty || draftDirty) {
    sourceStatus(
      "This clip has unsaved work. Save it before changing clips, or clear the interval editor to discard its draft.",
    );
    return;
  }
  sourceStatus(`Opening ${pretty(id)}…`);
  const request = ++selection;
  const clip = inventory.clips.find(
    (c) => c.collection === collection && c.clip_id === id,
  );
  const marked = await api(`/api/datasets/${collection}/${id}/labels`);
  if (request !== selection) return;
  current = clip;
  labels = marked;
  labels.events ||= [];
  activeSegment = -1;
  $("dataset-review").hidden = false;
  $("clip-title").textContent = pretty(id);
  video.src = `${base()}/source`;
  video.playbackRate = Number($("playback-speed").value);
  $("source-credit").innerHTML =
    `${escape(current.attribution)} / <a href="${escape(current.source_page)}" target="_blank" rel="noreferrer">Source</a> / ${escape(current.license)}`;
  $("source-context").textContent =
    `${current.training_eligible ? "Modern fencing source approved for review." : "Excluded from training."} ${current.curation_note || ""} ${current.mvp_scope_reason || ""} Split group: ${current.split_group}.`;
  $("reviewer").value =
    labels.reviewer_role === "assistant" || labels.reviewer === "unreviewed"
      ? ""
      : labels.reviewer;
  $("reviewer-role").value =
    labels.reviewer_role === "coach" ? "coach" : "athlete";
  for (const [id, key] of [
    ["track-description", "track_description"],
    ["weapon", "weapon"],
    ["facing", "facing"],
    ["camera-motion", "camera_motion"],
    ["primary-track-id", "primary_track_id"],
    ["athlete-id", "athlete_id"],
    ["recording-session-id", "recording_session_id"],
    ["camera-setup-id", "camera_setup_id"],
  ])
    $(id).value = labels[key] || (id === "primary-track-id" ? "primary" : "");
  $("opponent-visible").checked = labels.opponent_visible;
  for (const key of ["x", "y", "width", "height"])
    $(`crop-${key}`).value = labels.crop[key];
  $("footwork-summary").innerHTML = "";
  $("load-suggestions").disabled = !clip.prepared;
  if (clip.prepared)
    api(`${base()}/poses`)
      .then((result) => {
        if (request === selection)
          $("footwork-summary").innerHTML = footworkPanel(result);
      })
      .catch((error) => {
        if (request === selection) status(error.message);
      });
  $("segment-exclusions").innerHTML = (inventory.exclusion_flags || [])
    .map(
      (flag) =>
        `<label><input name="exclusion" type="checkbox" value="${escape(flag)}" /> ${escape(pretty(flag))}</label>`,
    )
    .join("");
  $("event-buttons").innerHTML = (inventory.event_kinds || [])
    .map(
      (kind) =>
        `<button type="button" data-event-mark="${kind}">Mark ${escape(pretty(kind))}</button>`,
    )
    .join("");
  clearEditor();
  renderSources();
  renderSegments();
  renderEvents();
  $("source-status").textContent = "";
  status(
    `${labels.segments.length} intervals and ${labels.events.length} event markers. Choose Edit interval to change one, or use the clip actions to accept/reject it.`,
  );
}
$("show-excluded").addEventListener("change", async () => {
  try {
    inventory = await api(
      `/api/datasets?include_excluded=${$("show-excluded").checked}`,
    );
    renderSources();
  } catch (error) {
    status(error.message);
  }
});
$("source-filter").addEventListener("input", renderSources);
$("queue-order").addEventListener("change", renderSources);
$("drafts-only").addEventListener("change", renderSources);
$("training-readiness").addEventListener("click", async (event) => {
  if (!event.target.closest("#check-training-readiness")) return;
  const button = $("check-training-readiness");
  button.disabled = true;
  button.textContent = "Checking reviewed data…";
  try {
    renderStrictReadiness(
      await api("/api/datasets/readiness?task=gesture&window_ms=750"),
    );
  } catch (error) {
    $("strict-readiness-report").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Check training readiness";
  }
});
$("source-list").addEventListener("click", (event) => {
  const b = event.target.closest("[data-clip]");
  if (b)
    openClip(b.dataset.collection, b.dataset.clip).catch((error) =>
      status(error.message),
    );
});
video.addEventListener("timeupdate", () => {
  $("video-time").textContent = `${video.currentTime.toFixed(3)} s`;
});
function stepFrame(sign) {
  if (!current) return;
  video.pause();
  video.currentTime = Math.max(
    0,
    Math.min(
      Number.isFinite(video.duration)
        ? video.duration
        : current.duration_ms / 1000,
      video.currentTime +
        sign / (Number(current.fps) > 0 ? Number(current.fps) : 30),
    ),
  );
}
function markBoundary(field) {
  if (!current) return;
  form.elements[field].value = video.currentTime.toFixed(3);
  draftDirty = true;
  editorStatus(
    `Marked ${field} at ${video.currentTime.toFixed(3)} s. Apply interval edits to update this draft.`,
  );
}
$("playback-speed").addEventListener("change", () => {
  video.playbackRate = Number($("playback-speed").value);
});
$("step-back").addEventListener("click", () => stepFrame(-1));
$("step-forward").addEventListener("click", () => stepFrame(1));
$("next-draft").addEventListener("click", () => advanceDraft(1));
$("previous-draft").addEventListener("click", () => advanceDraft(-1));
$("cancel-edit").addEventListener("click", () => {
  clearEditor();
  activeSegment = -1;
  renderSegments();
  editorStatus("Editor cleared. Your saved labels were not changed.");
});
document.addEventListener("keydown", (event) => {
  if (
    !current ||
    saving ||
    event.repeat ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.target?.isContentEditable ||
    event.target?.matches?.("input, textarea, select")
  )
    return;
  const key = event.key.toLowerCase();
  if (event.code === "Space" && !event.target?.matches?.("button, a")) {
    event.preventDefault();
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  } else if (key === "arrowleft" || key === "arrowright") {
    event.preventDefault();
    stepFrame(key === "arrowleft" ? -1 : 1);
  } else if (key === "i" || key === "o") {
    event.preventDefault();
    markBoundary(key === "i" ? "start" : "end");
  } else if (key === "n" || key === "p") {
    event.preventDefault();
    advanceDraft(key === "n" ? 1 : -1);
  } else if (key === "c" && activeSegment >= 0) {
    event.preventDefault();
    form.elements.label.focus();
  } else if ((key === "a" || key === "r") && activeSegment >= 0) {
    event.preventDefault();
    if (draftDirty) {
      editorStatus(
        "Apply interval edits, or Clear to discard them, before changing labels.",
      );
      return;
    }
    const item = labels.segments[activeSegment];
    if (key === "a") setReview(item, "confident");
    else {
      makeDraft(item);
      item.status = "rejected";
      status("Rejected locally. Save review to persist it.");
    }
    renderSegments();
  }
});
form.elements.layer.addEventListener("change", movementOptions);
form.addEventListener("input", () => {
  draftDirty = true;
  $("editor-mode").textContent =
    form.dataset.editIndex !== undefined
      ? "Interval changes are not applied yet. Click Apply interval edits, or Clear to discard them."
      : "New interval is not applied yet. Click Add interval, or Clear to discard it.";
});
$("dataset-review").addEventListener("click", (event) => {
  const b = event.target.closest("button");
  if (!b || saving || !labels) return;
  if (b.dataset.mark) {
    markBoundary(b.dataset.mark);
    return;
  }
  if (b.dataset.edit !== undefined) {
    editSegment(Number(b.dataset.edit));
    return;
  }
  if (b.dataset.eventMark) {
    const time = Math.round(video.currentTime * 1000),
      track = $("primary-track-id").value.trim() || "primary";
    if (
      time > current.duration_ms ||
      labels.events.some(
        (e) =>
          e.kind === b.dataset.eventMark &&
          e.time_ms === time &&
          e.track_id === track &&
          e.status !== "rejected",
      )
    ) {
      status("This marker already exists or lies outside the clip.");
      return;
    }
    labels.events.push({
      id: crypto.randomUUID(),
      kind: b.dataset.eventMark,
      time_ms: time,
      track_id: track,
      status: "provisional",
      origin: "human",
      suggested_by: "",
      reviewed_by: "",
      certainty: "unsure",
      exclusion_flags: [],
      confidence: "medium",
      boundary_uncertainty_ms: 250,
      note: "",
    });
    dirty = true;
    renderEvents();
    status("Event marked as a draft. Review it and save.");
    return;
  }
  if (b.dataset.eventSeek !== undefined) {
    video.pause();
    video.currentTime =
      labels.events[Number(b.dataset.eventSeek)].time_ms / 1000;
    return;
  }
  for (const [prefix, records] of [
    ["", labels.segments],
    ["event", labels.events],
  ]) {
    for (const action of ["confirm", "unsure", "reject", "remove"]) {
      const property = prefix
        ? prefix + action[0].toUpperCase() + action.slice(1)
        : action;
      if (b.dataset[property] === undefined) continue;
      if (draftDirty) {
        editorStatus(
          "Apply interval edits, or Clear to discard them, before changing labels.",
        );
        return;
      }
      const index = Number(b.dataset[property]),
        item = records[index];
      if (action === "confirm" || action === "unsure")
        setReview(item, action === "confirm" ? "confident" : "unsure");
      else if (action === "reject") {
        makeDraft(item);
        item.status = "rejected";
        status("Rejected locally. Save review to persist it.");
      } else {
        records.splice(index, 1);
        dirty = true;
        if (!prefix) {
          clearEditor();
          activeSegment = -1;
        }
      }
      renderSegments();
      renderEvents();
      return;
    }
  }
});
$("event-list").addEventListener("change", (event) => {
  if (event.target.dataset.eventTime === undefined) return;
  const item = labels.events[Number(event.target.dataset.eventTime)],
    value = Number(event.target.value) * 1000;
  if (
    !event.target.value ||
    !Number.isFinite(value) ||
    value < 0 ||
    value > current.duration_ms
  ) {
    status("Choose an event time inside the video.");
    renderEvents();
    return;
  }
  item.time_ms = Math.round(value);
  makeDraft(item);
  renderEvents();
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  const d = new FormData(form),
    index = form.dataset.editIndex,
    original = index === undefined ? null : labels.segments[Number(index)];
  const item = {
    ...original,
    id: original?.id || crypto.randomUUID(),
    start_ms: Math.round(Number(d.get("start")) * 1000),
    end_ms: Math.round(Number(d.get("end")) * 1000),
    layer: d.get("layer"),
    label: d.get("label"),
    track_id: d.get("track").trim(),
    note: d.get("note"),
    origin: original?.origin || "human",
    suggested_by: original?.suggested_by || "",
    confidence: original?.confidence || "medium",
    boundary_uncertainty_ms: Number(d.get("boundary")),
    exclusion_flags: d.getAll("exclusion"),
  };
  if (
    item.end_ms <= item.start_ms ||
    item.end_ms > current.duration_ms ||
    !item.track_id
  ) {
    editorStatus(
      "Could not apply: choose a start before the end, keep the end inside this video, and enter an athlete track.",
    );
    return;
  }
  makeDraft(item);
  if (index === undefined) {
    labels.segments.push(item);
    activeSegment = labels.segments.length - 1;
  } else {
    labels.segments[Number(index)] = item;
    activeSegment = Number(index);
  }
  clearEditor();
  renderSegments();
  status(
    "Interval applied to this clip. Inspect it, then accept and Save review to keep it.",
  );
});
$("load-suggestions").addEventListener("click", async () => {
  if (draftDirty) {
    editorStatus(
      "Apply interval edits, or Clear to discard them, before loading suggestions.",
    );
    return;
  }
  const request = selection;
  $("load-suggestions").disabled = true;
  status("Loading pose suggestions…");
  try {
    const proposed = await api(`${base()}/suggestions`);
    if (request !== selection || saving) return;
    let added = 0;
    for (const item of proposed.segments) {
      if (
        !labels.segments.some(
          (s) =>
            s.id === item.id ||
            (s.status !== "rejected" &&
              s.track_id === item.track_id &&
              s.layer === item.layer &&
              s.start_ms < item.end_ms &&
              s.end_ms > item.start_ms),
        )
      ) {
        labels.segments.push(item);
        added++;
      }
    }
    for (const item of proposed.events) {
      if (
        !labels.events.some(
          (e) =>
            e.id === item.id ||
            (e.kind === item.kind &&
              e.track_id === item.track_id &&
              e.time_ms === item.time_ms),
        )
      ) {
        labels.events.push(item);
        added++;
      }
    }
    dirty ||= added > 0;
    renderSegments();
    renderEvents();
    status(
      `Added ${added} draft suggestions. Existing intervals were kept; review the new items before saving.`,
    );
  } catch (error) {
    status(`Suggestions could not be loaded: ${error.message}`);
  } finally {
    if (request === selection) $("load-suggestions").disabled = false;
  }
});
for (const id of [
  "reviewer",
  "reviewer-role",
  "track-description",
  "weapon",
  "facing",
  "camera-motion",
  "opponent-visible",
  "crop-x",
  "crop-y",
  "crop-width",
  "crop-height",
  "primary-track-id",
  "athlete-id",
  "recording-session-id",
  "camera-setup-id",
])
  $(id).addEventListener("input", () => {
    dirty = true;
    updateSaveButtons();
  });
window.addEventListener("beforeunload", (event) => {
  if (dirty || draftDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
function currentAnnotations() {
  return {
    ...labels,
    schema_version: inventory.label_schema_version,
    reviewer: $("reviewer").value.trim() || "unreviewed",
    reviewer_role: $("reviewer-role").value,
    primary_track_id: $("primary-track-id").value.trim() || "primary",
    athlete_id: $("athlete-id").value.trim(),
    recording_session_id: $("recording-session-id").value.trim(),
    camera_setup_id: $("camera-setup-id").value.trim(),
    track_description: $("track-description").value,
    weapon: $("weapon").value,
    facing: $("facing").value,
    camera_motion: $("camera-motion").value,
    opponent_visible: $("opponent-visible").checked,
    crop: Object.fromEntries(
      ["x", "y", "width", "height"].map((k) => [
        k,
        Number($(`crop-${k}`).value),
      ]),
    ),
  };
}
$("save-labels").addEventListener("click", async () => {
  if (draftDirty) {
    editorStatus(
      "Apply interval edits, or Clear to discard them, before saving this review.",
    );
    return;
  }
  const overlap = findIntervalOverlap(labels.segments);
  if (overlap) {
    const { first, second } = overlap;
    const overlapStart = Math.max(first.start_ms, second.start_ms) / 1000;
    const overlapEnd = Math.min(first.end_ms, second.end_ms) / 1000;
    activeSegment = second.index;
    renderSegments();
    status(
      `Cannot save yet: ${pretty(first.label)} (${(first.start_ms / 1000).toFixed(2)}–${(first.end_ms / 1000).toFixed(2)} s) overlaps ${pretty(second.label)} (${(second.start_ms / 1000).toFixed(2)}–${(second.end_ms / 1000).toFixed(2)} s) on ${second.track_id} / ${pretty(second.layer)} at ${overlapStart.toFixed(2)}–${overlapEnd.toFixed(2)} s. Adjust one interval or reject the incorrect one, then Save review again.`,
    );
    $("segment-list")
      .querySelector(`[data-segment-index="${second.index}"]`)
      ?.scrollIntoView({ block: "nearest" });
    return;
  }
  const b = $("save-labels");
  b.disabled = true;
  saving = true;
  b.textContent = "Saving…";
  status("Saving this clip review…");
  $("dataset-review").inert = true;
  try {
    labels = await api(`${base()}/labels`, {
      method: "PUT",
      body: JSON.stringify(currentAnnotations()),
    });
    dirty = false;
    inventory = await api(
      `/api/datasets?include_excluded=${$("show-excluded").checked}`,
    );
    renderSources();
    renderSegments();
    renderEvents();
    status(
      "Review saved. Exports and experimental training will update automatically in the background.",
    );
  } catch (error) {
    status(error.message);
  } finally {
    b.disabled = false;
    saving = false;
    $("dataset-review").inert = false;
    updateSaveButtons();
  }
});
$("export-labels").addEventListener("click", () => {
  if (draftDirty) {
    editorStatus(
      "Apply interval edits, or Clear to discard them, before exporting.",
    );
    return;
  }
  const url = URL.createObjectURL(
    new Blob(
      [
        JSON.stringify(
          { source: current, annotations: currentAnnotations() },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `${current.clip_id}-labels.json`;
  a.click();
  URL.revokeObjectURL(url);
});
try {
  inventory = await api(
    `/api/datasets?include_excluded=${$("show-excluded").checked}`,
  );
  renderSources();
  if (inventory.clips.length) {
    const first = sourceOrder()[0];
    await openClip(first.collection, first.clip_id);
  }
} catch (error) {
  status(error.message);
}

async function refreshAutomaticTraining() {
  try {
    const progress = await api("/api/datasets/automation");
    const element = $("automatic-training-status");
    if (progress.status === "completed") {
      element.textContent = `Automatic training complete · ${progress.usable_windows} usable windows · ${progress.automatic_drafts} automatic drafts · ${progress.promoted ? "validated model activated" : "experimental model; coach model unchanged"}`;
    } else if (progress.status === "failed") {
      element.textContent = `Automatic training needs attention: ${progress.error}`;
    } else {
      element.textContent = `Automatic training: ${progress.stage || progress.status}`;
    }
  } catch {
    $("automatic-training-status").textContent =
      "Automatic training status unavailable. Reconnecting…";
  }
}
await refreshAutomaticTraining();
setInterval(refreshAutomaticTraining, 5000);

import { api, sessionPath } from "./api-client.js";
import { groups } from "./ui.js";
function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}
export const state = {
  config: {},
  sessions: [],
  logs: [],
  plans: [],
  session: null,
  runs: [],
  run: null,
  screen: "train",
  drillId: "lunge",
  reviewRepIndex: 0,
  metricIndex: 0,
  groupIndex: 0,
  sampleOverlay: true,
  progressRange: "week",
  progressMonth: "",
  progressShowAllSessions: false,
  showLogForm: false,
  openLogEditor: false,
  reviewSavedSessionId: null,
  trendKey: "",
  libraryFilter: "all",
  mode: "local",
  question: "",
  pendingQuestion: "",
  partialReply: "",
  coachError: "",
  preferences: read("fencecoach.preferences", {
    goal: 3,
    skill: "beginner",
    saved: [],
  }),
  loading: true,
  loadingSession: false,
  generating: false,
  busy: false,
  error: "",
  draftClip: null,
  videoJob: null,
  videoResult: null,
  videoWindows: [],
  editingSavedTimes: false,
  savedTimingDraft: null,
  videoAnnotations: null,
  pendingMissedRep: null,
  videoJobs: [],
  reviewResult: null,
  videoOverlay: true,
};
// Treat persisted preferences as user data, not trusted renderable markup.
const stored = state.preferences || {};
state.preferences = {
  goal:
    Number.isInteger(stored.goal) && stored.goal >= 1 && stored.goal <= 14
      ? stored.goal
      : 3,
  skill: ["beginner", "intermediate"].includes(stored.skill)
    ? stored.skill
    : "beginner",
  saved: Array.isArray(stored.saved)
    ? stored.saved.filter((id) => ["lunge", "footwork", "control"].includes(id))
    : [],
};
let epoch = 0;
export function savePreferences() {
  try {
    localStorage.setItem("fencecoach.preferences", JSON.stringify(state.preferences));
  } catch {
    throw new Error(
      "Your browser couldn’t save these preferences. Check available storage.",
    );
  }
}
export async function initStore() {
  const [config, sessions, logs, plans] = await Promise.all([
    api("/api/config"),
    api("/api/sessions"),
    api("/api/training-logs"),
    api("/api/practice-plans"),
  ]);
  state.config = config;
  state.logs = logs;
  state.plans = plans;
  const ready = {
    local: config.local_ready,
    gemini: config.gemini_ready,
    bedrock: config.bedrock_ready,
  };
  state.mode = ready[config.provider]
    ? config.provider
    : config.gemini_ready
      ? "gemini"
      : config.local_ready
        ? "local"
        : config.bedrock_ready
          ? "bedrock"
          : "demo";
  state.sessions = sessions;
  let saved;
  try {
    saved = localStorage.getItem("fencecoach.session");
  } catch {
    /* Optional storage. */
  }
  const latest = sessions.find((s) => s.session_id === saved) || sessions[0];
  if (latest) await selectSession(latest.session_id);
  state.loading = false;
}
export async function selectSession(id) {
  const ticket = ++epoch;
  state.loadingSession = true;
  try {
    const [session, runs] = await Promise.all([
      api(sessionPath(id)),
      api(`${sessionPath(id)}/reports`),
    ]);
    if (ticket !== epoch) return false;
    if (state.reviewSavedSessionId && id !== state.reviewSavedSessionId)
      state.reviewSavedSessionId = null;
    state.session = session;
    state.runs = runs;
    state.run = runs[0] || null;
    state.reviewRepIndex = 0;
    state.metricIndex = 0;
    state.groupIndex = 0;
    restoreRunFocus();
    state.question = "";
    state.coachError = "";
    state.partialReply = "";
    try {
      localStorage.setItem("fencecoach.session", id);
    } catch {
      /* Session still works. */
    }
    return true;
  } finally {
    if (ticket === epoch) state.loadingSession = false;
  }
}
export async function refreshSessions() {
  state.sessions = await api("/api/sessions");
}
export function restoreRunFocus() {
  const id = state.run?.focus_metric_id;
  if (!id || !state.session) return;
  const all = groups(state.session.metrics);
  const group = all.findIndex((items) =>
    items.some((metric) => metric.metric_id === id),
  );
  if (group >= 0) {
    state.groupIndex = group;
    state.metricIndex = all[group].findIndex((metric) => metric.metric_id === id);
  }
}
export async function loadSample() {
  const existing = state.sessions.find((s) => s.is_demo && !s.video_job_id);
  const session = existing || (await api("/api/demo", { method: "POST" }));
  if (!existing) await refreshSessions();
  await selectSession(session.session_id);
}
export async function generateReport(question) {
  if (!state.session || state.generating) return;
  const id = state.session.session_id;
  state.pendingQuestion = question;
  state.coachingJob = null;
  state.generating = true;
  state.partialReply = "";
  state.coachError = "";
  try {
    const job = await api(`${sessionPath(id)}/coaching-jobs`, {
      method: "POST",
      body: JSON.stringify({
        question,
        mode: state.mode,
        focus_metric_id: null,
      }),
    });
    state.coachingJob = job;
    try {
      localStorage.setItem("fencecoach.coachingJob", job.job_id);
    } catch {}
    const run = await waitForCoaching(job.job_id);
    if (state.session?.session_id === id) {
      state.runs.unshift(run);
      state.run = run;
      if (state.question === question) state.question = "";
    }
    return run;
  } catch (error) {
    state.coachError = error.message;
    throw error;
  } finally {
    state.generating = false;
    state.pendingQuestion = "";
  }
}

export async function waitForCoaching(id) {
  const started = Date.now();
  const limit = state.mode === "local" ? 100000 : 55000;
  while (Date.now() - started < limit) {
    let job;
    try {
      job = await api(`/api/coaching-jobs/${encodeURIComponent(id)}`, {
        signal: AbortSignal.timeout(8000),
      });
    } catch (error) {
      try {
        localStorage.removeItem("fencecoach.coachingJob");
      } catch {}
      throw new Error(
        "Lost connection to Flèche. Your question is kept; reconnect and try again.",
      );
    }
    state.coachingJob = job;
    const stage = document.getElementById("coaching-stage");
    if (stage) stage.textContent = job.stage;
    state.partialReply = job.partial_reply || "";
    const partial = document.getElementById("coaching-partial");
    if (partial) {
      partial.textContent = state.partialReply;
      partial.closest(".chat-message").hidden = !state.partialReply;
    }
    if (job.status === "completed") {
      try {
        localStorage.removeItem("fencecoach.coachingJob");
      } catch {}
      return api(`/api/reports/${encodeURIComponent(job.run_id)}`);
    }
    if (["failed", "cancelled"].includes(job.status)) {
      try {
        localStorage.removeItem("fencecoach.coachingJob");
      } catch {}
      throw new Error(
        job.status === "cancelled"
          ? "Reply stopped. You can edit your question and send it again."
          : job.error || "Coaching request failed. Try again.",
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  try {
    localStorage.removeItem("fencecoach.coachingJob");
  } catch {}
  try {
    await api(`/api/coaching-jobs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
      signal: AbortSignal.timeout(5000),
    });
  } catch {}
  throw new Error(
    "The coach took too long to respond. Your question is kept; try again.",
  );
}

export async function resumeCoaching(onState = () => {}) {
  let id;
  try {
    id = localStorage.getItem("fencecoach.coachingJob");
  } catch {}
  if (!id) return;
  let job;
  try {
    job = await api(`/api/coaching-jobs/${encodeURIComponent(id)}`);
  } catch (error) {
    try {
      localStorage.removeItem("fencecoach.coachingJob");
    } catch {}
    state.coachError = error.message;
    onState();
    return;
  }
  if (state.session?.session_id !== job.session_id) await selectSession(job.session_id);
  state.question = job.question || state.question;
  state.pendingQuestion = job.question || state.question;
  state.coachingJob = job;
  state.mode = job.mode || state.mode;
  state.generating = true;
  onState();
  try {
    const run = await waitForCoaching(id);
    if (state.session?.session_id === run.session_id) {
      state.runs = await api(`${sessionPath(run.session_id)}/reports`);
      state.run = run;
    }
  } catch (error) {
    state.coachError = error.message;
    throw error;
  } finally {
    state.generating = false;
    state.pendingQuestion = "";
    onState();
  }
}

export async function stopCoaching() {
  const id = state.coachingJob?.job_id;
  if (!id || !state.generating) return;
  await api(`/api/coaching-jobs/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    signal: AbortSignal.timeout(8000),
  });
}

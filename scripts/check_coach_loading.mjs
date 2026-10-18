// Run with: node --experimental-vm-modules scripts/check_coach_loading.mjs
// Exercise the actual store and view while the POST is still unresolved.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { SourceTextModule } from "node:vm";

// Load browser ES modules without changing their package type or mocking imports.
const modules = new Map();
async function load(url) {
  if (!modules.has(url.href)) modules.set(url.href, readFile(url, "utf8").then(
    (source) => new SourceTextModule(source, { identifier: url.href }),
  ));
  return modules.get(url.href);
}
async function importWeb(path) {
  const module = await load(new URL(path, import.meta.url));
  await module.link((specifier, parent) => load(new URL(specifier, parent.identifier)));
  await module.evaluate();
  return module.namespace;
}

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => storage.delete(key),
};
globalThis.document = { getElementById: () => null };
const { state, generateReport, resumeCoaching } = await importWeb("../src/fencecoach/web/store.js");
const { coach } = await importWeb("../src/fencecoach/web/views.js");

const previous = {
  run_id: "previous",
  session_id: "clip",
  question: "Previous arm question",
  created_at: "2026-10-18T10:00:00Z",
  response_kind: "conversation",
  report: { summary: "Previous answer.", observations: [] },
  sources: [],
};
const current = {
  ...previous,
  run_id: "current",
  question: "Current torso question",
  created_at: "2026-10-18T10:01:00Z",
  report: { summary: "Current answer.", observations: [] },
};
state.session = { session_id: "clip", title: "Practice", metrics: [] };
state.sessions = [state.session];
state.runs = [previous];
state.run = previous;
state.coachingJob = { job_id: "old-job", question: previous.question };
state.question = current.question;
state.mode = "gemini";

let resolvePost;
const response = (value) => ({ ok: true, json: async () => value });
globalThis.fetch = async (path, options) => {
  if (options.method === "POST") {
    assert.equal(JSON.parse(options.body).question, current.question);
    return new Promise((resolve) => { resolvePost = resolve; });
  }
  if (path === "/api/coaching-jobs/new-job")
    return response({ job_id: "new-job", status: "completed", run_id: current.run_id });
  if (path === "/api/reports/current") return response(current);
  throw new Error(`Unexpected request: ${path}`);
};

const pending = generateReport(current.question);
assert.equal(state.coachingJob, null, "The old job must not remain cancellable");
state.question = "Draft edited while waiting";
const pendingTurn = coach(state).match(/<article class="coach-turn">([\s\S]*?)<\/article>/)[1];
assert.ok(pendingTurn.includes(current.question));
assert.ok(!pendingTurn.includes(previous.question));
assert.ok(!pendingTurn.includes(state.question));
assert.ok(coach(state).includes(previous.question), "Keep completed history visible");
resolvePost(response({ job_id: "new-job", question: current.question }));
await pending;
assert.equal(state.run.run_id, current.run_id);
assert.equal(state.generating, false);
assert.equal(state.pendingQuestion, "");
assert.equal(state.question, "Draft edited while waiting");

globalThis.fetch = async () => { throw new Error("Simulated network failure"); };
await assert.rejects(generateReport("Failed question"), /Simulated network failure/);
assert.equal(state.generating, false);
assert.equal(state.pendingQuestion, "");
assert.equal(state.coachError, "Simulated network failure");
assert.equal(state.run.run_id, current.run_id);
storage.set("fencecoach.coachingJob", "resumed-job");
globalThis.fetch = async (path) => {
  if (path === "/api/coaching-jobs/resumed-job") return response({
    job_id: "resumed-job", session_id: "clip", question: "Resumed question",
    status: "completed", run_id: current.run_id,
  });
  if (path === "/api/reports/current") return response(current);
  if (path === "/api/sessions/clip/reports") return response([current, previous]);
  throw new Error(`Unexpected resume request: ${path}`);
};
await resumeCoaching(() => {
  if (state.generating) assert.equal(state.pendingQuestion, "Resumed question");
});
assert.equal(state.generating, false);
assert.equal(state.pendingQuestion, "");
console.log("Coach pending text, completion and failure checks passed.");

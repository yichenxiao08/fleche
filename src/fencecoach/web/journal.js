import { html } from "./html.js";
import { e, icon } from "./ui.js";
import { api } from "./api-client.js";

export function journalRows(logs) {
  return html`<div class="journal-list">
    ${logs
      .slice(0, 60)
      .map(
        (l) =>
          html`<article class="journal-entry">
            <div>
              <strong>${e(l.focus)}</strong
              ><small
                >${e(l.practiced_on)} · ${l.duration_minutes} min · Effort
                ${l.effort}/10</small
              >
              <p>${e(l.notes)}</p>
              ${l.session_id
                ? `<button class="text-action" data-session="${e(l.session_id)}">Open video review ${icon("arrow")}</button>`
                : ""}
            </div>
            <button class="text-action" data-log-edit="${e(l.log_id)}">Edit</button>
          </article>`,
      )
      .join("") ||
    '<p class="empty-note">Log today’s practice, even without a video.</p>'}
  </div>`;
}
export function logForm(state) {
  const log = state.editingLog || {},
    today = new Date(),
    visible = Boolean(state.showLogForm || state.editingLog);
  today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
  return html`<form
    id="training-log-form"
    class="progress-log-form"
    data-log-id="${e(log.log_id || "")}"
    ${visible ? "" : "hidden"}
  >
    <input type="hidden" name="drill_id" value="${e(log.drill_id || "")}" />
    <div class="form-row">
      <label class="field"
        ><span>Practice date</span
        ><input
          name="practiced_on"
          type="date"
          value="${e(log.practiced_on || today.toISOString().slice(0, 10))}"
          required /></label
      ><label class="field"
        ><span>Minutes</span
        ><input
          name="duration_minutes"
          type="number"
          min="1"
          max="720"
          value="${log.duration_minutes || 15}"
          required
      /></label>
    </div>
    <label class="field"
      ><span>Focus</span
      ><input
        name="focus"
        maxlength="100"
        value="${e(log.focus || "Footwork")}"
        required /></label
    ><label class="field"
      ><span>Effort / 1–10</span
      ><input
        name="effort"
        type="number"
        min="1"
        max="10"
        value="${log.effort || 5}"
        required /></label
    ><label class="field"
      ><span>Link a video review (optional)</span
      ><select name="session_id">
        <option value="">No video</option>
        ${state.sessions
          .filter((s) => !s.is_demo)
          .map(
            (s) =>
              html`<option
                value="${e(s.session_id)}"
                ${s.session_id === log.session_id ? "selected" : ""}
              >
                ${e(s.title)}
              </option>`,
          )
          .join("")}
      </select></label
    ><label class="field"
      ><span>What did you work on?</span
      ><textarea name="notes" maxlength="2000" rows="3">
${e(log.notes || "")}</textarea
      ></label
    ><button class="primary-action" type="submit">Save practice ${icon("arrow")}</button
    >${log.log_id
      ? html`<button
          class="text-action"
          type="button"
          data-log-delete="${e(log.log_id)}"
        >
          Delete log
        </button>`
      : ""}
  </form>`;
}
export function setupJournal({ state, render, go, notice, toast }) {
  document.addEventListener("click", async (event) => {
    const b = event.target.closest("button");
    if (!b || b.disabled) return;
    try {
      if (b.hasAttribute("data-log-new")) {
        const currentlyOpen = Boolean(state.showLogForm || state.editingLog);
        state.editingLog = null;
        state.showLogForm = !currentlyOpen;
        if (state.showLogForm && state.screen !== "progress") {
          state.openLogEditor = true;
          go("progress");
          return;
        }
        render({ keepScroll: true });
        if (state.showLogForm)
          document
            .getElementById("training-log-form")
            .scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (b.dataset.logEdit) {
        state.editingLog = state.logs.find((l) => l.log_id === b.dataset.logEdit);
        state.showLogForm = true;
        if (state.screen !== "progress") {
          state.openLogEditor = true;
          go("progress");
          return;
        }
        render({ keepScroll: true });
        document
          .getElementById("training-log-form")
          .scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (b.dataset.logDelete) {
        b.disabled = true;
        await api(`/api/training-logs/${encodeURIComponent(b.dataset.logDelete)}`, {
          method: "DELETE",
        });
        state.logs = await api("/api/training-logs");
        state.editingLog = null;
        state.showLogForm = false;
        render({ keepScroll: true });
        toast("Practice log deleted.");
      }
    } catch (error) {
      notice(error.message);
    }
  });
  document.addEventListener("submit", async (event) => {
    if (event.target.id !== "training-log-form") return;
    event.preventDefault();
    const form = event.target,
      data = Object.fromEntries(new FormData(form));
    data.duration_minutes = Number(data.duration_minutes);
    data.effort = Number(data.effort);
    data.session_id = data.session_id || null;
    data.drill_id = data.drill_id || null;
    const id = form.dataset.logId;
    form.querySelector('button[type="submit"]').disabled = true;
    try {
      await api(`/api/training-logs${id ? "/" + encodeURIComponent(id) : ""}`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      });
      state.logs = await api("/api/training-logs");
      state.editingLog = null;
      state.showLogForm = false;
      render({ keepScroll: true });
      toast("Practice saved to your journal.");
    } catch (error) {
      notice(error.message);
      form.querySelector('button[type="submit"]').disabled = false;
    }
  });
}

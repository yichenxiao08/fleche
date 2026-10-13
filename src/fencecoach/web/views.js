import { html } from "./html.js";
import { formatCoachText } from "./coach-text.js";
import { athleteReview } from "./athlete-review.js?v=20261012-review-layout-v1";
import {
  e,
  icon,
  primary,
  secondary,
  heading,
  photo,
  date,
  clock,
  label,
  pretty,
  groups,
  mean,
  displayMetric,
  practiceStats,
  periodStart,
  dayKey,
  trendChart,
} from "./ui.js";
import { journalRows, logForm } from "./journal.js?v=20261012-review-layout-v1";
import { drills, findDrill } from "./practice-library.js";
import { capture, getClipURL } from "./media.js";
import { frameStepControls } from "./replay-player.js?v=20261012-startup-fix-v1";
import {
  analysis,
  videoSetup,
  videoHistory,
} from "./video.js?v=20261012-review-layout-v1";
import {
  drillRows,
  sessionRows,
  sessionPicker,
  emptySession,
  modePicker,
  metricEvidence,
  reportContent,
  runDetails,
  measurementTable,
  selectedMetrics,
} from "./components.js";

function activityRows(
  items,
  id = "",
  emptyMessage = "Your first practice will appear here.",
) {
  if (!items.length) return `<p class="empty-note">${e(emptyMessage)}</p>`;
  return html`<div class="activity-list" ${id ? `id="${e(id)}"` : ""}>
    ${items
      .map((item) => {
        const isLog = Boolean(item.log_id),
          action = isLog
            ? `data-log-edit="${e(item.log_id)}"`
            : `data-session="${e(item.session_id)}"`,
          itemDate = date(
            item.practiced_on ? `${item.practiced_on}T12:00:00` : item.created_at,
          );
        return html`<article class="activity-entry">
          <button class="activity-main" ${action}>
            <span class="log-icon">${icon(isLog ? "calendar" : "target")}</span>
            <span class="activity-copy">
              <strong>${e(item.title)}</strong>
              <small>${e(itemDate)} · ${isLog ? "Practice log" : "Video review"}</small>
            </span>
            ${icon("chevron")}
          </button>
          ${item.session_id && isLog
            ? html`<button
                class="activity-secondary"
                data-session="${e(item.session_id)}"
              >
                Review
              </button>`
            : ""}
        </article>`;
      })
      .join("")}
  </div>`;
}

function monthCalendar(year, month, practicedDays, currentMonth, selectedMonth) {
  const first = new Date(year, month, 1),
    leading = (first.getDay() + 6) % 7,
    totalDays = new Date(year, month + 1, 0).getDate(),
    cellCount = Math.ceil((leading + totalDays) / 7) * 7,
    monthNames = Array.from({ length: 12 }, (_, index) =>
      new Date(2000, index, 1).toLocaleDateString(undefined, { month: "long" }),
    ),
    currentValue = Number(currentMonth.replace("-", "")),
    selectedValue = Number(selectedMonth.replace("-", "")),
    [currentYear, currentMonthNumber] = currentMonth.split("-").map(Number),
    minimumYear = currentYear - 80,
    years = Array.from({ length: 81 }, (_, index) => currentYear - index);
  return html`<section class="month-calendar" aria-label="Practice calendar">
    <div class="month-calendar-header">
      <button
        class="month-step"
        data-progress-month-step="-1"
        aria-label="Previous month"
        ${year <= minimumYear && month === 0 ? "disabled" : ""}
      >
        ${icon("back")}
      </button>
      <label class="month-picker">
        <select id="progress-month" aria-label="Month">
          ${monthNames
            .map(
              (name, index) =>
                html`<option
                  value="${index}"
                  ${month === index ? "selected" : ""}
                  ${year === currentYear && index + 1 > currentMonthNumber
                    ? "disabled"
                    : ""}
                >
                  ${e(name)}
                </option>`,
            )
            .join("")}
        </select>
      </label>
      <label class="month-picker year-picker">
        <select id="progress-year" aria-label="Year">
          ${years
            .map(
              (optionYear) =>
                html`<option
                  value="${optionYear}"
                  ${year === optionYear ? "selected" : ""}
                >
                  ${optionYear}
                </option>`,
            )
            .join("")}
        </select>
      </label>
      <button
        class="month-step"
        data-progress-month-step="1"
        aria-label="Next month"
        ${selectedValue >= currentValue ? "disabled" : ""}
      >
        ${icon("chevron")}
      </button>
    </div>
    <div
      class="month-calendar-grid"
      role="group"
      aria-label="${e(
        first.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
      )} practice days"
    >
      ${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        .map((weekday) => `<span class="month-weekday">${weekday}</span>`)
        .join("")}
      ${Array.from({ length: cellCount }, (_, index) => {
        const day = index - leading + 1;
        if (day < 1 || day > totalDays)
          return '<span class="month-day empty" aria-hidden="true"></span>';
        const dateValue = new Date(year, month, day),
          key = dayKey(dateValue),
          done = practicedDays.has(key),
          isToday = key === dayKey(new Date());
        return `<span class="month-day ${done ? "done" : ""} ${isToday ? "today" : ""}" aria-label="${e(dateValue.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }))}${done ? ", practice logged" : ""}">${day}</span>`;
      }).join("")}
    </div>
  </section>`;
}

export function train(state) {
  const stats = practiceStats(state.sessions, state.logs),
    focus = findDrill(state.drillId),
    latest = stats.real[0];
  return html`${heading(
      "READY WHEN YOU ARE",
      "Make your<br>next touch count.",
      html`<span class="heading-date">${e(date(new Date(), true))}</span>`,
    )}
    <div class="training-layout">
      <section>
        <div class="week-strip">
          <div>
            ${icon("streak")}<strong
              >${stats.streak
                ? `${stats.streak}-day practice streak`
                : "Your next practice starts here"}</strong
            >
          </div>
          <span>${stats.week.length} / ${state.preferences.goal} THIS WEEK</span>
        </div>
        ${photo(
          "piste-feature",
          html`<span class="image-badge">TODAY’S FOCUS / ${focus.minutes} MIN</span>
            <div class="image-footer">
              <h2>${focus.title}</h2>
              <button
                class="round-action"
                data-drill="${e(focus.id)}"
                aria-label="Start ${e(focus.name)} drill"
              >
                ${icon("arrow")}
              </button>
            </div>`,
        )}
        ${primary("Start training", `data-drill="${e(focus.id)}"`)}
        <div class="home-shortcuts">
          <button data-sample>${icon("play")}Explore sample review</button
          ><button data-go="record">${icon("upload")}Upload a video</button>
        </div>
      </section>
      <aside class="training-aside">
        <div class="section-heading">
          <h2>Build your foundations</h2>
          <button data-go="library">Explore ${icon("chevron")}</button>
        </div>
        ${drillRows(drills, state.preferences.saved)}
        ${state.plans.length
          ? html`<div class="daily-focus">
              <p class="eyebrow">FROM YOUR COACH</p>
              <h3>${e(state.plans.at(-1).name)}</h3>
              <p>${e(state.plans.at(-1).success_criterion)}</p>
              <button class="text-action" data-go="library">
                Open saved practice ${icon("arrow")}
              </button>
            </div>`
          : html`<div class="daily-focus">
              <p class="eyebrow">ONE SESSION. ONE FOCUS.</p>
              <h3>A controlled return.</h3>
              <p>
                Reset your guard between each rep. Bring one question to your next
                practice.
              </p>
            </div>`}
        <div class="section-heading">
          <h2>${latest ? "Pick up where you left off" : "Your practice journal"}</h2>
          <button data-go="progress">View all ${icon("chevron")}</button>
        </div>
        ${latest?.log_id ? journalRows([latest]) : sessionRows(latest ? [latest] : [])}
      </aside>
    </div>`;
}
export function library(state) {
  const filtered =
    state.libraryFilter === "saved"
      ? drills.filter((d) => state.preferences.saved.includes(d.id))
      : drills;
  return html`${heading("THE PRACTICE LIBRARY", "Build your<br>foundations.")}
    <div class="range-control library-tabs">
      <button
        data-filter="all"
        class="${state.libraryFilter === "all" ? "active" : ""}"
      >
        All drills</button
      ><button
        data-filter="saved"
        class="${state.libraryFilter === "saved" ? "active" : ""}"
      >
        Saved drills
      </button>
    </div>
    <div class="library-grid">
      ${filtered
        .map(
          (drill, i) =>
            html`<button class="drill-card" data-drill="${e(drill.id)}">
              ${photo(
                `library-photo crop-${i}`,
                `<span class="image-badge">${e(drill.level)}</span>`,
              )}
              <div>
                <p class="eyebrow">${drill.minutes} MIN / GUIDED PRACTICE</p>
                <h2>${e(drill.name)}</h2>
                <p>${e(drill.subtitle)}</p>
                <span
                  >${state.preferences.saved.includes(drill.id) ? "SAVED / " : ""}Start
                  a deliberate set ${icon("arrow")}</span
                >
              </div>
            </button>`,
        )
        .join("") ||
      '<p class="empty-note">Save a drill from its practice page to keep it here.</p>'}
    </div>
    ${state.plans.length
      ? html`<section>
          <div class="section-heading"><h2>From your coach</h2></div>
          ${state.plans
            .map(
              (plan) =>
                `<article class="side-card"><p class="eyebrow">SAVED PRACTICE</p><h2>${e(plan.name)}</h2><ol>${plan.steps.map((step) => `<li>${e(step)}</li>`).join("")}</ol><p class="helper">${e(plan.success_criterion)}</p><button class="primary-action" data-plan-practice="${e(plan.plan_id)}">Log this practice ${icon("arrow")}</button><button class="text-action" data-session="${e(plan.session_id)}">Original review ${icon("arrow")}</button></article>`,
            )
            .join("")}
        </section>`
      : ""}`;
}
export function drill(state) {
  const data = findDrill(state.drillId),
    saved = state.preferences.saved.includes(data.id);
  return html`<div class="screen-top">
      <button class="text-action" data-go="library">
        ${icon("back")}Training library</button
      ><span>GUIDED PRACTICE / FOIL</span
      ><button
        class="icon-button ${saved ? "saved" : ""}"
        data-save-drill
        aria-label="${saved ? "Remove saved drill" : "Save drill"}"
        aria-pressed="${saved}"
      >
        ${icon("flag")}
      </button>
    </div>
    <div class="drill-layout">
      ${photo(
        "drill-cover",
        html`<span class="image-badge">${e(data.level)}</span>
          <div class="image-footer"><h2>${data.title}</h2></div>`,
      )}
      <section class="drill-detail">
        <p class="eyebrow">${data.minutes} MINUTES / ${e(data.level)}</p>
        <h1>${e(data.name)}</h1>
        <p class="detail-description">
          ${e(data.subtitle)}. Keep the setup consistent and give each repetition a
          deliberate finish.
        </p>
        <div class="drill-steps">
          ${data.steps
            .map(
              ([title, body], i) =>
                html`<div>
                  <b>0${i + 1}</b>
                  <p><strong>${e(title)}</strong><span>${e(body)}</span></p>
                </div>`,
            )
            .join("")}
        </div>
        ${primary("Set up camera", 'data-go="record"')}
        <p class="helper">${e(data.criterion)}</p>
        <details class="disclosure">
          <summary>About this practice ${icon("chevron")}</summary>
          <p>${e(data.note)} Adapt the exercise with your fencing coach.</p>
        </details>
      </section>
    </div>`;
}
export function record(state) {
  const draft = state.draftClip,
    ready = capture.ready,
    recording = capture.recording;
  let preview;
  if (ready) preview = '<video id="camera-preview" autoplay muted playsinline></video>';
  else if (draft) preview = '<video id="draft-preview" controls playsinline></video>';
  else
    preview = photo(
      "camera-example",
      '<span class="image-badge">FRAMING EXAMPLE</span>',
    );
  return html`${heading("YOUR PRACTICE", "Move. Reset.<br>Repeat.")}
    <div class="record-layout">
      <section>
        <div class="capture-view">
          <div class="capture-stage">
            ${preview}${!draft
              ? '<div class="capture-corners"><i></i><i></i><i></i><i></i></div>'
              : ""}${ready
              ? html`<div class="camera-top">
                  <span class="camera-mode"
                    >${recording ? "<i></i> RECORDING" : "CAMERA PREVIEW"}</span
                  ><strong id="record-clock">${clock(capture.elapsed)}</strong>
                </div>`
              : ""}${!ready && !draft
              ? '<div class="camera-guidance"><strong>WHOLE BODY IN FRAME</strong><p>Leave room for your lunge and recovery.</p></div>'
              : ""}
          </div>
          <div class="capture-bottom">
            <span>${icon("camera")}Fixed side view</span
            ><span>${icon("target")}One fencer</span>
          </div>
        </div>
        <p class="helper">
          ${draft
            ? "Analyze sends this clip to your local FenceCoach server. Download a copy to keep it elsewhere."
            : "Camera access starts only when you choose Enable camera. Audio is not recorded."}
        </p>
      </section>
      <section class="capture-info">
        <p class="eyebrow">
          ${draft
            ? "CLIP READY"
            : recording
              ? "PRACTICE IN PROGRESS"
              : "BEFORE YOUR FIRST REP"}
        </p>
        <h2>
          ${draft
            ? "See your movement."
            : recording
              ? "Make each rep count."
              : "Ready when you are."}
        </h2>
        <p>
          ${draft
            ? "Track your movement, review the proposed recovery intervals, and save the measurements you approve."
            : recording
              ? "Keep your return deliberate. Finish the recording when your set is complete."
              : "Place your camera side-on, then check your framing."}
        </p>
        ${draft
          ? html`${videoSetup(state)}${secondary(
                "Download video",
                "data-download-draft",
              )}${secondary("Choose another clip", "data-upload-draft")}<button
                class="text-action"
                data-clear-draft
              >
                Start again ${icon("back")}
              </button>`
          : html`${!recording
              ? '<ul class="setup-checklist"><li>Whole body visible</li><li>Camera stays still</li><li>Space to move safely</li></ul>'
              : ""}${recording
              ? '<button class="record-action" data-finish-recording><span class="record-dot"></span>Finish practice</button>'
              : ready
                ? '<button class="record-action" data-start-recording><span class="record-dot"></span>Start recording</button>'
                : primary("Enable camera", "data-enable-camera")}${!recording
              ? secondary("Upload an existing clip", "data-upload-draft")
              : ""}`}
        <input class="sr-only" type="file" id="draft-file" accept="video/*" />
        <p class="subtle-note">
          ${draft
            ? "Local video storage / up to 200 MB"
            : "Analyze up to 2 minutes / 200 MB"}
        </p>
      </section>
    </div>
    ${videoHistory(state)}`;
}
export const review = athleteReview;
export function coach(state) {
  if (!state.session)
    return `${heading("SESSION COACH", "Let’s work on it.")}${emptySession("Bring a session to the conversation.")}`;
  const turns = [...state.runs].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at),
  );
  const run = turns[0] || state.run;
  const sessionReview = turns.find((turn) => turn.response_kind !== "conversation");
  const localEvidence = state.reviewResult?.technique_evaluation?.reps?.some(
    (rep) => rep.measurements?.projected_torso_tilt,
  );
  const needsClearerClip =
    state.reviewResult?.quality_gate?.coaching_allowed === false && !localEvidence;
  const overview = needsClearerClip
    ? "Ask general technique questions here. For personal feedback, upload a fixed-camera clip showing your full body and weapon hand."
    : sessionReview?.report.summary ||
      "Ask about technique, your session, or your next practice.";
  const shortOverview =
    formatCoachText(overview).length > 220
      ? formatCoachText(overview)
          .slice(0, 217)
          .replace(/\s+\S*$/, "") + "…"
      : formatCoachText(overview);
  const practiceQuestion = needsClearerClip
    ? "Suggest a general drill for practicing a fencing lunge."
    : "Suggest one drill for my next practice using the supplied evidence.";
  const hasClip = state.session.video_job_id || getClipURL();
  const footage = hasClip
    ? html`<video
          id="replay-video"
          data-session-id="${e(state.session.session_id)}"
          controls
          playsinline
          preload="metadata"
          aria-label="Practice session video"
        ></video
        >${state.session.video_job_id
          ? html`<canvas id="review-overlay" aria-hidden="true"></canvas
              ><button
                class="overlay-toggle"
                data-video-overlay
                aria-pressed="${state.videoOverlay}"
              >
                ${icon("target")}Landmarks ${state.videoOverlay ? "on" : "off"}
              </button>`
          : ""}`
    : html`<div class="no-footage">
        ${icon("camera")}
        <h2>${state.session.is_demo ? "Sample session" : "No video attached"}</h2>
        <p>
          ${state.session.is_demo
            ? "This session uses illustrative measurements. Upload your footage to see it here."
            : "Attach the video for this practice session to watch it alongside your coach."}
        </p>
        <button
          type="button"
          class="secondary-action"
          ${state.session.is_demo ? 'data-go="record"' : "data-attach-video"}
        >
          ${state.session.is_demo ? "Upload a clip" : "Attach session video"}
          ${icon("upload")}
        </button>
      </div>`;
  const conversation = turns
    .map(
      (turn) =>
        html`<article class="coach-turn">
          <div class="chat-message user">
            <span class="eyebrow">YOU</span>
            <p>${e(turn.question)}</p>
          </div>
          <div class="chat-message coach">
            <span class="coach-emblem">${icon("spark")}</span>
            <div>${reportContent(turn)}</div>
          </div>
        </article>`,
    )
    .join("");
  const pending = state.generating
    ? html`<article class="coach-turn">
        <div class="chat-message user">
          <span class="eyebrow">YOU</span>
          <p>${e(state.coachingJob?.question || state.question)}</p>
        </div>
        <div class="chat-message coach" ${state.partialReply ? "" : "hidden"}>
          <span class="coach-emblem">${icon("spark")}</span>
          <p id="coaching-partial" class="conversation-answer">
            ${e(state.partialReply || "")}
          </p>
        </div>
        <div class="generating" role="status">
          <span class="spinner"></span
          ><span id="coaching-stage">Coach is replying…</span
          ><button class="text-action" type="button" data-stop-coaching>Stop</button>
        </div>
      </article>`
    : "";
  return html`${heading("SESSION COACH", "Let’s work on it.")}${sessionPicker(state)}
    <div class="coach-workspace">
      <section class="coach-replay" aria-label="Session video">
        <div class="replay-view">${footage}</div>
        ${hasClip
          ? frameStepControls(
              "replay-frame-controls",
              state.reviewResult?.preview?.fps_hint || 30,
            )
          : ""}${state.session.is_demo && state.reviewResult?.source_credit
          ? html`<p class="video-credit">
              ${e(state.reviewResult.source_credit)} ·
              <a
                href="https://ocw.mit.edu/courses/pe-740-fencing-spring-2007/pages/video/"
                target="_blank"
                rel="noreferrer"
                >Video source</a
              >
            </p>`
          : ""}<input
          class="sr-only"
          id="session-video-file"
          type="file"
          accept="video/*"
        />
      </section>
      <div class="coach-conversation-column">
        <section class="coach-chat" aria-labelledby="coach-chat-title">
          <h2 id="coach-chat-title">Talk with your coach</h2>
          <div class="coach-composer">
            <form id="coach-form">
              <label for="question" class="sr-only">Message your coach</label
              ><textarea
                id="question"
                name="question"
                rows="2"
                minlength="1"
                maxlength="1500"
                required
                placeholder="Ask a question or follow up…"
              >
${e(state.question)}</textarea
              ><button
                class="send-question"
                type="submit"
                aria-label="Send message to coach"
                ${state.generating ? "disabled" : ""}
              >
                ${icon("arrow")}
              </button>
            </form>

            ${state.coachError
              ? html`<div class="coach-status coach-error" role="alert">
                  <strong>Your message wasn’t answered.</strong>
                  <p>${e(state.coachError)}</p>
                </div>`
              : ""}
          </div>
          <div class="coach-conversation">
            ${pending}${turns.length
              ? conversation
              : !state.generating
                ? html`<div class="coach-welcome">
                    <span class="coach-emblem">${icon("spark")}</span>
                    <p>
                      Start with a question. Your replies will appear here, newest
                      first.
                    </p>
                  </div>`
                : ""}
          </div>
        </section>
      </div>
    </div>`;
}
export function progress(state) {
  const stats = practiceStats(state.sessions, state.logs),
    now = new Date(),
    currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
    selectedMonth = /^\d{4}-\d{2}$/.test(state.progressMonth || "")
      ? state.progressMonth
      : currentMonth,
    [selectedYear, selectedMonthNumber] = selectedMonth.split("-").map(Number),
    monthIndex = selectedMonthNumber - 1,
    monthStart = new Date(selectedYear, monthIndex, 1),
    rangeStart = state.progressRange === "month" ? monthStart : periodStart("week"),
    rangeEnd = new Date(
      Math.min(
        state.progressRange === "month"
          ? new Date(selectedYear, monthIndex + 1, 1).getTime()
          : Infinity,
        now.getTime() + 1,
      ),
    ),
    showAllSessions = Boolean(state.progressShowAllSessions),
    selectedMonthName = monthStart.toLocaleDateString(undefined, { month: "long" });
  const period = stats.real.filter((session) => {
    const createdAt = new Date(session.created_at);
    return createdAt >= rangeStart && createdAt < rangeEnd;
  });
  const visibleSessions = showAllSessions ? period : period.slice(0, 3);
  const days = new Set(period.map((s) => dayKey(s.created_at))),
    weekStart = periodStart("week");
  const completedDays = days;
  const allGroups = new Map();
  for (const session of period)
    for (const metrics of groups(session.metrics)) {
      const key = JSON.stringify([metrics[0].name, metrics[0].unit]);
      if (!allGroups.has(key))
        allGroups.set(key, {
          name: metrics[0].name,
          unit: metrics[0].unit,
          points: [],
        });
      allGroups.get(key).points.push({
        value: mean(metrics),
        created_at: session.created_at,
        capture_profile: session.capture_profile || {},
      });
    }
  const selected = allGroups.get(state.trendKey) || allGroups.values().next().value;
  const comparable =
    selected?.points.length >= 2 &&
    selected.points.every((point) =>
      comparableSetup(selected.points[0].capture_profile, point.capture_profile),
    );
  const weekCalendar = Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(weekStart);
    dt.setDate(dt.getDate() + i);
    return dt;
  });
  return html`${heading(
      "PROGRESS",
      "Your progress.",
      '<button class="icon-button" data-go="settings" aria-label="Change weekly goal">' +
        icon("flag") +
        "</button>",
    )}
    <div class="range-control progress-tabs">
      <button
        data-range="week"
        class="${state.progressRange === "week" ? "active" : ""}"
      >
        This week</button
      ><button
        data-range="month"
        class="${state.progressRange === "month" ? "active" : ""}"
      >
        Month
      </button>
    </div>
    <div class="progress-layout">
      <section>
        <div class="progress-hero">
          <div>
            <span>PRACTICE SESSIONS</span><strong>${period.length}</strong>
            <p>
              ${period.reduce((total, s) => total + (s.duration_minutes || 0), 0)}
              minutes logged ·
              ${state.progressRange === "week"
                ? `Weekly goal: ${state.preferences.goal} sessions`
                : `${selectedMonthName} ${selectedYear} · ${days.size} practice days`}
            </p>
          </div>
          ${state.progressRange === "week"
            ? html`<div
                class="goal-ring ${stats.week.length >= state.preferences.goal
                  ? "met"
                  : ""}"
              >
                <span
                  >${stats.week.length >= state.preferences.goal
                    ? icon("check")
                    : `${stats.week.length}/${state.preferences.goal}`}</span
                ><small
                  >${stats.week.length >= state.preferences.goal
                    ? "WEEKLY GOAL MET"
                    : "THIS WEEK"}</small
                >
              </div>`
            : html`<div class="goal-ring month-goal-ring">
                <span>${days.size}</span><small>PRACTICE DAYS</small>
              </div>`}
        </div>
        ${state.progressRange === "week"
          ? html`<div class="week-calendar">
              ${weekCalendar
                .map(
                  (dt) =>
                    html`<div>
                      <span
                        >${e(
                          dt.toLocaleDateString(undefined, { weekday: "narrow" }),
                        )}</span
                      ><b class="${completedDays.has(dayKey(dt)) ? "done" : ""}"
                        >${completedDays.has(dayKey(dt))
                          ? icon("check")
                          : dt.getDate()}</b
                      >
                    </div>`,
                )
                .join("")}
            </div>`
          : monthCalendar(
              selectedYear,
              monthIndex,
              completedDays,
              currentMonth,
              selectedMonth,
            )}
        
      </section>
      <aside class="progress-history">
      <div class="section-heading">
          <h2>Movement trends</h2>
        </div>
        <div class="progress-chart">
          ${selected
            ? html`<label class="field"
                  ><span>Choose a measurement</span
                  ><select id="trend-picker">
                    ${[...allGroups.entries()]
                      .map(
                        ([key, item]) =>
                          `<option value="${e(key)}" ${item === selected ? "selected" : ""}>${e(label(item.name))} · ${e(item.unit)}</option>`,
                      )
                      .join("")}
                  </select></label
                >${comparable
                  ? trendChart([...selected.points].reverse(), selected.unit)
                  : '<p class="empty-note">Log another practice with the same setup to compare this measurement.</p>'}`
            : '<p class="empty-note">Save a video review or log a practice to start tracking your sessions.</p>'}
        </div>
        <div class="progress-history-heading">
          <div>
            <h2>
              ${state.progressRange === "week"
                ? "Sessions this week"
                : `Sessions in ${selectedMonthName} ${selectedYear}`}
            </h2>
            <span>${period.length}</span>
          </div>
          <button
            class="primary-action progress-log-action"
            data-log-new
            aria-expanded="${Boolean(state.showLogForm || state.editingLog)}"
            aria-controls="training-log-form"
          >
            ${state.showLogForm || state.editingLog ? "Close form" : "Log a practice"}
            ${icon(state.showLogForm || state.editingLog ? "close" : "arrow")}
          </button>
        </div>
        ${logForm(state)}
        ${activityRows(
          visibleSessions,
          "all-session-history",
          state.progressRange === "week"
            ? "No sessions logged this week."
            : `No sessions logged in ${selectedMonthName} ${selectedYear}.`,
        )}
        ${period.length > 3
          ? html`<button
              class="view-all-sessions"
              data-toggle-sessions
              aria-expanded="${showAllSessions}"
              aria-controls="all-session-history"
            >
              ${showAllSessions
                ? "Show recent sessions"
                : `View all ${period.length} sessions`}
              ${icon("chevron")}
            </button>`
          : ""}
      </aside>
    </div>`;
}
export function settings(state) {
  return html`${heading("YOUR TRAINING SPACE", "Make it yours.")}
    <div class="settings-layout">
      <section class="side-card">
        <form id="settings-form">
          <h2>Practice preferences</h2>
          <label class="field"
            ><span>Weekly practice goal</span
            ><input
              name="goal"
              type="number"
              min="1"
              max="14"
              value="${state.preferences.goal}"
              required /></label
          ><label class="field"
            ><span>Level for new sessions</span
            ><select name="skill">
              <option
                value="beginner"
                ${state.preferences.skill === "beginner" ? "selected" : ""}
              >
                Beginner
              </option>
              <option
                value="intermediate"
                ${state.preferences.skill === "intermediate" ? "selected" : ""}
              >
                Intermediate
              </option>
            </select></label
          >
          <p class="helper">
            Saved on this device. Existing sessions keep their original skill level.
          </p>
          ${primary("Save preferences", 'type="submit"')}
        </form>
      </section>
      <section>
        <div class="daily-focus">
          <p class="eyebrow">YOUR SESSION COACH</p>
          <h3>
            ${state.config.live_configured
              ? "Live AI is configured."
              : "Start with a demo review."}
          </h3>
          <p>
            ${state.config.live_configured
              ? "Choose Gemini AI, Local AI or AWS AI in the coach. Local readiness confirms the selected model is downloaded; cloud access still depends on credentials."
              : "Demo mode runs the coaching workflow over your measurements without making a paid AI call."}
          </p>
          <details class="disclosure">
            <summary>Set up live coaching ${icon("chevron")}</summary>
            <p>
              Gemini coaching uses your Google API key saved on this server. Local
              coaching uses Ollama; AWS coaching uses your configured Bedrock model.
              Messages and relevant training context go to the selected cloud provider.
              Credentials stay on the server.
            </p>
            ${state.config.model_id
              ? html`<p>Model: ${e(state.config.model_id)}</p>`
              : ""}
            <p>Provider charges apply. See the repository README for setup.</p>
          </details>
        </div>
        <div class="section-heading"><h2>Keep your practice</h2></div>
        <p class="helper">
          Sessions, reports and analyzed clips are stored by the local server. Drafts,
          unprocessed attached clips and preferences stay in this browser. Export your
          work to keep a copy. Analysis supports short side-view practice clips; account
          sync is not available yet.
        </p>
        <a class="text-action" href="/static/prototypes-compare.html"
          >See the original design study ${icon("arrow")}</a
        >
      </section>
    </div>`;
}
export const screens = {
  analysis,
  train,
  library,
  drill,
  record,
  review,
  coach,
  progress,
  settings,
};

function comparableSetup(a, b) {
  const fields = [
    "camera_setup_id",
    "weapon",
    "weapon_arm",
    "front_leg",
    "facing",
    "camera_motion",
    "scene_type",
  ];
  return (
    fields.every((key) => a[key] && a[key] !== "unknown" && a[key] === b[key]) &&
    a.camera_motion === "fixed" &&
    a.scene_type === "solo" &&
    JSON.stringify(a.inference_crop || null) ===
      JSON.stringify(b.inference_crop || null)
  );
}

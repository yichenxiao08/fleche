const $ = (id) => document.getElementById(id);
const jobId = location.pathname.split('/').filter(Boolean).at(-1);
const endpoint = `/api/videos/${encodeURIComponent(jobId)}/coach-feedback`;
const storageKey = `fencecoach.coach-feedback.${jobId}`;
const repFields = ['rating','done_well','main_issue','evidence_description','cue','improvement','intentional'];
const commonFields = ['reviewer','reviewer_role','weapon','intended_drill','target_height'];
let context, draft, active = 0, dirty = false, saving = false, timer, generation = 0, presentedTime = 0, hasPresented = false, conflict = false;
const video = $('video');
document.querySelector('.workspace').inert = true;
$('mark-frame').disabled = true;
const clock = (ms) => { const n = Math.max(0, Math.round(ms)); return `${String(Math.floor(n/60000)).padStart(2,'0')}:${String(Math.floor(n/1000)%60).padStart(2,'0')}.${String(n%1000).padStart(3,'0')}`; };
function fail(error) { $('error').hidden = false; $('error').textContent = error.message || String(error); }
async function api(method = 'GET', payload) {
  const response = await fetch(endpoint, {method, headers: payload ? {'Content-Type':'application/json'} : {}, body: payload ? JSON.stringify(payload) : undefined});
  const body = await response.json();
  if (!response.ok) { const err = new Error(typeof body.detail === 'string' ? body.detail : 'Could not save this review. Check the fields and try again.'); err.status = response.status; throw err; }
  return body;
}
function localBackup() { try { localStorage.setItem(storageKey, JSON.stringify({draft,dirty})); } catch { $('save-status').textContent = 'Browser backup unavailable; use Save draft or Export feedback.'; } }
function readForm() {
  if (!draft) return;
  for (const field of repFields) draft.reps[active][field] = $(field).value;
  for (const field of commonFields) draft[field] = $(field).value;
  const offset = Number($('offset').value);
  if (Number.isFinite(offset) && offset >= 0) draft.source_offset_ms = Math.round(offset * 1000);
}
function changed() {
  readForm(); draft.status = 'draft'; dirty = true; generation++; localBackup();
  $('save-status').textContent = conflict ? 'Conflicting server change: export your draft before reloading.' : 'Unsaved changes · saving shortly…';
  clearTimeout(timer); if (!conflict) timer = setTimeout(() => save('draft'), 800);
  nav(); updateClock();
}
async function save(status = 'draft') {
  clearTimeout(timer);
  if (saving || conflict) return;
  readForm(); const currentGeneration = generation;
  const payload = structuredClone(draft); payload.status = status;
  saving = true; $('save').disabled = true; $('submit').disabled = true; $('save-status').textContent = 'Saving…';
  try {
    const saved = await api('PUT', payload);
    draft.revision = saved.revision; draft.saved_at = saved.saved_at; draft.attribution = saved.attribution; draft.integration = saved.integration;
    if (currentGeneration === generation) { dirty = false; draft.status = saved.status; }
    localBackup(); $('error').hidden = true;
    $('save-status').textContent = dirty ? 'More changes waiting to save…' : saved.status === 'submitted' ? `Submitted · connected to coach · ${saved.integration?.remeasured_metrics || 0} measurements recalculated. Technique examples saved; classifier weights unchanged.` : 'Saved to server · refresh-safe';
  } catch (error) {
    conflict = error.status === 409; dirty = true; localBackup(); fail(error);
    $('save-status').textContent = `${error.message} · Browser draft retained.`;
    if (error.status === 422) {
      const missingRep = error.message.match(/rep (\d+)/i);
      if (missingRep && draft.reps[Number(missingRep[1])-1]) { active = Number(missingRep[1])-1; renderRep(); }
      if (!draft.reviewer.trim() || !draft.intended_drill.trim()) document.querySelector('.player-pane details').open = true;
    }
  } finally {
    saving = false; $('save').disabled = conflict; $('submit').disabled = conflict;
    if (dirty && !conflict && currentGeneration !== generation) timer = setTimeout(() => save('draft'), 500);
  }
}
function nav() {
  $('rep-nav').replaceChildren();
  draft.reps.forEach((rep, index) => {
    const button = document.createElement('button'); button.type = 'button';
    button.textContent = `Rep ${index+1}${rep.rating ? ' ✓' : ''}`; button.setAttribute('aria-current', String(index === active));
    button.addEventListener('click', () => { readForm(); active = index; renderRep(); seek((rep.action_start_ms ?? context.windows[index].onset_ms ?? context.windows[index].start_ms)/1000); });
    $('rep-nav').append(button);
  });
  $('progress').textContent = `${draft.reps.filter(r => r.rating).length} / ${draft.reps.length} assessed`;
}
function renderRep() {
  const rep = draft.reps[active]; $('rep-heading').textContent = `Rep ${active+1}`;
  for (const field of repFields) $(field).value = rep[field] || (field === 'intentional' ? 'unknown' : '');
  $('evidence-time').textContent = rep.evidence_ms == null ? 'No frame marked' : `Video ${clock(rep.evidence_ms)} · Original ${clock(rep.evidence_ms + draft.source_offset_ms)}`;
  $('jump-evidence').disabled = rep.evidence_ms == null;
  $('phase-jumps').replaceChildren();
  const w = context.windows[active];
  for (const [label, field, original] of [['Action start','action_start_ms',w.onset_ms ?? w.start_ms],[context.intervals_reviewed ? 'Reviewed lunge' : 'Suggested lunge','lunge_ms',w.start_ms],['Return to guard','guard_ms',w.end_ms]]) {
    const time = rep[field] ?? original;
    const row = document.createElement('div'); row.className = 'phase-edit-row';
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.addEventListener('click', () => seek(time/1000));
    const stamp = document.createElement('span'); stamp.textContent = clock(time); stamp.className = 'phase-time';
    const set = document.createElement('button'); set.type = 'button'; set.textContent = 'Set to current frame'; set.setAttribute('aria-label', `Set ${label.toLowerCase()} to current frame`); set.dataset.phaseSet = ''; set.disabled = video.readyState < 2 || video.seeking;
    set.addEventListener('click', () => { video.pause(); rep[field] = Math.round(visibleTime()*1000); changed(); renderRep(); });
    const reset = document.createElement('button'); reset.type = 'button'; reset.textContent = 'Reset'; reset.disabled = rep[field] == null; reset.setAttribute('aria-label', `Reset ${label.toLowerCase()} time`);
    reset.addEventListener('click', () => { rep[field] = null; changed(); renderRep(); });
    row.append(b, stamp, set, reset); $('phase-jumps').append(row);
  }
  const note = document.createElement('p'); note.className = 'timing-note'; note.textContent = 'Pause on the correct frame, then set its bookmark. Drafts autosave. Submitting applies corrected timings to session measurements and checks their order.'; $('phase-jumps').append(note);
  const evaluated = context.technique_evaluation?.reps?.[active];
  if (evaluated) {
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = `Automatic checks · ${evaluated.findings.length} review flags`; details.append(summary);
    const intro = document.createElement('p'); intro.className = 'timing-note'; intro.textContent = 'Computed from tracked video frames using the basic-lunge rubric. Review flags are provisional; absence of flags does not establish correct technique.'; details.append(intro);
    for (const finding of evaluated.findings) {
      const p = document.createElement('p'); p.className = 'timing-note'; p.textContent = `${finding.observation} ${finding.cue}`;
      const jump = document.createElement('button'); jump.type = 'button'; jump.textContent = `View ${clock(finding.evidence_ms)}`; jump.addEventListener('click', () => seek(finding.evidence_ms/1000)); details.append(p, jump);
    }
    for (const [key, measurement] of Object.entries(evaluated.measurements)) {
      const p = document.createElement('p'); p.className = 'timing-note'; p.textContent = `${key.replaceAll('_',' ')}: ${measurement.value} ${measurement.unit}${measurement.note ? ` · ${measurement.note}` : ''}`; details.append(p);
    }
    for (const gap of evaluated.unavailable) { const p = document.createElement('p'); p.className = 'timing-note'; p.textContent = gap; details.append(p); }
    $('phase-jumps').append(details);
  }
  nav();
}
function seek(time) {
  if (video.readyState < 1) return;
  video.pause(); hasPresented = false;
  video.currentTime = Math.max(0, Math.min(time, Math.max(0, video.duration-0.001) || context.duration_ms/1000)); updateClock();
}
function visibleTime() { return hasPresented ? presentedTime : video.currentTime; }
function updateClock() {
  const time = visibleTime(); $('clock').textContent = clock(time*1000);
  $('original-clock').textContent = `Original ${clock(time*1000 + (draft?.source_offset_ms || 0))}`;
  if (document.activeElement !== $('seek-time')) $('seek-time').value = time.toFixed(3);
}
function step(direction) {
  const fps = context.fps || 30;
  const frame = Math.round(visibleTime()*fps) + direction;
  seek(Math.max(0, frame/fps + 0.1/fps));
}
if ('requestVideoFrameCallback' in video) {
  const onFrame = (_, metadata) => { presentedTime = metadata.mediaTime; hasPresented = true; updateClock(); video.requestVideoFrameCallback(onFrame); };
  video.requestVideoFrameCallback(onFrame);
}
video.addEventListener('timeupdate', updateClock); video.addEventListener('seeked', updateClock);
function frameButtons(disabled) { $('mark-frame').disabled = disabled; document.querySelectorAll('[data-phase-set]').forEach(b => { b.disabled = disabled; }); }
video.addEventListener('seeking', () => frameButtons(true));
video.addEventListener('seeked', () => frameButtons(false));
video.addEventListener('loadeddata', () => frameButtons(false));
$('prev-frame').addEventListener('click', () => step(-1)); $('next-frame').addEventListener('click', () => step(1));
$('seek').addEventListener('click', () => { const time = Number($('seek-time').value); if (Number.isFinite(time)) seek(time); });
$('speed').addEventListener('change', () => { video.playbackRate = Number($('speed').value); });
$('mark-frame').addEventListener('click', () => { video.pause(); draft.reps[active].evidence_ms = Math.round(visibleTime()*1000); changed(); renderRep(); });
$('jump-evidence').addEventListener('click', () => seek(draft.reps[active].evidence_ms/1000));
$('feedback-form').addEventListener('submit', (event) => event.preventDefault());
for (const field of [...repFields,...commonFields,'offset']) $(field).addEventListener('input', changed);
$('save').addEventListener('click', () => save('draft')); $('submit').addEventListener('click', () => save('submitted'));
$('export').addEventListener('click', () => {
  readForm(); const blob = new Blob([JSON.stringify({job_id:jobId,clip_title:context.title,...draft},null,2)], {type:'application/json'});
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = `fencecoach-feedback-${jobId.slice(0,8)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener('beforeunload', (event) => { if (dirty) { localBackup(); event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', (event) => {
  if (event.target.closest('input,textarea,select,button')) return;
  if (event.key === ',' || event.key === '.') { event.preventDefault(); step(event.key === ',' ? -1 : 1); }
});
try {
  context = await api(); draft = context.feedback;
  try { const backup = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (backup?.dirty && backup.draft?.revision === draft.revision) { draft = backup.draft; dirty = true; }
    else if (backup?.dirty && backup.draft) { conflict = true; dirty = true; fail(new Error('This browser has unsaved edits from an older review version. Export them before reloading.')); draft = backup.draft; }
  } catch {}
  if (!draft.reps.length) throw new Error('No rep intervals are available. Save reviewed intervals in the video analysis first.');
  const offset = Number(new URLSearchParams(location.search).get('offset_ms'));
  if (!draft.revision && Number.isFinite(offset) && offset >= 0) draft.source_offset_ms = offset;
  $('clip-title').textContent = context.title;
  for (const field of commonFields) $(field).value = draft[field];
  $('offset').value = draft.source_offset_ms/1000;
  $('precision').textContent = `Step through actual preview frames (~${Math.round(context.fps)} fps). , and . also step frames. Millisecond timestamps identify displayed frames; pose measurements are sampled roughly every ${Math.round(context.pose_sample_interval_ms || 83)} ms.`;
  video.src = `/api/videos/${encodeURIComponent(jobId)}/preview`;
  $('save-status').textContent = conflict ? 'Conflicting review version · export your draft before reloading' : dirty ? 'Restored browser draft · save to server' : draft.saved_at ? 'Saved review loaded' : 'Ready · changes autosave';
  $('save').disabled = conflict; $('submit').disabled = conflict;
  renderRep(); document.querySelector('.workspace').inert = false;
  if (dirty && !conflict) timer = setTimeout(() => save('draft'), 500);
} catch (error) { fail(error); $('save-status').textContent = 'Review could not load'; $('feedback-form').inert = true; }

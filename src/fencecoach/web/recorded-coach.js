// A read-only recording player. No network requests or live coaching input.
(() => {
  const recordings = JSON.parse(document.getElementById("recordings").textContent);
  const select = document.getElementById("recording");
  const conversation = document.getElementById("conversation");
  const play = document.getElementById("play");
  const next = document.getElementById("next");
  const reset = document.getElementById("reset");
  let current = null, shown = 0, timer = null;

  function pause() {
    clearInterval(timer);
    timer = null;
    play.textContent = "Play recording";
  }
  function update() {
    const complete = shown === current.turns.length;
    next.disabled = complete;
    play.disabled = complete;
    document.getElementById("progress").textContent = `${shown} of ${current.turns.length} turns`;
    if (complete) pause();
  }
  function reveal() {
    if (!shown) conversation.replaceChildren();
    if (shown >= current.turns.length) return;
    const turn = current.turns[shown++];
    const section = document.createElement("section");
    section.className = "turn";
    section.setAttribute("aria-label", `Recorded turn ${shown}`);
    for (const [role, text] of [["athlete", turn.question], ["coach", turn.answer]]) {
      const paragraph = document.createElement("p");
      paragraph.className = `message ${role}`;
      const label = document.createElement("small");
      label.textContent = role === "athlete" ? "Athlete · recorded" : `Coach · recorded ${turn.provider_label} reply · originally ${(turn.latency_ms / 1000).toFixed(2)}s`;
      paragraph.append(label, document.createTextNode(text));
      section.append(paragraph);
    }
    conversation.append(section);
    update();
  }
  function load() {
    pause();
    current = recordings[select.selectedIndex];
    shown = 0;
    document.getElementById("title").textContent = current.title;
    document.getElementById("details").textContent = current.description;
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Play this saved conversation, or reveal one turn at a time.";
    conversation.replaceChildren(empty);
    update();
  }
  for (const recording of recordings) {
    const option = document.createElement("option");
    option.textContent = recording.title;
    select.append(option);
  }
  select.addEventListener("change", load);
  reset.addEventListener("click", load);
  next.addEventListener("click", () => { pause(); reveal(); });
  play.addEventListener("click", () => {
    if (timer) { pause(); return; }
    reveal();
    if (shown < current.turns.length) {
      play.textContent = "Pause recording";
      timer = setInterval(reveal, 1300);
    }
  });
  load();
})();

"""Publish manually selected recordings verbatim, embedded for API-free playback."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = ROOT / "evals/conversational_kb/model_review/recorded_demo_selection.json"
    selections = json.loads(manifest.read_text(encoding="utf-8"))
    recordings = []
    for selection in selections:
        row = json.loads((ROOT / selection["source"]).read_text(encoding="utf-8"))
        turns = [t for t in row["turns"] if t["turn"] in selection["turns"]]
        if len(turns) != len(selection["turns"]):
            raise ValueError("Recording selection includes an unrun turn.")
        recordings.append(
            {
                "title": selection["title"],
                "description": selection["description"],
                "turns": [
                    {
                        "question": t["question"],
                        "answer": t["answer"],
                        "latency_ms": t["latency_ms"],
                        "provider_label": t.get("model_id") or t["run"]["model_id"],
                    }
                    for t in turns
                ],
            }
        )
    payload = json.dumps(recordings, ensure_ascii=False).replace("<", "\\u003c")
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FenceCoach · Recorded session</title><link rel="stylesheet" href="recorded-coach.css">
<script src="recorded-coach.js" defer></script></head><body>
<header><a class="brand" href="/">FENCECOACH</a><span class="recorded">Recorded session</span></header>
<main><h1>A conversation from the piste.</h1>
<p class="intro">These are saved coaching conversations, replayed exactly as recorded. Nothing here is live. Playing a recording makes no API calls and uses no model quota.</p>
<div class="layout"><aside><label for="recording">Choose a recording</label><select id="recording"></select><p id="details" class="details"></p></aside>
<section class="panel" aria-label="Recorded conversation"><div class="panel-heading"><h2 id="title"></h2><span class="recorded">Recorded session</span></div>
<div id="conversation" aria-live="polite"></div><div class="controls"><button class="primary" id="play">Play recording</button><button id="next">Next turn</button><button id="reset">Reset</button><span id="progress" role="status"></span></div></section></div>
<p class="footnote">Replies and original response times come from saved runs. Playback timing is shortened for this demonstration. This page cannot answer new questions.</p></main>
<script id="recordings" type="application/json">__RECORDINGS__</script></body></html>
""".replace("__RECORDINGS__", payload)
    (ROOT / "src/fencecoach/web/recorded-coach.html").write_text(page, encoding="utf-8")
    print(f"Saved {len(recordings)} original recordings. No API calls.")


if __name__ == "__main__":
    main()

"""Record an honest 80-second product rehearsal in an isolated database."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from fencecoach.video_preview import build_preview


def caption(page, title, detail):
    page.evaluate(
        """([title, detail]) => {
      document.getElementById('demo-caption')?.remove();
      const box = document.createElement('div'); box.id = 'demo-caption';
      box.style = 'position:fixed;bottom:18px;left:18px;right:18px;z-index:99999;background:#911b27;color:white;padding:18px 24px;border-radius:12px;font:17px sans-serif;box-shadow:0 4px 28px #0004;pointer-events:none';
      const h = document.createElement('strong'); h.textContent = title;
      const p = document.createElement('div'); p.textContent = detail;
      p.style = 'margin-top:7px;font-size:14px'; box.append(h,p); document.body.append(box);
    }""",
        [title, detail],
    )


def main():
    project = Path(__file__).resolve().parents[1]
    docs = project / "docs"
    docs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "FENCECOACH_DB_PATH": str(temp / "app.sqlite3"),
            "FENCECOACH_DATABASE_URL": "",
            "FENCECOACH_VIDEO_DIR": str(temp / "videos"),
            "FENCECOACH_SEED_EXAMPLES": "true",
            "FENCECOACH_AUTOMATIC_TRAINING": "false",
            "FENCECOACH_PHOENIX_ENDPOINT": "",
            "FENCECOACH_VIDEO_WORKER": "false",
            "FENCECOACH_COACHING_WORKER": "true",
        }
        with (temp / "server.log").open("w") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "fencecoach.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=env,
                cwd=project,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    try:
                        if httpx.get(base + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        record_video_dir=str(temp / "recording"),
                        record_video_size={"width": 1280, "height": 800},
                    )
                    page = context.new_page()
                    page.goto(base)
                    caption(
                        page,
                        "FenceCoach / grounded coaching workflow",
                        "Fixed-camera solo drills. Measurement tools, retrieval, conversational memory, and observable runs.",
                    )
                    page.wait_for_timeout(9000)
                    page.locator('[data-go="record"]:visible').first.click()
                    expect(page.locator("[data-video-job]")).to_have_count(3)
                    page.locator("[data-video-job]").filter(has_text="Jump lunge").click()
                    expect(page.locator("#analysis-video")).to_be_visible()
                    page.locator("#analysis-video").evaluate("v => { v.muted=true; v.play(); }")
                    caption(
                        page,
                        "Automatic QA before coaching",
                        "Real MIT archival footage, real pose extraction. Low resolution fails QA; the app blocks personalized advice.",
                    )
                    page.wait_for_timeout(9000)
                    page.locator("details").filter(has_text="Overlay contact sheet").locator(
                        "summary"
                    ).click()
                    page.locator('img[alt^="Twelve"]').scroll_into_view_if_needed()
                    caption(
                        page,
                        "Inspect 12 sampled overlays in one view",
                        "Proposed reps remain suggestions. Visibility confidence does not prove correct athlete tracking or technique.",
                    )
                    page.wait_for_timeout(11000)
                    page.locator('[data-go="record"]:visible').first.click()
                    page.locator("[data-sample]").click()
                    expect(page.locator('.review-actions [data-go="coach"]')).to_be_visible()
                    page.locator('.review-actions [data-go="coach"]').click()
                    page.locator("#mode").select_option("demo")
                    page.locator("#question").fill("Review the measured recovery intervals")
                    page.locator('#coach-form button[type="submit"]').click()
                    expect(page.locator(".chat-message.coach").last).to_be_visible(timeout=20000)
                    caption(
                        page,
                        "Rehearse the evidence workflow without an API key",
                        "This section uses synthetic measurements and the deterministic sample formatter; it is not an LLM quality demonstration.",
                    )
                    page.wait_for_timeout(10000)
                    page.locator('[data-go="progress"]:visible').first.click()
                    caption(
                        page,
                        "Persistent sessions, coaching turns, and practice logs",
                        "Progress comparisons require matching named camera setups. Synthetic examples do not count toward practice goals.",
                    )
                    page.wait_for_timeout(9000)
                    page.goto("http://127.0.0.1:6006")
                    page.wait_for_timeout(2500)
                    links = page.locator('a[href*="/projects/"]')
                    if links.count():
                        links.first.click()
                        page.wait_for_timeout(1500)
                    page.screenshot(path=str(docs / "phoenix-traces.png"), full_page=True)
                    caption(
                        page,
                        "Actual Phoenix traces from live local-model runs",
                        "Tool spans, model IDs, available token usage, latency, and API fee estimates. Question and video content are omitted.",
                    )
                    page.wait_for_timeout(10000)
                    smoke = json.loads((project / "data/evals/mcp-smoke.json").read_text())
                    page.set_content(
                        '<html><body style="background:#faf9f6;color:#201d1b;padding:65px;font-family:sans-serif"><small style="color:#a22533">FENCECOACH / MCP PROTOCOL CHECK</small><h1 style="font-size:48px">Five tools. One evidence source.</h1>'
                        + "".join(
                            f'<p style="padding:12px;border-bottom:1px solid #ddd;font-size:22px">{name}</p>'
                            for name in smoke["tools"]
                        )
                        + "<p>Actual recorded result: official SDK stdio client passed discovery, resource reads, five calls, and missing-session handling.</p><p>Claude Desktop / Code integration has not been exercised.</p></body></html>"
                    )
                    caption(
                        page,
                        "Read-only MCP tools for an external assistant",
                        "Local protocol check passed. Expert coaching validation, clean supported clips, and hosted vision benchmarks remain pending.",
                    )
                    page.wait_for_timeout(10000)
                    recording = page.video.path()
                    context.close()
                    browser.close()
                    (temp / "encoded").mkdir()
                    shutil.copy2(recording, project / "tmp/demo-recording.webm")
                    preview = build_preview(Path(recording), temp / "encoded")
                    shutil.copy2(temp / "encoded/preview.mp4", docs / "demo.mp4")
                    shutil.copy2(temp / "encoded/poster.jpg", docs / "demo-poster.jpg")
                    report = {
                        "duration_ms": preview["duration_ms"],
                        "path": "docs/demo.mp4",
                        "synthetic_coach_section": True,
                        "live_trace_dashboard": True,
                        "claude_client": "not exercised",
                    }
                    (project / "data/evals/demo.json").write_text(json.dumps(report, indent=2))
                    print(json.dumps(report))
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    main()

"""Isolated real browser smoke. Synthetic analysis fixtures are clearly disclosed."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def make_clip(path, color):
    import av
    import numpy as np

    with av.open(str(path), "w") as container:
        stream = container.add_stream("libx264", rate=10)
        stream.width, stream.height, stream.pix_fmt = 1280, 720, "yuv420p"
        for i in range(30):
            pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
            pixels[:, :, color] = 40 + i
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def main():
    project = Path(__file__).resolve().parents[1]
    output = project / "data/evals/browser"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {
            **os.environ,
            "FENCECOACH_DB_PATH": str(temp / "app.sqlite3"),
            "FENCECOACH_DATABASE_URL": "",
            "FENCECOACH_VIDEO_DIR": str(temp / "videos"),
            "FENCECOACH_AUTOMATIC_TRAINING": "false",
            "FENCECOACH_KNOWLEDGE_DIR": str(project / "knowledge"),
            "FENCECOACH_PHOENIX_ENDPOINT": "",
        }
        log = (output / "server.log").open("w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, str(project / "tests/browser_server.py"), str(port)],
            cwd=project,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    if httpx.get(base + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if server.poll() is not None:
                    raise RuntimeError("Fixture server stopped; read server.log")
                time.sleep(0.1)
            else:
                raise RuntimeError("Fixture server did not become ready")
            for name, color in [("one", 0), ("two", 1)]:
                make_clip(temp / f"{name}.mp4", color)
            errors = []
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
                )
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}, permissions=["camera"]
                )
                page = context.new_page()
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(base)
                page.locator('[data-go="record"]').first.click()
                page.locator("[data-enable-camera]").click()
                expect(page.locator("[data-start-recording]")).to_be_visible()
                expect(page.locator(".setup-checklist li")).to_have_text(
                    [
                        "Whole body visible",
                        "Camera stays still",
                        "Space to move safely",
                    ]
                )
                page.locator("[data-start-recording]").click()
                time.sleep(1)
                page.locator("[data-finish-recording]").click()
                expect(page.locator("[data-video-upload]")).to_be_visible()
                page.locator("[data-clear-draft]").click()
                for name in ("one", "two"):
                    page.locator("#draft-file").set_input_files(str(temp / f"{name}.mp4"))
                    expect(page.locator("[data-video-upload]")).to_be_visible()
                    page.locator("#video-title").fill(f"UI fixture {name}")
                    page.locator("#camera-setup-id").fill("test-side")
                    for selector in ("weapon-arm", "front-leg", "facing"):
                        page.locator("#" + selector).select_option("right")
                    page.locator("#camera-motion").select_option("fixed")
                    page.locator("[data-video-upload]").click()
                    expect(page.locator("[data-video-accept]")).to_be_enabled(timeout=30000)
                    expect(page.locator("[data-rep-review-seek]")).to_have_count(1)
                    page.locator("[data-rep-review-seek]").first.click()
                    page.locator("[data-video-accept]").click()
                    # Wait for acceptance and session loading to finish before navigating.
                    ask_coach = page.get_by_role("button", name="Ask the coach")
                    expect(ask_coach).to_be_visible(timeout=15000)
                    ask_coach.click()
                    page.locator("#question").fill("What can you tell me about my lunge?")
                    page.locator('#coach-form button[type="submit"]').click()
                    expect(page.locator(".chat-message.coach").last).to_contain_text(
                        "slow", timeout=15000
                    )
                    if name == "one":
                        # A rejected request must be visible at the composer and leave it usable.
                        pattern = "**/api/sessions/*/coaching-jobs"

                        def reject_chat(route):
                            route.fulfill(
                                status=422,
                                content_type="application/json",
                                body=json.dumps(
                                    {
                                        "detail": "This video is unsupported for coaching. Whole body must stay in frame."
                                    }
                                ),
                            )

                        page.route(pattern, reject_chat)
                        page.locator("#question").fill("Review my lunge again")
                        page.locator("#question").press("Enter")
                        expect(page.locator(".coach-error")).to_contain_text(
                            "Whole body must stay in frame"
                        )
                        expect(page.locator("#question")).to_be_enabled()
                        page.unroute(pattern, reject_chat)
                        page.locator("#question").fill("What is recovery in fencing?")
                        page.locator("#question").press("Enter")
                        expect(page.locator("#question")).to_be_enabled(timeout=15000)
                        expect(page.locator(".coach-error")).to_have_count(0)
                        # A missing persisted job should clear itself instead of disabling chat.
                        page.evaluate(
                            "localStorage.setItem('fencecoach.coachingJob', 'missing-fixture-job')"
                        )
                        page.reload()
                        expect(page.locator(".coach-error")).to_contain_text(
                            "Coaching request not found"
                        )
                        expect(page.locator("#question")).to_be_enabled()
                        assert (
                            page.evaluate("localStorage.getItem('fencecoach.coachingJob')") is None
                        )
                    page.locator('[data-go="progress"]').first.click()
                    page.locator("[data-log-new]").click()
                    page.locator('#training-log-form [name="focus"]').fill(
                        f"Persistent fixture {name}"
                    )
                    page.locator('#training-log-form button[type="submit"]').click()
                    expect(page.locator(".journal-list")).to_contain_text(
                        f"Persistent fixture {name}"
                    )
                    page.reload()
                    page.locator('[data-go="progress"]').first.click()
                    expect(page.locator(".journal-list")).to_contain_text(
                        f"Persistent fixture {name}"
                    )
                    page.locator('[data-go="record"]').first.click()
                    if page.locator("[data-clear-draft]").count():
                        page.locator("[data-clear-draft]").click()
                page.locator("#draft-file").set_input_files(str(temp / "one.mp4"))
                page.locator("#video-title").fill("Unsupported fixture")
                page.locator("[data-video-upload]").click()
                expect(page.locator("[data-video-accept]")).to_be_disabled(timeout=30000)
                expect(page.locator("body")).to_contain_text("720p", timeout=10000)
                page.screenshot(path=str(output / "unsupported.png"), full_page=True)
                mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
                m = mobile.new_page()
                m.goto(base)
                m.locator('[data-go="progress"]:visible').first.click()
                assert m.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                ), "Horizontal overflow on mobile"
                m.screenshot(path=str(output / "mobile.png"), full_page=True)
                mobile.close()
                context.close()
                browser.close()
            assert not errors, errors
            report = {
                "status": "passed",
                "clips": 2,
                "recording": "fake browser camera exercised",
                "upload_job_review_coach_log_reload": True,
                "unsupported_save_disabled": True,
                "mobile_width": 390,
                "page_errors": errors,
                "analysis_and_llm": "Synthetic test fixtures; real HTTP, queue, persistence, and UI. Does not validate pose inference or coaching correctness.",
            }
            (project / "data/evals/browser-smoke.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            log.close()


if __name__ == "__main__":
    main()

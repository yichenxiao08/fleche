"""Exercise the recorded player in Chromium and prove it makes no API calls."""

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "src/fencecoach/web"))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    prohibited, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1200, "height": 900})

            def route(request_route):
                url = request_route.request.url
                if not url.startswith(base + "/") or "/api/" in url:
                    prohibited.append(url)
                    request_route.abort()
                else:
                    request_route.continue_()

            context.route("**/*", route)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/recorded-coach.html")
            expect(page.locator(".recorded")).to_have_count(2)
            recordings = json.loads(page.locator("#recordings").text_content())
            assert len(recordings) == 3
            for index, recording in enumerate(recordings):
                page.locator("#recording").select_option(index=index)
                for number, turn in enumerate(recording["turns"], 1):
                    page.locator("#next").click()
                    expect(page.locator(".turn")).to_have_count(number)
                    assert (
                        page.locator(".coach").last.evaluate("e => e.lastChild.textContent")
                        == turn["answer"]
                    )
                    assert (
                        page.locator(".athlete").last.evaluate("e => e.lastChild.textContent")
                        == turn["question"]
                    )
                expect(page.locator("#next")).to_be_disabled()
                page.locator("#reset").click()
                expect(page.locator(".turn")).to_have_count(0)
                page.locator("#play").click()
                expect(page.locator("#progress")).to_have_text(
                    f"{len(recording['turns'])} of {len(recording['turns'])} turns", timeout=6000
                )
                expect(page.locator("#play")).to_be_disabled()
            page.screenshot(path=str(ROOT / "work/recorded-coach-demo-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(ROOT / "work/recorded-coach-demo-mobile.png"), full_page=True)
            assert not prohibited, prohibited
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(
        "Three recorded conversations replayed verbatim; next/play/reset/selection/mobile passed; zero API/external requests and browser errors."
    )


if __name__ == "__main__":
    main()

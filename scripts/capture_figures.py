"""Capture the README figures from the built demo: screenshots at 2x and the three GIFs, from real recordings.

    uv run python scripts/capture_figures.py [--only hero evidence venn verify ghosts]

Needs ``npm run build`` in ``skeleton/web``, Playwright with Chromium and ffmpeg on the PATH. The static demo in
``skeleton/web/dist`` is served on a free local port and driven in headless Chromium. Headless Chromium draws no cursor,
so the recordings show the page and nothing else.

Writes ``docs/figures/ui-night-3.png`` and ``docs/figures/ui-vampire-evidence.png`` (device scale 2) and, from Playwright recordings kept
in ``build/recordings`` (gitignored), the GIFs ``docs/figures/venn-click.gif``, ``verify-then-change-one-byte.gif`` and
``ghosts-decision.gif``, each cut with ``scripts/make_gif.py`` (96 colours, no dithering, under 5 MB).
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "skeleton" / "web" / "dist"
FIGURES = ROOT / "docs" / "figures"
RECORDINGS = ROOT / "build" / "recordings"
VIEWPORT = {"width": 1280, "height": 800}
GIF_WIDTH = 900
SHOTS = ("hero", "evidence")
MOMENTS = ("venn", "verify", "ghosts")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base class names it so
        return


def serve() -> tuple[str, http.server.ThreadingHTTPServer]:
    handler = functools.partial(_Quiet, directory=str(DIST))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/", server


def newest_run(app_folder: str) -> str:
    runs = json.loads((DIST / "demo" / app_folder / "runs.json").read_text(encoding="utf-8"))
    return str(runs[0]["run_id"])


def open_app(page: Page, base: str, query: str) -> None:
    page.goto(base + query)
    page.wait_for_selector("#headline")
    page.wait_for_selector("svg.venn")


def shot_hero(browser: Browser, base: str) -> None:
    """The top of the Vampires demo page, as a visitor sees it."""
    page = browser.new_page(viewport={"width": 1440, "height": 1120}, device_scale_factor=2)
    open_app(page, base, "?app=vampires-demo")
    page.screenshot(path=str(FIGURES / "ui-night-3.png"))
    page.close()


def shot_evidence(browser: Browser, base: str) -> None:
    """The Vampire's row opened: the billed line, the inventory line and the instruction planted in a tag, as data."""
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=2)
    open_app(page, base, "?app=vampires-demo")
    page.click('.legend-item[data-region="OB"]')
    row = page.locator(".row").first
    row.locator(".row-head").click()
    page.wait_for_selector("table.evidence")
    row.screenshot(path=str(FIGURES / "ui-vampire-evidence.png"))
    page.close()


class Recording:
    """One Playwright video of one page. ``mark`` notes the seconds since the page started when the action begins."""

    def __init__(self, browser: Browser, name: str) -> None:
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        self.folder = RECORDINGS / name
        shutil.rmtree(self.folder, ignore_errors=True)
        self.context = browser.new_context(
            viewport=VIEWPORT, record_video_dir=str(self.folder), record_video_size=VIEWPORT
        )
        self.page = self.context.new_page()
        self.began = time.monotonic()
        self.start = 0.0
        self.end = 0.0

    def action_begins(self) -> None:
        self.start = time.monotonic() - self.began

    def action_ends(self) -> None:
        self.end = time.monotonic() - self.began

    def finish(self) -> Path:
        video = self.page.video
        assert video is not None
        self.context.close()
        return Path(video.path())


def hold(page: Page, seconds: float) -> None:
    """Let the viewer read: the recording has no cursor, so a pause is all there is to hold."""
    page.wait_for_timeout(int(seconds * 1000))


def record_venn(browser: Browser, base: str) -> tuple[Path, float, float, str | None]:
    rec = Recording(browser, "venn-click")
    page = rec.page
    open_app(page, base, "?app=vampires-demo")
    venn = page.locator("svg.venn")
    page.evaluate("(y) => window.scrollTo(0, y)", int(venn.bounding_box()["y"]) - 90)
    hold(page, 1.0)
    rec.action_begins()
    hold(page, 2.0)
    box = venn.bounding_box()
    assert box is not None
    venn.click(position={"x": box["width"] * 282 / 440, "y": box["height"] * 222 / 400})
    page.wait_for_selector(".row")
    hold(page, 2.0)
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    page.locator(".row").first.scroll_into_view_if_needed()
    hold(page, 4.5)
    rec.action_ends()
    return rec.finish(), rec.start, rec.end, None


def record_verify(browser: Browser, base: str) -> tuple[Path, float, float, str | None]:
    rec = Recording(browser, "verify-then-change-one-byte")
    page = rec.page
    open_app(page, base, "?app=vampires-demo")
    page.locator(".foot").scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    hold(page, 1.0)
    rec.action_begins()
    hold(page, 1.0)
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    hold(page, 3.0)
    page.click('[data-action="tamper"]')
    page.wait_for_selector(".verdict.failed")
    hold(page, 4.0)
    rec.action_ends()
    box = page.locator(".foot").bounding_box()
    assert box is not None
    top = max(0, int(box["y"]) - 40)
    crop = f"{VIEWPORT['width']}:{VIEWPORT['height'] - top}:0:{top}"
    return rec.finish(), rec.start, rec.end, crop


def record_ghosts(browser: Browser, base: str) -> tuple[Path, float, float, str | None]:
    rec = Recording(browser, "ghosts-decision")
    page = rec.page
    open_app(page, base, f"?app=ghosts-demo&run={newest_run('ghosts')}")
    hold(page, 1.0)
    rec.action_begins()
    hold(page, 2.0)
    row = page.locator(".row", has=page.locator(".row-decision")).first
    row.scroll_into_view_if_needed()
    hold(page, 1.5)
    row.locator(".row-head").click()
    page.wait_for_selector("table.evidence")
    row.scroll_into_view_if_needed()
    hold(page, 5.0)
    rec.action_ends()
    return rec.finish(), rec.start, rec.end, None


RECORDERS: dict[str, tuple[Callable[[Browser, str], tuple[Path, float, float, str | None]], str]] = {
    "venn": (record_venn, "venn-click.gif"),
    "verify": (record_verify, "verify-then-change-one-byte.gif"),
    "ghosts": (record_ghosts, "ghosts-decision.gif"),
}


def make_gif(video: Path, out: Path, start: float, end: float, crop: str | None) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "make_gif.py"),
        str(video),
        str(out),
        "--start",
        f"{start:.2f}",
        "--duration",
        f"{end - start:.2f}",
        "--width",
        str(GIF_WIDTH),
        "--fps",
        "12",
        "--colors",
        "96",
        "--dither",
        "none",
    ]
    if crop:
        command += ["--crop", crop]
    return subprocess.run(command, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", choices=[*SHOTS, *MOMENTS], help="make only these figures")
    args = parser.parse_args()
    wanted: set[str] = set(args.only or [*SHOTS, *MOMENTS])
    if not (DIST / "index.html").exists():
        raise SystemExit("build the front end first: npm run build in skeleton/web")
    FIGURES.mkdir(parents=True, exist_ok=True)
    base, server = serve()
    failed = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            if "hero" in wanted:
                shot_hero(browser, base)
                print("wrote docs/figures/ui-night-3.png")
            if "evidence" in wanted:
                shot_evidence(browser, base)
                print("wrote docs/figures/ui-vampire-evidence.png")
            for name, (record, gif) in RECORDERS.items():
                if name in wanted:
                    video, start, end, crop = record(browser, base)
                    failed += make_gif(video, FIGURES / gif, start, end, crop)
            browser.close()
    finally:
        server.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

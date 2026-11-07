"""Capture the link card and the review screenshots from the built demo (ui-kit Req 9.1).

* ``skeleton/web/public/og.png``: the demo overview at 1200 x 630, with the product name in the masthead. Sections that
  do not fit whole are left out, and the script stops if any text still touches an edge.
* with ``--review``: full-page screenshots at 1440 and 390 px wide into ``build/screens/`` (gitignored), for the
  overview, a region filter, an opened finding, verify, change one byte and the morning report.

Needs ``npm run build`` in ``skeleton/web`` and Playwright with Chromium. Serves ``skeleton/web/dist`` with the static
demo on a free local port, headless.

Run: ``uv run python scripts/capture_card.py [--review]``
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import threading
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "skeleton" / "web" / "dist"
CARD = ROOT / "skeleton" / "web" / "public" / "og.png"
SCREENS = ROOT / "build" / "screens"
DEMO = "?app=vampires-demo"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base class names it so
        return


def _serve() -> tuple[str, http.server.ThreadingHTTPServer]:
    handler = functools.partial(_Quiet, directory=str(DIST))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/", server


def _open(page: Page, url: str) -> None:
    page.goto(url)
    page.wait_for_selector("#headline")


def _review(page: Page, base: str, width: int) -> None:
    tag = f"{width}"
    _open(page, base + DEMO)
    page.screenshot(path=str(SCREENS / f"{tag}-overview.png"), full_page=True)
    page.click('.legend-item[data-region="OB"]')
    page.screenshot(path=str(SCREENS / f"{tag}-filter-OB.png"), full_page=True)
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    page.screenshot(path=str(SCREENS / f"{tag}-opened.png"), full_page=True)
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    page.screenshot(path=str(SCREENS / f"{tag}-verified.png"), full_page=True)
    page.click('[data-action="tamper"]')
    page.wait_for_selector(".verdict.failed")
    page.locator(".foot").screenshot(path=str(SCREENS / f"{tag}-tampered.png"))
    page.click(".mast-link")
    page.wait_for_selector(".headline")
    page.screenshot(path=str(SCREENS / f"{tag}-report.png"), full_page=True)


CARD_SIZE = {"width": 1200, "height": 630}

#: Drops every top-level section of the page that does not fit whole in the card, so the bottom edge falls between
#: sections and never through a heading. The masthead and the opening section stay, so the card shows the product name.
_FIT_SECTIONS = """
(height) => {
  const dropped = [];
  for (const section of document.querySelectorAll("main.page > section, main.page > footer")) {
    if (section.getBoundingClientRect().bottom > height) {
      section.style.display = "none";
      dropped.push(section.getAttribute("aria-label") || section.className);
    }
  }
  return dropped;
}
"""

#: Lists every visible element that holds text and reaches past an edge of the card.
_CUT_TEXT = """
({width, height}) => {
  const cut = [];
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".skip")) continue; // parked off-screen until it has focus
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== "");
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.top < 0 || r.left < 0 || r.bottom > height || r.right > width) {
      cut.push(`${el.tagName.toLowerCase()} "${el.textContent.trim().slice(0, 40)}"`);
    }
  }
  return cut;
}
"""


def _fit_card(page: Page) -> None:
    """Make the card show only whole sections, and fail if any text still touches an edge."""
    page.evaluate(_FIT_SECTIONS, CARD_SIZE["height"])
    if not page.locator("main.page > section").count():
        raise SystemExit("the card has no whole section to show")
    cut = page.evaluate(_CUT_TEXT, CARD_SIZE)
    if cut:
        raise SystemExit("text is cut at an edge of the card: " + "; ".join(cut))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--review", action="store_true", help="also write review screenshots to build/screens")
    args = parser.parse_args()
    if not (DIST / "index.html").exists():
        raise SystemExit("build the front end first: npm run build in skeleton/web")
    base, server = _serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            card = browser.new_page(viewport=CARD_SIZE, reduced_motion="reduce")
            _open(card, base + DEMO)
            _fit_card(card)
            card.screenshot(path=str(CARD))
            print(f"wrote {CARD.relative_to(ROOT)}")
            if args.review:
                SCREENS.mkdir(parents=True, exist_ok=True)
                for width in (1440, 390):
                    page = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                    _review(page, base, width)
                    page.close()
                print(f"wrote review screenshots to {SCREENS.relative_to(ROOT)}")
            browser.close()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Render a figure kept as an HTML file with one ``<svg id="figure">`` to a PNG at 2x on a white ground.

    uv run python scripts/render_figure.py [docs/figures/architecture.html]

The PNG is written beside the source with the same name. The source loads its fonts from ``skeleton/web/node_modules``,
so run ``npm ci`` in ``skeleton/web`` first. Needs Playwright with Chromium.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "figures" / "architecture.html").resolve()
    out = source.with_suffix(".png")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=2)
        page.goto(source.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_function("document.fonts.status === 'loaded'")
        page.locator("#figure").screenshot(path=str(out))
        browser.close()
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

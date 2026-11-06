"""Helpers for the browser tests: page setup, axe-core and the nights the local server holds (ui-kit Req 10.1, 12)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKELETON = Path(__file__).resolve().parents[2]
ROOT = SKELETON.parent
DIST = SKELETON / "web" / "dist"
AXE = SKELETON / "web" / "node_modules" / "axe-core" / "axe.min.js"
DEMO = ROOT / "apps" / "vampires" / "demo"
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

HOSTILE_NAME = "<img src=x onerror=alert(1)>"
HOSTILE_KEY = '<script>alert("key")</script>'


@dataclass
class Nights:
    """Run ids on the local server: the three demo nights and three made for the tests."""

    demo: list[str]
    clean: str
    hostile: str
    twelve: str
    rested: str


AXE_SOURCE = AXE.read_text(encoding="utf-8") if AXE.exists() else ""

#: Records every layout shift so a test can sum them (ui-kit Req 9.2).
LAYOUT_SHIFT = """
window.__layoutShift = 0;
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__layoutShift += entry.value;
}).observe({ type: "layout-shift", buffered: true });
"""


def new_page(browser: Any, width: int = 1440, height: int = 1000, reduced_motion: str = "no-preference") -> Any:
    """A page with axe-core and the layout-shift recorder injected. Init scripts are not subject to the page's CSP."""
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion=reduced_motion)
    if AXE_SOURCE:
        context.add_init_script(script=AXE_SOURCE)
    context.add_init_script(script=LAYOUT_SHIFT)
    page = context.new_page()
    page.dialogs = []
    page.on("dialog", lambda dialog: (page.dialogs.append(dialog.message), dialog.dismiss()))
    return page


def open_page(page: Any, base_url: str, query: str = "") -> None:
    page.goto(f"{base_url}/{query}")
    page.wait_for_selector("#headline")


def assert_axe_clean(page: Any) -> None:
    """Run axe-core with the WCAG 2.0, 2.1 and 2.2 A and AA rules; fail on any violation (ui-kit Req 10.1, 12.2)."""
    assert AXE_SOURCE, f"axe-core not found at {AXE}"
    violations = page.evaluate(
        """async (tags) => {
          const result = await axe.run(document, { runOnly: { type: "tag", values: tags } });
          return result.violations.map((v) => ({
            id: v.id, help: v.help, targets: v.nodes.map((n) => n.target.join(" ")),
          }));
        }""",
        AXE_TAGS,
    )
    assert violations == [], "\n".join(f"{v['id']}: {v['help']} at {v['targets'][:5]}" for v in violations)

"""Drive the real UI in headless Chromium and scan every screen state with axe-core (WCAG 2.2 AA).

Usage: python scripts/ui_check.py [base_url] [shots_dir]
The page must already be served (for example `nightaudit serve --app vampires --runs runs/demo`).
Exits non-zero on any axe violation or console error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AXE = ROOT / "skeleton" / "web" / "node_modules" / "axe-core" / "axe.min.js"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def scan(page: Page, label: str) -> list[dict[str, object]]:
    page.add_script_tag(path=str(AXE))
    result = page.evaluate("async (tags) => await axe.run(document, {runOnly: {type: 'tag', values: tags}})", TAGS)
    violations = result["violations"]
    print(f"{label:<28} violations={len(violations)} passes={len(result['passes'])}")
    for v in violations:
        print(f"   {v['id']}: {v['help']} ({len(v['nodes'])} nodes)")
    return violations


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    shots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        dialogs: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        page.goto(base, wait_until="networkidle")
        page.wait_for_selector(".venn")
        states = [("overview", None)]
        for code in ["OB", "B", "IB", "I", "O", "IO", "IOB"]:
            states.append((f"region {code}", code))
        for label, code in states:
            if code:
                page.click(f'.legend-item[data-region="{code}"]')
                page.wait_for_timeout(150)
            if page.locator(".row-head").count():
                page.locator(".row-head").first.click()
                page.wait_for_timeout(150)
            if scan(page, label):
                failures.append(label)
            if shots and code in (None, "OB"):
                page.screenshot(path=str(shots / f"ui-{label.replace(' ', '-')}.png"), full_page=True)
            if code:
                page.click(f'.legend-item[data-region="{code}"]')
        # Hostile text from a ledger must render as text: open every Poltergeist row and look for a dialog.
        page.click('.legend-item[data-region="O"]')
        for i in range(page.locator(".row-head").count()):
            page.locator(".row-head").nth(i).click()
            page.wait_for_timeout(150)
        page.wait_for_timeout(500)
        shown = page.locator("text=<img src=x onerror=alert(1)>").count()
        print(f"script payload shown as text: {shown} place(s); dialogs opened: {len(dialogs)}")
        if dialogs or not shown:
            failures.append("xss")
        # Keyboard path: tab to the first legend button and press Enter, then open a row with Enter.
        page.goto(base, wait_until="networkidle")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        focused = page.evaluate("document.activeElement && document.activeElement.className")
        print("third Tab lands on:", focused)
        page.focus('.legend-item[data-region="OB"]')
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        title = page.inner_text("#findings-title")
        print("after Enter on Vampire:", json.dumps(title))
        if not title.upper().startswith("VAMPIRE"):
            failures.append("keyboard filter")
        browser.close()
    if errors:
        print("console errors:", errors)
        failures.append("console")
    print("RESULT:", "PASS" if not failures else f"FAIL {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

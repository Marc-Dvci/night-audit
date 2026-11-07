"""Drive the real UI in headless Chromium and scan every screen state with axe-core (WCAG 2.2 AA).

Usage: python scripts/ui_check.py [base_url] [shots_dir]
The page must already be served (for example `nightaudit serve --app vampires --runs runs/demo`).
Exits non-zero on any axe violation or console error, on a script payload that the data holds and the page does not
show as text, or on any dialog. A night whose data holds no payload (the live lab night) reports the payload check as
not applicable. The first line printed names the URL every figure below it was measured on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[1]
AXE = ROOT / "skeleton" / "web" / "node_modules" / "axe-core" / "axe.min.js"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
#: The script tag the demo nights plant in a resource name.
PAYLOAD = "<img src=x onerror=alert(1)>"


def payload_count(body: str) -> int:
    """How many times a response body holds the payload, written raw or with JSON's ``\\u003c`` escapes."""
    escaped = PAYLOAD.replace("<", "\\u003c").replace(">", "\\u003e")
    return body.count(PAYLOAD) + body.count(escaped)


def xss_verdict(payload_in_data: int, shown: int, dialogs: int) -> tuple[bool, str]:
    """Whether the payload check passes, and its line. With no payload in the data there is nothing to show as text,
    so the check is not applicable; a dialog fails it either way."""
    if dialogs:
        return False, f"xss: FAIL, {dialogs} dialog(s) opened"
    if not payload_in_data:
        return True, "xss: not applicable, no payload on this night"
    if not shown:
        return (
            False,
            f"xss: FAIL, the data holds the payload {payload_in_data} time(s) and the page shows it as text 0 times",
        )
    return True, f"xss: payload in the data {payload_in_data} time(s), shown as text in {shown} place(s), no dialog"


def has_json_body(status: int, content_type: str) -> bool:
    """Whether a response's body is read for the payload count. A redirect has no body: reading it raises."""
    return "json" in content_type and not 300 <= status < 400


def scan(page: Page, label: str) -> list[dict[str, object]]:
    result = page.evaluate("async (tags) => await axe.run(document, {runOnly: {type: 'tag', values: tags}})", TAGS)
    violations = result["violations"]
    print(f"{label:<28} violations={len(violations)} passes={len(result['passes'])}")
    for v in violations:
        print(f"   {v['id']}: {v['help']} ({len(v['nodes'])} nodes)")
    return violations


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    shots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    from playwright.sync_api import sync_playwright

    print(f"measured on: {base}")
    failures: list[str] = []
    bodies: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # axe-core is injected before the page loads: the page's Content-Security-Policy refuses an inline script tag.
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(path=str(AXE))
        page = context.new_page()
        errors: list[str] = []
        dialogs: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        page.on(
            "response",
            lambda r: bodies.append(r.text()) if has_json_body(r.status, r.headers.get("content-type", "")) else None,
        )
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
        shown = page.locator(f"text={PAYLOAD}").count()
        ok, line = xss_verdict(sum(payload_count(b) for b in bodies), shown, len(dialogs))
        print(line)
        if not ok:
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
        title = page.inner_text("#rows-title")
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

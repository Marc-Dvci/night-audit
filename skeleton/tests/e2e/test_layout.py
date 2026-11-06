"""Layout: phones, unbroken words, no layout shift, one A4 report, same origin only (ui-kit Req 3.4, 7.1, 9, 10.3)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from e2e.browser_kit import Nights, new_page, open_page

pytestmark = pytest.mark.e2e
Served = tuple[Path, Nights]

SUMMARY = ".headline, .tagline, .money-line, .ledger-head, .ledger-source, .stamp"

#: For every word of every summary line, the number of line boxes it spans. A word split across lines spans two.
SPLIT_WORDS = """(selector) => {
  const split = [];
  for (const el of document.querySelectorAll(selector)) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent;
      for (const m of text.matchAll(/\\S+/g)) {
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        const tops = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
        if (tops.size > 1) split.push(m[0]);
      }
    }
  }
  return split;
}"""


@pytest.mark.parametrize("width", [360, 390, 768, 1024, 1440])
def test_no_summary_word_is_broken_and_nothing_scrolls_sideways(
    browser: Any, base_url: str, nights: tuple[Path, Nights], width: int
) -> None:
    _, n = nights
    page = new_page(browser, width=width, height=900)
    for run in (n.demo[2], n.clean, n.hostile):
        open_page(page, base_url, f"?app=vampires&run={run}")
        assert page.evaluate(SPLIT_WORDS, SUMMARY) == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), run
    page.context.close()


def test_fonts_arrive_without_moving_anything(page: Any, base_url: str, nights: tuple[Path, Nights]) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.evaluate("document.fonts.ready")
    assert page.evaluate("[...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family)")
    assert page.evaluate("window.__layoutShift") == 0


def test_the_page_requests_nothing_from_another_origin(browser: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    page = new_page(browser)
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    assert requests and all(url.startswith(base_url) for url in requests), requests
    page.context.close()


def test_the_report_of_twelve_findings_prints_on_one_a4_page(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    page.goto(f"{base_url}/api/runs/{n.twelve}/report.html")
    assert page.locator("table.findings tbody tr").count() == 12
    pdf = page.pdf(format="A4", print_background=True)
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 1

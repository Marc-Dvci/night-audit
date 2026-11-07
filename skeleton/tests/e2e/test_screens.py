"""Every screen state of the demo path in headless Chromium, each checked by axe-core (ui-kit Req 2, 4-8, 10-12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from e2e.browser_kit import HOSTILE_KEY, HOSTILE_NAME, Nights, assert_axe_clean, new_page, open_page

pytestmark = pytest.mark.e2e
Served = tuple[Path, Nights]
#: A region's label is read without knowing any of these words (product rules: plain words first).
HALLOWEEN_WORDS = ("Vampire", "Ghost", "Poltergeist", "Phantom", "Skeleton", "Wraith", "Familiar", "Living")

#: The rendered size of every text in <main>: CSS font size for HTML, font size times the drawing scale for SVG text.
TEXT_SIZES = """() => [...document.querySelectorAll('main *')]
  .filter((e) => [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim()))
  .map((e) => {
    const size = parseFloat(getComputedStyle(e).fontSize);
    const svg = e.closest('svg');
    const scale = svg ? svg.getBoundingClientRect().width / svg.viewBox.baseVal.width : 1;
    return [e.id || String(e.className.baseVal ?? e.className), size * scale];
  })"""


def query(page: Any) -> dict[str, list[str]]:
    return parse_qs(urlparse(page.url).query)


def test_overview_states_what_is_compared_and_tonights_result(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    headline = page.inner_text("#headline")
    assert headline.startswith("2 resources are running and on the bill with no approval:")
    assert page.inner_text(".tagline").startswith("Every night, this AWS account is checked")
    ledgers = page.inner_text(".ledgers")
    for word in ("DECLARED", "RUNNING", "BILLED", "resources", "Cost and Usage Report 2.0 line items."):
        assert word in ledgers.upper() if word.isupper() else word in ledgers
    assert page.locator("svg.venn").is_visible()
    # The headline is the largest text on the page below the masthead.
    sizes = page.evaluate(TEXT_SIZES)
    largest = max(sizes, key=lambda pair: pair[1])
    assert largest[0] == "headline-lead", largest
    assert_axe_clean(page)


@pytest.mark.parametrize("code", ["OB", "B", "IB", "O", "I", "IO", "IOB"])
def test_each_region_filter_names_the_region_and_its_meaning(
    page: Any, base_url: str, nights: Served, code: str
) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[0]}")
    page.click(f'.legend-item[data-region="{code}"]')
    page.wait_for_selector(".filter-note")
    assert query(page)["region"] == [code]
    assert page.get_attribute(f'.legend-item[data-region="{code}"]', "aria-pressed") == "true"
    assert page.inner_text(".filter-meaning")
    # The region is named by its plain label: the filter note and the section title lead with it, never the tag.
    label = page.inner_text(".filter-label")
    assert label and not any(word in label for word in HALLOWEEN_WORDS), label
    assert page.inner_text("#rows-title").upper().startswith(label.upper())  # the rule title is set in capitals
    assert page.inner_text(f'.legend-item[data-region="{code}"] .legend-label') == label
    assert_axe_clean(page)
    page.click('[data-action="clear-filter"]')
    assert "region" not in query(page)


def test_a_venn_region_click_filters_the_rows(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    venn = page.locator("svg.venn")
    box = venn.bounding_box()
    # (282, 222) of the 440 x 400 view box is inside the OB region. locator.click scrolls the diagram into view first.
    venn.click(position={"x": box["width"] * 282 / 440, "y": box["height"] * 222 / 400})
    assert query(page)["region"] == ["OB"]


def test_an_opened_finding_shows_its_evidence(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    head = page.locator(".row-head").first
    head.focus()
    page.keyboard.press("Enter")
    assert page.locator(".row-head").first.get_attribute("aria-expanded") == "true"
    page.wait_for_selector("table.evidence")
    assert query(page)["open"]
    assert_axe_clean(page)


def test_a_deep_link_opens_and_scrolls_to_the_finding(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    key = "i-0f3e9b1d2c4a5e6f7"
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}&region=OB&open={key}")
    head = page.locator(f'.row-head[data-key="{key}"]')
    assert head.get_attribute("aria-expanded") == "true"
    page.wait_for_function(
        "(el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; }",
        arg=head.element_handle(),
        timeout=2000,
    )
    assert page.evaluate("document.activeElement.dataset.key") == key
    assert query(page)["open"] == [key]


def test_a_deep_link_to_nothing_shows_the_run(page: Any, base_url: str) -> None:
    open_page(page, base_url, "?app=nope&run=zzzz&region=XYZ&open=missing")
    params = query(page)
    assert "region" not in params and "open" not in params
    assert page.inner_text("#headline")


def test_the_nights_strip_opens_a_night(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    marks = page.locator(".night")
    assert marks.count() == 3
    assert "2 new" in page.inner_text(".strip")
    marks.first.click()
    page.wait_for_selector(f'.night[data-run="{n.demo[0]}"][aria-current="date"]')
    assert query(page)["run"] == [n.demo[0]]
    assert_axe_clean(page)


def test_laid_to_rest_lists_what_was_resolved(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.rested}")
    text = page.inner_text(".rest")
    assert "LAID TO REST" in text.upper()
    for part in ("Exists, never approved, not billed", "Poltergeist", "gone-soon", "10 Nov 2026", "2 nights"):
        assert part in text, part
    assert text.index("Exists, never approved, not billed") < text.index("Poltergeist")
    assert_axe_clean(page)


def test_verify_counts_the_rows_and_matches_the_page(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    verdict = page.inner_text("#verdict")
    chain = page.inner_text("#chain-hash")
    assert verdict.startswith("VERIFIED")
    assert chain in verdict and "matches the manifest and the hash on this page" in verdict
    assert page.inner_text("#printer").count("ROW ") >= 10
    assert_axe_clean(page)


def test_verify_with_reduced_motion_prints_only_the_final_line(browser: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    page = new_page(browser, reduced_motion="reduce")
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    assert page.inner_text("#printer") == ""
    page.context.close()


def test_change_one_byte_fails_at_a_row_and_restore_verifies(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.ok")
    page.click('[data-action="tamper"]')
    page.wait_for_selector(".verdict.failed")
    assert page.inner_text("#verdict").startswith("FAILED at row ")
    assert_axe_clean(page)
    page.click('[data-action="restore"]')
    page.wait_for_selector(".verdict.ok")


def test_a_forged_finding_in_the_served_run_makes_verify_fail_and_names_it(
    page: Any, base_url: str, nights: Served
) -> None:
    """Regression: the page showed an edited finding beside a passing "verified"."""
    _, n = nights

    def serve_a_lie(route: Any) -> None:
        response = route.fetch()
        document = response.json()
        forged = dict(document["findings"][0])
        forged["key"] = "i-0forged"
        document["findings"].append(forged)
        route.fulfill(response=response, json=document)

    page.route(f"**/api/runs/{n.demo[2]}", serve_a_lie)
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    assert "i-0forged" in page.inner_text("body")
    page.click('[data-action="verify"]')
    page.wait_for_selector(".verdict.failed")
    verdict = page.inner_text("#verdict")
    assert verdict.startswith("FAILED")
    assert 'finding "i-0forged" is shown but is not in the evidence' in verdict
    assert "VERIFIED" not in verdict


def test_the_report_is_linked_and_loads_nothing_else(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    page.click(".mast-link")
    page.wait_for_selector(".headline")
    assert "MORNING REPORT" in page.inner_text(".brand")
    assert all(url.startswith(base_url) for url in requests)
    assert_axe_clean(page)


def test_a_clean_night_reads_as_finished(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.clean}")
    assert page.inner_text("#headline") == "All three ledgers agree. Nothing to report tonight."
    labels = [t.strip() for t in page.locator("svg.venn .venn-count").all_text_contents()]
    assert labels == ["2"], labels
    assert page.locator(".legend").count() == 0
    assert "appear in all three ledgers" in page.inner_text("#rows")
    assert_axe_clean(page)


@pytest.mark.parametrize("width", [390, 360])
def test_a_phone_has_no_horizontal_scroll(browser: Any, base_url: str, nights: Served, width: int) -> None:
    _, n = nights
    page = new_page(browser, width=width, height=800)
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    scrolls = "(() => { const s = document.querySelector('.scroll'); return s.scrollWidth > s.clientWidth; })()"
    assert page.evaluate(scrolls), "the evidence table scrolls inside its own container"
    assert_axe_clean(page)
    page.context.close()


def test_a_script_payload_in_a_ledger_is_only_text(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.hostile}")
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    text = page.inner_text("main")
    assert HOSTILE_KEY in text and HOSTILE_NAME in text
    assert page.locator("main img, main script").count() == 0
    assert page.dialogs == []
    assert_axe_clean(page)


def test_every_action_is_reachable_by_keyboard_with_a_phosphor_ring(page: Any, base_url: str, nights: Served) -> None:
    _, n = nights
    open_page(page, base_url, f"?app=vampires&run={n.demo[2]}")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip"
    seen: set[str] = set()
    for _ in range(200):
        page.keyboard.press("Tab")
        info = page.evaluate("""() => { const e = document.activeElement; const s = getComputedStyle(e);
            return [e.id || e.dataset.action || e.className, s.outlineColor, s.outlineStyle]; }""")
        if info[0] in seen and info[0] == "skip":
            break
        seen.add(info[0])
        if info[0] and info[0] != "skip":
            assert info[1] == "rgb(124, 255, 178)" and info[2] == "solid", info
    for wanted in ("run-select", "mast-link", "verify"):
        assert any(wanted in item for item in seen), (wanted, seen)
    assert any("legend-item" in item for item in seen)
    assert any("row-head" in item for item in seen)
    assert any(item.startswith("night") for item in seen)

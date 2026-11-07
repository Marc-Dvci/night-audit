"""The Ghosts page in headless Chromium, through the same server and axe checks as every other screen (Req 10).

The pages are the static Ghosts demo shipped in the build (``dist/demo/ghosts/``), which is what a visitor opens: two
nights of Hollow Pines, the first with no review decision and the second with three.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from e2e.browser_kit import DIST, assert_axe_clean, new_page, open_page

pytestmark = pytest.mark.e2e
GHOSTS = DIST / "demo" / "ghosts"
#: Words that belong to the cloud app. On a page about people none of them may appear.
CLOUD_WORDS = re.compile(r"\b(resources?|resource id|keys?)\b", re.IGNORECASE)


def ghost_nights() -> tuple[str, str]:
    """The Ghosts demo run ids, (first night, second night)."""
    runs = json.loads((GHOSTS / "runs.json").read_text("utf-8")) if (GHOSTS / "runs.json").exists() else []
    if len(runs) != 2:
        pytest.skip("build the demos and the front end: uv run python scripts/build_demos.py; npm run build")
    newest, oldest = runs[0]["run_id"], runs[1]["run_id"]
    return oldest, newest


def test_the_ghosts_overview_speaks_about_people(page: Any, base_url: str) -> None:
    _, second = ghost_nights()
    open_page(page, base_url, f"?app=ghosts-demo&run={second}")
    assert page.inner_text("#headline").startswith("3 people have active accounts and paid seats")
    assert page.inner_text(".recorded") == "Recorded run. Not live data."
    assert "180 people" in page.inner_text(".ledgers")
    assert page.inner_text(".compare-intro").startswith("Every person is looked up in all three.")
    assert page.text_content("#venn-title") == "People by region across the three ledgers"
    notes = page.locator(".notes li").all_inner_texts()
    assert notes[0] == "Lantern Chat invoices 3 more seats than it assigns (178 invoiced, 175 assigned)."
    money = page.inner_text(".money")
    assert "3 seats paid for nobody named" in money and "no person to match" in money
    text = page.inner_text("body")
    assert not CLOUD_WORDS.search(text), CLOUD_WORDS.search(text)
    assert_axe_clean(page)


def test_the_app_switch_offers_vampires_live_vampires_demo_ghosts_demo_and_own_build_demo(
    page: Any, base_url: str
) -> None:
    open_page(page, base_url, "?app=ghosts-demo")
    options = page.locator("#app-select option").all_inner_texts()
    assert options == ["Cloud account", "Cloud account demo", "Staff access demo company", "Night Audit's own build"]
    assert page.locator("#app-select").input_value() == "ghosts-demo"


def test_the_old_demo_link_still_opens_the_vampires_demo(page: Any, base_url: str) -> None:
    open_page(page, base_url, "?demo=1")
    assert page.locator("#app-select").input_value() == "vampires-demo"
    assert page.inner_text("#headline")


def test_an_opened_ghost_states_its_condition_and_shows_its_evidence(page: Any, base_url: str) -> None:
    _, second = ghost_nights()
    open_page(page, base_url, f"?app=ghosts-demo&run={second}")
    key = "j.marsh@hollowpines.com"
    row = page.locator(".row", has=page.locator(f'.row-head[data-key="{key}"]'))
    assert row.locator(".row-explain").inner_text() == (
        "Left on 2026-09-12. Account still active, last sign-in 2026-10-30. Seats in Belfry CRM and Crypt Docs."
    )
    row.locator(".row-head").click()
    page.wait_for_selector("table.evidence")
    context = row.locator("dl.context").inner_text()
    assert "left on" in context.lower() and "2026-09-12" in context
    text = row.inner_text()
    # The plain label comes first; the Halloween name is only the tag after it.
    assert text.index("Account and paid seat, not on staff") < text.index("Ghost")
    assert_axe_clean(page)


def test_the_review_sheet_is_a_download(page: Any, base_url: str) -> None:
    first, _ = ghost_nights()
    open_page(page, base_url, f"?app=ghosts-demo&run={first}")
    links = page.locator(".downloads a")
    assert links.all_inner_texts() == ["Review sheet (CSV)", "Review sheet (HTML)"]
    with page.expect_download() as info:
        links.first.click()
    download = info.value
    assert download.suggested_filename == "review.csv"
    content = Path(download.path()).read_text("utf-8")
    assert content.startswith("person,region,region_code,") and "j.marsh@hollowpines.com" in content
    assert page.inner_text(".review-state") == "No decision recorded for this night yet."
    assert page.locator(".row-decision").count() == 0
    assert_axe_clean(page)


def test_recorded_decisions_show_with_their_reviewer_and_date(page: Any, base_url: str) -> None:
    _, second = ghost_nights()
    open_page(page, base_url, f"?app=ghosts-demo&run={second}")
    assert page.inner_text(".review-state").startswith("3 decisions recorded by Dana Okafor, IT manager on 2026-11-05.")
    decided = {
        page.locator(".row", has=page.locator(f'.row-head[data-key="{key}"]')).locator(".row-decision").inner_text()
        for key in ("j.marsh@hollowpines.com", "p.lindqvist@hollowpines.com", "svc-reporting@hollowpines.com")
    }
    assert decided == {
        "Decision: revoke by Dana Okafor, IT manager on 2026-11-05",
        "Decision: investigate by Dana Okafor, IT manager on 2026-11-05",
    }
    assert page.locator(".row-decision").count() == 3
    assert_axe_clean(page)


@pytest.mark.parametrize("width", [390])
def test_the_ghosts_page_fits_a_phone(browser: Any, base_url: str, width: int) -> None:
    _, second = ghost_nights()
    page = new_page(browser, width=width, height=844)
    open_page(page, base_url, f"?app=ghosts-demo&run={second}")
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert_axe_clean(page)
    page.context.close()

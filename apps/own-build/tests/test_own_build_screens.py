"""The own-build page in headless Chromium, through the skeleton's harness and its axe checks (ui-kit Req 10, 12).

The page is the static demo shipped in the build (``dist/demo/own-build/``), which is what a visitor opens. The server
is the skeleton's own ``create_app`` over an empty runs folder, serving the built front end; the page set-up, the page
opener and the axe check come from the skeleton's ``e2e.browser_kit``.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import uvicorn
from e2e.browser_kit import DIST, assert_axe_clean, new_page, open_page
from nightaudit.api import create_app
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e
OWN = DIST / "demo" / "own-build"
#: Words that belong to the other two apps. In the headline, notes and ledger sentences none of them may appear (the rows
#: name files, and some paths hold "ghosts" or "vampires").
FOREIGN = ("resource", "vampire", "ghost", "person", "people", "seat", "account")
TEXT_OF_ALL = "els => els.map((e) => e.textContent)"


def in_chromium(width: int = 1440, height: int = 1000) -> Callable[[Callable[[Any, str], None]], Callable[[str], None]]:
    """Run a test body in headless Chromium, on a page made by the skeleton's ``new_page``.

    Playwright's sync API allows one session per thread, and the skeleton's ``browser`` fixture already holds the main
    thread's when the whole suite runs. So the body runs in its own thread with its own session, and anything it raises
    is raised in the test.
    """

    def decorate(body: Callable[[Any, str], None]) -> Callable[[str], None]:
        def test(own_url: str) -> None:
            failure: list[BaseException] = []

            def work() -> None:
                try:
                    with sync_playwright() as playwright:
                        try:
                            chromium = playwright.chromium.launch(headless=True)
                        except Exception as exc:  # noqa: BLE001 - a missing browser is a setup problem
                            failure.append(pytest.skip.Exception(f"Chromium is not installed ({exc})"))
                            return
                        page = new_page(chromium, width=width, height=height)
                        try:
                            body(page, own_url)
                        finally:
                            page.context.close()
                            chromium.close()
                except BaseException as exc:  # noqa: BLE001 - raised again in the test's own thread
                    failure.append(exc)

            thread = threading.Thread(target=work)
            thread.start()
            thread.join()
            if failure:
                raise failure[0]

        test.__name__ = body.__name__
        test.__doc__ = body.__doc__
        return test

    return decorate


@pytest.fixture(scope="module")
def own_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if not (DIST / "index.html").exists():
        pytest.skip("build the front end first: npm run build in skeleton/web")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    port = sock.getsockname()[1]
    app = create_app(tmp_path_factory.mktemp("no-runs"), static_dir=DIST)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


def night() -> str:
    runs = json.loads((OWN / "runs.json").read_text("utf-8")) if (OWN / "runs.json").exists() else []
    if len(runs) != 1:
        pytest.skip("build the demos and the front end: uv run python scripts/build_demos.py; npm run build")
    return str(runs[0]["run_id"])


@in_chromium()
def test_the_page_reads_in_files_and_states_the_allocation(page: Any, url: str) -> None:
    open_page(page, url, f"?app=own-build-demo&run={night()}")
    sentences = page.locator(".headline-lead, .headline-line").all_inner_texts()
    assert sentences == [
        "45 files were built with Kiro and no spec names them.",
        "8 files were worked on by Kiro, named by no spec, and are gone.",
        "36 files were written by hand or generated: no spec names them and no Kiro session touched them.",
        "3 files were promised by a spec and never built.",
    ]
    notes = page.locator(".notes li").all_inner_texts()
    assert notes[0].startswith("Credits per file are an allocation:") and "not a measurement" in notes[0]
    assert page.text_content("#venn-title") == "Files by region across the three ledgers"
    ledgers = page.inner_text(".ledgers")
    assert "SPECS" in ledgers.upper() and "376 files" in ledgers and "229 files" in ledgers
    assert "allocation chosen for this audit, not a measurement" in ledgers
    text = (page.inner_text(".lede") + " " + ledgers).lower()
    assert not [w for w in FOREIGN if w in text], [w for w in FOREIGN if w in text]
    assert_axe_clean(page)


@in_chromium()
def test_the_app_switch_lists_the_own_build_demo_last_and_selects_it(page: Any, url: str) -> None:
    open_page(page, url, "?app=own-build-demo")
    options = page.locator("#app-select option").all_inner_texts()
    assert options[-1] == "Night Audit's own build" and "Vampires" in options and "Ghosts demo company" in options
    assert page.locator("#app-select").input_value() == "own-build-demo"


@in_chromium()
def test_the_venn_names_the_regions_in_words_and_counts_them(page: Any, url: str) -> None:
    open_page(page, url, f"?app=own-build-demo&run={night()}")
    names = page.locator("svg.venn .venn-name").evaluate_all(TEXT_OF_ALL)
    joined = " ".join(names).upper()
    for words in ("PROMISED BY A", "SPEC'D, NO KIRO", "BUILT, SPEC'D, GONE", "WRITTEN BY HAND"):
        assert words in joined, words
    counts = page.locator("svg.venn .venn-count").evaluate_all(TEXT_OF_ALL)
    assert sorted(counts, key=int) == ["0", "3", "8", "36", "45", "119", "176"]


@in_chromium()
def test_an_opened_file_states_its_condition_and_shows_its_evidence(page: Any, url: str) -> None:
    open_page(page, url, f"?app=own-build-demo&run={night()}")
    row = page.locator(".row", has=page.locator('.row-head[data-key=".devcontainer/devcontainer.json"]'))
    assert row.locator(".row-explain").inner_text() == (
        "Tracked by git. Kiro sessions that touched it: 2. No spec names this file."
    )
    row.locator(".row-head").click()
    page.wait_for_selector("table.evidence")
    assert "3.2145" in row.inner_text()
    assert_axe_clean(page)


@in_chromium()
def test_a_promise_never_built_shows_the_spec_that_made_it(page: Any, url: str) -> None:
    open_page(page, url, f"?app=own-build-demo&run={night()}")
    row = page.locator(".row", has=page.locator('.row-head[data-key="demo/build.py"]'))
    assert row.locator(".row-explain").inner_text() == (
        "Named by three-way-match. Git does not track it at the recorded commit "
        "and no Kiro session in the export touched it."
    )


@in_chromium(width=390, height=844)
def test_the_own_build_page_fits_a_phone(page: Any, url: str) -> None:
    open_page(page, url, f"?app=own-build-demo&run={night()}")
    page.locator(".row-head").first.click()
    page.wait_for_selector("table.evidence")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert_axe_clean(page)

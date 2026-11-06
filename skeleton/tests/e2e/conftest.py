"""Browser test fixtures (ui-kit Req 12): headless Chromium against a local server on a free port.

Needs the Python ``playwright`` package with Chromium (``uv add --dev playwright`` and
``uv run playwright install chromium``) and a built front end (``npm run build`` in ``skeleton/web``). Without them the
browser tests skip and say why.

The server runs ``create_app`` over a temporary runs folder holding the three demo nights, a clean night, a night with
hostile ledger values and a night with twelve findings. Its socket is bound to port 0 and listening before the server
thread starts, so the first request waits in the backlog: no polling and no sleeps.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from nightaudit.api import create_app
from nightaudit.runner import run_control

from e2e.browser_kit import DEMO, DIST, HOSTILE_KEY, HOSTILE_NAME, Nights, new_page

HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None

LEDGERS = """\
ledgers:
  intended: {key_field: id, normalisers: [strip], connector: {type: csv, path: intended.csv}}
  observed: {key_field: id, normalisers: [strip], connector: {type: csv, path: observed.csv}}
  billed: {key_field: resource, normalisers: [strip], connector: {type: csv, path: billed.csv}}
"""


def _csv(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _control(folder: Path, control_id: str, intended: str, observed: str, billed: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "control.yaml").write_text(f"id: {control_id}\ntitle: {control_id}\napp: vampires\n{LEDGERS}", "utf-8")
    (folder / "intended.csv").write_text("row_id,id\n" + intended, "utf-8")
    (folder / "observed.csv").write_text("row_id,id,ts,Name\n" + observed, "utf-8")
    (folder / "billed.csv").write_text("row_id,resource,amount\n" + billed, "utf-8")
    return folder / "control.yaml"


@pytest.fixture(scope="session")
def nights(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Nights]:
    if not HAS_PLAYWRIGHT:
        pytest.skip("install the browser driver: uv add --dev playwright && uv run playwright install chromium")
    if not (DIST / "index.html").exists():
        pytest.skip("build the front end first: npm run build in skeleton/web")
    runs = tmp_path_factory.mktemp("runs")
    demo = [
        run_control(DEMO / f"night-{n}" / "control.yaml", runs, run_time=datetime(2026, 11, 3 + n, 2, tzinfo=UTC))
        .run_id
        for n in (1, 2, 3)
    ]
    work = tmp_path_factory.mktemp("controls")
    old = "2026-09-01T00:00:00Z"
    clean = run_control(
        _control(work / "clean", "clean-account", "i1,a\ni2,b\n", f"o1,a,{old},\no2,b,{old},\n",
                 "b1,a,1.00\nb2,b,2.50\n"),
        runs, run_time=datetime(2026, 11, 7, 2, tzinfo=UTC),
    ).run_id
    hostile = run_control(
        _control(work / "hostile", "hostile-account", "i1,a\n",
                 f"o1,a,{old},\no2,{_csv(HOSTILE_KEY)},{old},{_csv(HOSTILE_NAME)}\n", "b1,a,1.00\n"),
        runs, run_time=datetime(2026, 11, 8, 2, tzinfo=UTC),
    ).run_id
    observed = "".join(f"o{n},k{n:02d},{old},\n" for n in range(12))
    billed = "".join(f"b{n},k{n:02d},{n}.25\n" for n in range(6))
    twelve = run_control(_control(work / "twelve", "twelve-account", "", observed, billed), runs,
                         run_time=datetime(2026, 11, 9, 2, tzinfo=UTC)).run_id
    # Two nights of one control: the second night lays the first night's Poltergeist to rest.
    rest = _control(work / "rest", "rest-account", "i1,a\n", f"o1,a,{old},\no2,gone-soon,{old},\n", "b1,a,1.00\n")
    run_control(rest, runs, run_time=datetime(2026, 11, 10, 2, tzinfo=UTC))
    (work / "rest" / "observed.csv").write_text(f"row_id,id,ts,Name\no1,a,{old},\n", "utf-8")
    rested = run_control(rest, runs, run_time=datetime(2026, 11, 12, 2, tzinfo=UTC)).run_id
    return runs, Nights(demo=demo, clean=clean, hostile=hostile, twelve=twelve, rested=rested)


@pytest.fixture(scope="session")
def base_url(nights: tuple[Path, Nights]) -> Iterator[str]:
    runs, _ = nights
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(runs, static_dir=DIST), log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


@pytest.fixture(scope="session")
def browser(nights: tuple[Path, Nights]) -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            chromium = p.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - a missing browser is a setup problem, not a test failure
            pytest.skip(f"Chromium is not installed: uv run playwright install chromium ({exc})")
        yield chromium
        chromium.close()


@pytest.fixture()
def page(browser: Any) -> Iterator[Any]:
    p = new_page(browser)
    yield p
    p.context.close()

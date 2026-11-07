"""No text in the repository, the built demo, ``examples/`` or a page the app serves uses the words in ``LABELS``.

A demo is called a demo, a recorded run a recorded run, and an example value an example value. This file is the one
place the words appear, as the pattern below. ``casebook/heldout/`` is sealed and not read.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nightaudit.api import create_app
from nightaudit.runner import run_control

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
SEALED = "casebook/heldout/"
BUILT = (ROOT / "skeleton/web/public/demo", ROOT / "examples", ROOT / "skeleton/web/dist")
DIST = ROOT / "skeleton/web/dist"
DEMO = ROOT / "apps/vampires/demo"
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".ico", ".pdf", ".zip", ".gz", ".mp4"}

LABELS = re.compile(r"synthetic|fictional|invented|made[- ]up|fake", re.IGNORECASE)


def labelled_lines(text: str) -> list[str]:
    """Each line of *text* that holds one of the words, as ``<line>: <text>``."""
    return [f"{n}: {line.strip()[:120]}" for n, line in enumerate(text.splitlines(), start=1) if LABELS.search(line)]


def _text(file: Path) -> str | None:
    if file.suffix.lower() in BINARY or not file.is_file():
        return None
    try:
        return file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _repository_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    built = [f.relative_to(ROOT).as_posix() for folder in BUILT if folder.is_dir() for f in folder.rglob("*")]
    return sorted({p for p in [*out.splitlines(), *built] if not p.startswith(SEALED) and p != SELF})


def test_no_repository_built_demo_or_example_file_uses_a_listed_word() -> None:
    found: dict[str, list[str]] = {}
    for path in _repository_files():
        text = _text(ROOT / path)
        if text is not None and (lines := labelled_lines(text)):
            found[path] = lines
    assert found == {}


def test_no_page_the_app_serves_uses_a_listed_word(tmp_path: Path) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("build the front end first: npm run build in skeleton/web")
    runs = tmp_path / "runs"
    ids = [
        run_control(
            DEMO / f"night-{n}" / "control.yaml", runs, run_time=datetime(2026, 11, 3 + n, 2, tzinfo=UTC)
        ).run_id
        for n in (1, 2, 3)
    ]
    http = TestClient(create_app(runs, static_dir=DIST))
    index = http.get("/")
    assert index.status_code == 200
    assets = re.findall(r'(?:src|href)="\.?(/assets/[^"]+\.(?:js|css))"', index.text)
    assert assets, "the page links no script or style"
    served = sorted(
        {*assets, *(f"/assets/{f.name}" for f in (DIST / "assets").iterdir() if f.suffix in {".js", ".css"})}
    )
    paths = ["/", *served, "/api/runs", "/api/latest"]
    paths += [p for run_id in ids for p in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/report.html")]
    found: dict[str, list[str]] = {}
    for path in paths:
        response = http.get(path)
        assert response.status_code == 200, path
        if lines := labelled_lines(response.text):
            found[path] = lines
    assert found == {}


def _each_word() -> list[str]:
    """Every spelling the pattern names, read from the pattern itself so the words are written only once."""
    words: list[str] = []
    for alternative in LABELS.pattern.split("|"):
        words += [alternative.replace("[- ]", sep) for sep in "- "] if "[- ]" in alternative else [alternative]
    return words


@pytest.mark.parametrize("word", _each_word())
def test_the_scan_sees_each_word_in_any_case(word: str) -> None:
    assert labelled_lines(f"a {word.upper()} account") != []
    assert labelled_lines(f"a {word.title()}Clock") != []


@pytest.mark.parametrize("line", ["Recorded run. Not live data.", "a demo account (111122223333)", "example values"])
def test_the_scan_passes_the_words_a_demo_uses(line: str) -> None:
    assert labelled_lines(line) == []

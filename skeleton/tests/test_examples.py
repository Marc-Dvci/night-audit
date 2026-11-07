"""``examples/vampires-night/`` is one finished demo night, copied from the committed demo by
``scripts/build_examples.py``. It must stay the same bytes as the demo, and its pack must verify against its page."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from nightaudit.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_examples", ROOT / "scripts" / "build_examples.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_example_night_is_the_committed_demo_byte_for_byte() -> None:
    pairs = _script().copies()
    assert len(pairs) == 7
    for source, copy in pairs:
        assert copy.exists(), f"{copy} is missing: run uv run python scripts/build_examples.py"
        assert copy.read_bytes() == source.read_bytes(), f"{copy} differs from {source}"
    names = {
        p.relative_to(ROOT / "examples" / "vampires-night").as_posix()
        for p in (ROOT / "examples" / "vampires-night").rglob("*")
        if p.is_file()
    }
    assert names == {c.relative_to(ROOT / "examples" / "vampires-night").as_posix() for _, c in pairs}


@pytest.mark.integration
def test_the_example_night_verifies_against_its_page(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["verify", str(ROOT / "examples" / "vampires-night")]) == 0
    out = capsys.readouterr().out
    assert "the page matches the evidence" in out

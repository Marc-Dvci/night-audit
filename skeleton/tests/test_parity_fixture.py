"""The fixture the TypeScript tests compare against comes from the current Python code (ui-kit Req 6.4).

Regenerate with ``uv run pytest skeleton/tests/test_parity_fixture.py --update-parity-fixture`` (or
``uv run python scripts/write_parity_fixture.py``).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("write_parity_fixture", ROOT / "scripts" / "write_parity_fixture.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_parity_fixture_is_current(request: pytest.FixtureRequest) -> None:
    writer = _writer()
    expected: str = writer.build()
    if request.config.getoption("--update-parity-fixture"):
        writer.main()
    assert writer.FIXTURE.exists(), "run with --update-parity-fixture to write it"
    assert writer.FIXTURE.read_text(encoding="utf-8") == expected


def test_the_fixture_covers_failure_at_a_row_and_at_the_manifest() -> None:
    data = json.loads(_writer().build())
    verdicts = {v["name"]: v["verdict"] for v in data["pack"]["variants"]}
    assert verdicts["untouched"]["ok"]
    assert verdicts["change one byte"]["failed_row"] is not None
    assert verdicts["last row removed"] == {**verdicts["last row removed"], "ok": False, "failed_row": None}
    passing = [name for name, v in verdicts.items() if v["ok"]]
    assert passing == ["untouched", "no trailing newline"]
    texts = [v["jsonl"] for v in data["pack"]["variants"]]
    assert len(set(texts)) == len(texts), "every variant changes the pack"

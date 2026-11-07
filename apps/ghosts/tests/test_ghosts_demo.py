"""The recorded demo ships everything the UI kit reads, in Ghosts' words (Req 7.2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import RunResult
from nightaudit.report import run_numbers

DEMO = Path(__file__).resolve().parents[1] / "demo"


def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ghosts_demo_build", DEMO / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_a_fresh_build_has_every_file_and_its_evidence_verifies(tmp_path: Path) -> None:
    build = builder()
    run_id = build.build(tmp_path / "out", tmp_path / "runs")
    out = tmp_path / "out"
    (summary,) = json.loads((out / "runs.json").read_text("utf-8"))
    assert summary["run_id"] == run_id and summary["findings"] == 8 and summary["app"] == "ghosts"
    folder = out / run_id
    for name in build.RUN_FILES:
        assert (folder / name).exists(), name
    document = json.loads((folder / "run.json").read_text("utf-8"))
    view = document.pop("view")
    run = RunResult.model_validate(document)
    verdict = verify_evidence_pack(folder)
    assert verdict.ok, verdict.detail
    assert verdict.final_hash == run.evidence_chain_hash
    assert view["finding_count"] == 8
    assert run.ui.title == "Ghosts" and run.ui.noun.plural == "people"
    assert view["headline"].startswith("3 Ghosts have active accounts and paid seats but are not on the HR roster")
    assert "Recorded run of a synthetic account" in (folder / "report.html").read_text("utf-8")
    assert run_numbers(run)
    entry = json.loads((out / "apps.entry.json").read_text("utf-8"))
    assert entry == {"name": "ghosts-demo", "title": "Hollow Pines demo company", "mode": "demo",
                     "base": "demo/ghosts/"}


def test_the_committed_demo_is_the_builders_output(tmp_path: Path) -> None:
    build = builder()
    build.build(tmp_path / "out", tmp_path / "runs")
    assert files(build.OUT) == files(tmp_path / "out"), "run: uv run python apps/ghosts/demo/build.py"

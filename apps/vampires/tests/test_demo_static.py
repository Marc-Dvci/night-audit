"""The static demo ships everything the UI kit reads (ui-kit Req 6.5, 7.2, 8.1, 8.3; skeleton Req 10.8).

These tests read the files written by ``uv run python scripts/build_demos.py``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import RunResult
from nightaudit.report import run_numbers

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "skeleton" / "web" / "public"
DEMO = PUBLIC / "demo" / "vampires"
SUMMARIES = json.loads((DEMO / "runs.json").read_text("utf-8")) if (DEMO / "runs.json").exists() else []


def builder() -> ModuleType:
    path = ROOT / "apps" / "vampires" / "demo" / "build.py"
    spec = importlib.util.spec_from_file_location("vampires_demo_build", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_the_demo_is_built() -> None:
    assert len(SUMMARIES) == 3, "run: uv run python scripts/build_demos.py"
    assert [s["run_time"] for s in SUMMARIES] == sorted((s["run_time"] for s in SUMMARIES), reverse=True)


def test_apps_json_lists_vampires_live_vampires_demo_and_ghosts_demo() -> None:
    apps = json.loads((PUBLIC / "apps.json").read_text("utf-8"))
    assert [(a["name"], a["mode"], a["base"]) for a in apps] == [
        ("vampires", "live", "api/"),
        ("vampires-demo", "demo", "demo/vampires/"),
        ("ghosts-demo", "demo", "demo/ghosts/"),
        ("own-build-demo", "demo", "demo/own-build/"),
    ]
    assert all(set(a) == {"name", "title", "mode", "base"} for a in apps)
    for app in apps:
        if app["mode"] == "demo":
            assert (PUBLIC / app["base"] / "runs.json").exists(), app["name"]


def test_the_builder_writes_only_its_own_folder(tmp_path: Path) -> None:
    build = builder()
    with pytest.raises(ValueError, match="may only write"):
        build.build(build.DEMO_ROOT / "ghosts", tmp_path / "runs")
    with pytest.raises(ValueError, match="may only write"):
        build.build(build.DEMO_ROOT, tmp_path / "runs")
    assert (build.DEMO_ROOT / "ghosts" / "runs.json").exists()


def test_the_committed_demo_is_the_builders_output(tmp_path: Path) -> None:
    builder().build(tmp_path / "out", tmp_path / "runs")
    assert files(DEMO) == files(tmp_path / "out"), "run: uv run python scripts/build_demos.py"


@pytest.mark.parametrize("summary", SUMMARIES, ids=lambda s: s["run_id"])
def test_each_demo_night_has_its_files_and_its_evidence_verifies(summary: dict[str, object]) -> None:
    folder = DEMO / str(summary["run_id"])
    for name in ("run.json", "evidence.jsonl", "manifest.json", "report.html", "evidence.zip"):
        assert (folder / name).exists(), name
    document = json.loads((folder / "run.json").read_text("utf-8"))
    view = document.pop("view")
    assert document.pop("downloads") == []
    assert "decisions" not in document
    run = RunResult.model_validate(document)
    verdict = verify_evidence_pack(folder)
    assert verdict.ok, verdict.detail
    assert verdict.final_hash == run.evidence_chain_hash
    assert view["finding_count"] == summary["findings"]
    assert "new_findings" in summary
    assert run.ui.title == "Vampires"
    report = (folder / "report.html").read_text("utf-8")
    assert "Recorded run of synthetic data" in report
    assert run_numbers(run)

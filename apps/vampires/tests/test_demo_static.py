"""The static demo ships everything the UI kit reads (ui-kit Req 6.5, 7.2, 8.1, 8.3).

These tests read the files written by ``uv run python apps/vampires/demo/build.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import RunResult
from nightaudit.report import run_numbers

PUBLIC = Path(__file__).resolve().parents[3] / "skeleton" / "web" / "public"
DEMO = PUBLIC / "demo"
SUMMARIES = json.loads((DEMO / "runs.json").read_text("utf-8")) if (DEMO / "runs.json").exists() else []


def test_the_demo_is_built() -> None:
    assert len(SUMMARIES) == 3, "run: uv run python apps/vampires/demo/build.py"
    assert [s["run_time"] for s in SUMMARIES] == sorted((s["run_time"] for s in SUMMARIES), reverse=True)


def test_apps_json_offers_the_live_api_and_the_recorded_demo() -> None:
    apps = json.loads((PUBLIC / "apps.json").read_text("utf-8"))
    assert {(a["mode"], a["base"]) for a in apps} == {("live", "api/"), ("demo", "demo/")}
    assert all(set(a) == {"name", "title", "mode", "base"} for a in apps)


@pytest.mark.parametrize("summary", SUMMARIES, ids=lambda s: s["run_id"])
def test_each_demo_night_has_its_files_and_its_evidence_verifies(summary: dict[str, object], tmp_path: Path) -> None:
    folder = DEMO / str(summary["run_id"])
    for name in ("run.json", "evidence.jsonl", "manifest.json", "report.html", "evidence.zip"):
        assert (folder / name).exists(), name
    document = json.loads((folder / "run.json").read_text("utf-8"))
    view = document.pop("view")
    run = RunResult.model_validate(document)
    verdict = verify_evidence_pack(folder)
    assert verdict.ok, verdict.detail
    assert verdict.final_hash == run.evidence_chain_hash
    assert view["finding_count"] == summary["findings"]
    assert "new_findings" in summary
    assert run.ui.title == "Vampires"
    report = (folder / "report.html").read_text("utf-8")
    assert "Recorded run of a synthetic account" in report
    assert run_numbers(run)

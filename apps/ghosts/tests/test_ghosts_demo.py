"""The recorded demo ships everything the UI kit reads, in Ghosts' words (Req 7.2; skeleton Req 10.6-10.8)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from ghosts_testkit import as_windows
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import RunResult
from nightaudit.report import run_numbers

DEMO = Path(__file__).resolve().parents[1] / "demo"
PUBLIC_DEMO = Path(__file__).resolve().parents[3] / "skeleton" / "web" / "public" / "demo" / "ghosts"


def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ghosts_demo_build", DEMO / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def document(folder: Path) -> tuple[RunResult, dict[str, object], dict[str, object]]:
    data = json.loads((folder / "run.json").read_text("utf-8"))
    view = data.pop("view")
    extra = {k: data.pop(k) for k in ("downloads", "decisions") if k in data}
    return RunResult.model_validate(data), view, extra


def test_a_fresh_build_has_two_nights_one_without_and_one_with_decisions(tmp_path: Path) -> None:
    build = builder()
    first, second = build.build(tmp_path / "out", tmp_path / "runs")
    out = tmp_path / "out"
    summaries = json.loads((out / "runs.json").read_text("utf-8"))
    assert [s["run_id"] for s in summaries] == [second, first]
    assert all(s["findings"] == 8 and s["app"] == "ghosts" for s in summaries)
    for run_id in (first, second):
        folder = out / run_id
        for name in build.RUN_FILES:
            assert (folder / name).exists(), name
        run, view, extra = document(folder)
        verdict = verify_evidence_pack(folder)
        assert verdict.ok, verdict.detail
        assert verdict.final_hash == run.evidence_chain_hash
        assert view["finding_count"] == 8
        assert run.ui.title == "Ghosts" and run.ui.noun.plural == "people"
        assert str(view["headline"]).startswith("3 Ghosts have active accounts and paid seats but are not on the HR")
        assert "Recorded run. Not live data." in (folder / "report.html").read_text("utf-8")
        assert run_numbers(run)
        assert extra["downloads"] == [
            {"label": "Review sheet (CSV)", "file": "review.csv"},
            {"label": "Review sheet (HTML)", "file": "review.html"},
        ]
        assert "Lantern Chat invoices 3 more seats than it assigns (178 invoiced, 175 assigned)." in [
            n.text for n in run.notes
        ]

    _, _, quiet = document(out / first)
    assert "decisions" not in quiet and not (out / first / "decisions.jsonl").exists()
    _, _, decided = document(out / second)
    assert decided["decisions"] == {
        "ok": True,
        "detail": "evidence verifies; 3 decisions verify",
        "rows": [
            {
                "key": key,
                "region_code": code,
                "decision": decision,
                "decision_date": "2026-11-05",
                "reviewer": "Dana Okafor, IT manager",
            }
            for key, code, decision in (
                ("j.marsh@hollowpines.com", "OB", "revoke"),
                ("p.lindqvist@hollowpines.com", "OB", "revoke"),
                ("svc-reporting@hollowpines.com", "O", "investigate"),
            )
        ],
    }
    assert (out / second / "decisions.jsonl").exists()
    assert build.APP_ENTRIES == [
        {"name": "ghosts-demo", "title": "Ghosts demo company", "mode": "demo", "base": "demo/ghosts/"}
    ]


def test_the_committed_demo_is_the_builders_output(tmp_path: Path) -> None:
    builder().build(tmp_path / "out", tmp_path / "runs")
    assert files(PUBLIC_DEMO) == files(tmp_path / "out"), "run: uv run python scripts/build_demos.py"


def test_the_demo_has_the_same_bytes_when_the_platform_translates_newlines(tmp_path: Path) -> None:
    """The first CI run failed here: Windows wrote CRLF into ``manifest.json`` (and so into ``evidence.zip``)."""
    builder().build(tmp_path / "plain", tmp_path / "plain-runs")
    with as_windows():
        builder().build(tmp_path / "windows", tmp_path / "windows-runs")
    assert files(tmp_path / "windows") == files(tmp_path / "plain")


def test_the_review_sheet_is_crlf_in_every_line_and_the_html_has_none(tmp_path: Path) -> None:
    builder().build(tmp_path / "out", tmp_path / "runs")
    for folder in (tmp_path / "out").iterdir():
        if not folder.is_dir():
            continue
        sheet = (folder / "review.csv").read_bytes()
        assert sheet.count(b"\r\n") == sheet.count(b"\n") > 1, folder.name
        assert b"\r\r" not in sheet
        assert b"\r" not in (folder / "review.html").read_bytes()

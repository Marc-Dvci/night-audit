"""The recorded demo night: Night Audit's own build, in the UI kit's files and in this app's words."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import LedgerName, RunResult
from nightaudit.report import run_numbers
from own_build.connectors import KiroFiles, SpecFiles, TrackedFiles
from own_build_testkit import APP, DATA, as_windows

DEMO = APP / "demo"
PUBLIC_DEMO = APP.parents[1] / "skeleton" / "web" / "public" / "demo" / "own-build"


def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("own_build_demo_build", DEMO / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def document(folder: Path) -> tuple[RunResult, dict[str, object]]:
    data = json.loads((folder / "run.json").read_text("utf-8"))
    view = data.pop("view")
    for extra in ("downloads", "decisions"):
        data.pop(extra, None)
    return RunResult.model_validate(data), view


def test_a_fresh_build_has_one_night_that_verifies_and_speaks_about_files(tmp_path: Path) -> None:
    build = builder()
    [run_id] = build.build(tmp_path / "out", tmp_path / "runs")
    out = tmp_path / "out"
    [summary] = json.loads((out / "runs.json").read_text("utf-8"))
    assert summary["run_id"] == run_id and summary["app"] == "own-build" and summary["complete"] is True
    folder = out / run_id
    for name in build.RUN_FILES:
        assert (folder / name).exists(), name
    run, view = document(folder)
    verdict = verify_evidence_pack(folder)
    assert verdict.ok, verdict.detail
    assert verdict.final_hash == run.evidence_chain_hash
    assert run.ui.title == "Own build" and run.ui.noun.plural == "files"
    assert view["headline_sentences"] == [
        "49 files were built with Kiro and no spec names them.",
        "5 files were worked on by Kiro, named by no spec, and are gone.",
        "42 files were written by hand or generated: no spec names them and no Kiro session touched them.",
        "3 files were promised by a spec and never built.",
    ]
    assert run_numbers(run)
    assert build.APP_ENTRIES == [
        {"name": "own-build-demo", "title": "Night Audit's own build", "mode": "demo", "base": "demo/own-build/"}
    ]


def test_the_recorded_night_holds_these_region_counts(tmp_path: Path) -> None:
    """The record of what the control found in this repository at the recorded commit."""
    builder().build(tmp_path / "out", tmp_path / "runs")
    [folder] = [p for p in (tmp_path / "out").iterdir() if p.is_dir()]
    run, _ = document(folder)
    counts = {code: summary.key_count for code, summary in sorted(run.region_summaries.items())}
    assert counts == {"B": 5, "I": 3, "IO": 119, "IOB": 180, "O": 42, "OB": 49}
    assert str(run.billed_total) == "1072.7314"
    assert run.pending_keys == [] and run.unkeyed == [] and run.ledger_errors == {}


def test_the_committed_demo_is_the_builders_output(tmp_path: Path) -> None:
    builder().build(tmp_path / "out", tmp_path / "runs")
    assert files(PUBLIC_DEMO) == files(tmp_path / "out"), "run: uv run python scripts/build_demos.py own-build"


def test_the_demo_is_built_from_one_commit_and_names_it() -> None:
    commits = {
        row["commit"]
        for name in ("tracked-files.csv", "spec-files.csv")
        for row in csv.DictReader((DATA / name).open(encoding="utf-8", newline=""))
    }
    assert len(commits) == 1 and len(next(iter(commits))) == 40


def test_the_recorded_files_load_through_the_connectors() -> None:
    kwargs = {"base_dir": DATA}
    specs = SpecFiles(ledger=LedgerName.intended, path="spec-files.csv", **kwargs).fetch()
    tracked = TrackedFiles(ledger=LedgerName.observed, path="tracked-files.csv", **kwargs).fetch()
    kiro = KiroFiles(ledger=LedgerName.billed, files="kiro-files.csv", sessions="kiro-sessions.csv", **kwargs).fetch()
    assert (len(specs), len(tracked), len(kiro)) == (302, 390, 234)


def test_the_export_holds_no_prompt_and_no_reply() -> None:
    """Only paths, ids, model names, times and credits: the columns are the whole content."""
    for name, columns in (
        ("kiro-files.csv", ["file", "session", "credit_share", "started"]),
        ("kiro-sessions.csv", ["session", "started", "model", "files_touched", "credits"]),
    ):
        with (DATA / name).open(encoding="utf-8", newline="") as handle:
            assert next(csv.reader(handle)) == columns


def test_the_demo_has_the_same_bytes_when_the_platform_translates_newlines(tmp_path: Path) -> None:
    builder().build(tmp_path / "plain", tmp_path / "plain-runs")
    with as_windows():
        builder().build(tmp_path / "windows", tmp_path / "windows-runs")
    assert files(tmp_path / "windows") == files(tmp_path / "plain")

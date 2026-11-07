"""Contract tests: each own-build connector loads its recorded fixture, and a damaged export is refused."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from nightaudit.connectors import Connector
from nightaudit.models import LedgerName
from own_build.connectors import KiroFiles, SpecFiles, TrackedFiles
from own_build_testkit import FIXTURES, run_in


def specs(base: Path = FIXTURES) -> SpecFiles:
    return SpecFiles(ledger=LedgerName.intended, base_dir=base, path="spec-files.csv")


def tracked(base: Path = FIXTURES) -> TrackedFiles:
    return TrackedFiles(ledger=LedgerName.observed, base_dir=base, path="tracked-files.csv")


def kiro(base: Path = FIXTURES) -> KiroFiles:
    return KiroFiles(ledger=LedgerName.billed, base_dir=base, files="kiro-files.csv", sessions="kiro-sessions.csv")


def fixture_copy(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURES, tmp_path / "data")
    return tmp_path / "data"


def edit(folder: Path, name: str, old: str, new: str) -> None:
    path = folder / name
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.parametrize("connector", [specs(), tracked(), kiro()], ids=["specs", "tracked", "kiro"])
def test_every_connector_is_read_only(connector: Connector) -> None:
    assert connector.read_only is True


def test_each_connector_serves_its_own_ledger() -> None:
    assert (specs().ledger, tracked().ledger, kiro().ledger) == (
        LedgerName.intended,
        LedgerName.observed,
        LedgerName.billed,
    )


def test_spec_rows_fold_into_one_record_per_file_naming_every_spec_and_document() -> None:
    records = specs().fetch()
    assert [r.raw_key for r in records] == [
        "deploy/stack.yaml",
        "src/match.py",
        "src/old_report.py",
        "src/report.py",
        "tests/fixtures/sample.csv",
    ]
    match = next(r for r in records if r.raw_key == "src/match.py")
    assert match.ledger == LedgerName.intended and match.row_id == "spec:src/match.py"
    assert match.attrs == {"specs": "alpha", "documents": "alpha/design.md, alpha/tasks.md"}
    assert match.amount is None and match.timestamp is None


def test_the_tracked_files_are_one_record_each_with_the_short_commit() -> None:
    records = tracked().fetch()
    assert [r.raw_key for r in records] == [
        "README.md",
        "src/extra.py",
        "src/match.py",
        "src/report.py",
        "tests/fixtures/sample.csv",
    ]
    assert all(r.attrs == {"commit": "0123456789ab"} and r.timestamp is None for r in records)


def test_kiro_credits_are_summed_across_sessions_and_a_blank_share_is_zero_with_the_line_kept() -> None:
    records = {r.raw_key: r for r in kiro().fetch()}
    assert sorted(records) == ["old/gone.py", "src/extra.py", "src/match.py", "src/old_report.py", "src/report.py"]
    match = records["src/match.py"]
    assert match.amount == Decimal("1.5")
    assert match.attrs["sessions"] == "2" and match.attrs["unreported_lines"] == "1"
    assert match.attrs["models"] == "claude-haiku-5.5, claude-opus-5.5"
    assert match.attrs["last_session_on"] == "2026-11-07"
    assert match.timestamp == datetime(2026, 11, 7, 0, 10, tzinfo=UTC)
    assert records["src/extra.py"].amount == Decimal("0.25")
    assert "unreported_lines" not in records["src/extra.py"].attrs
    assert sum((r.amount or Decimal(0) for r in records.values()), Decimal(0)) == Decimal("5.00")


def test_a_file_whose_every_share_is_blank_is_billed_at_zero_and_still_present(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    (folder / "kiro-files.csv").write_text(
        "file,session,credit_share,started\nsrc/x.py,sess_a2,,2026-11-07T00:10:00.000Z\n", encoding="utf-8"
    )
    [record] = kiro(folder).fetch()
    assert record.raw_key == "src/x.py" and record.amount == Decimal(0)
    assert record.attrs["credits"] == "0" and record.attrs["unreported_lines"] == "1"


def test_kiro_spells_of_one_path_are_one_file(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    (folder / "kiro-files.csv").write_text(
        "file,session,credit_share,started\n"
        "src\\match.py,sess_a1,1.0,2026-11-06T22:01:00.000Z\n"
        "./src/match.py,sess_a3,0.5,2026-11-07T02:00:00.000Z\n",
        encoding="utf-8",
    )
    [record] = kiro(folder).fetch()
    assert record.raw_key == "src/match.py" and record.amount == Decimal("1.5")
    assert record.attrs["sessions"] == "2"


def test_a_kiro_line_with_no_file_is_kept_apart_with_its_credits(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    (folder / "kiro-files.csv").write_text(
        "file,session,credit_share,started\n,sess_a1,2.5,2026-11-06T22:01:00.000Z\n", encoding="utf-8"
    )
    [record] = kiro(folder).fetch()
    assert record.raw_key == "" and record.amount == Decimal("2.5")


def test_the_amounts_are_exact_decimals(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    (folder / "kiro-files.csv").write_text(
        "file,session,credit_share,started\n"
        "a/b.py,sess_a1,0.1,2026-11-06T22:01:00.000Z\n"
        "a/b.py,sess_a2,0.2,2026-11-06T22:02:00.000Z\n",
        encoding="utf-8",
    )
    [record] = kiro(folder).fetch()
    assert record.amount == Decimal("0.3") and record.attrs["credits"] == "0.3"


DAMAGE = [
    ("kiro-files.csv", "1.5,2026-11-06T22:01:00.000Z\nsrc/report.py", "abc,2026-11-06T22:01:00.000Z\nsrc/report.py"),
    ("kiro-files.csv", "0.25,2026-11-07T02:00:00.000Z\nold/gone.py", "-0.25,2026-11-07T02:00:00.000Z\nold/gone.py"),
    ("kiro-files.csv", "0.25,2026-11-07T02:00:00.000Z\nold/gone.py", "NaN,2026-11-07T02:00:00.000Z\nold/gone.py"),
    ("kiro-files.csv", "sess_a3,0.25,2026-11-07T02:00:00.000Z\nold", "sess_zz,0.25,2026-11-07T02:00:00.000Z\nold"),
    ("kiro-files.csv", "sess_a2,,2026-11-07T00:10:00.000Z", "sess_a2,,yesterday"),
    ("kiro-files.csv", "file,session,credit_share,started", "file,session,share,started"),
    ("kiro-sessions.csv", "claude-opus-5.5,3,4.5", "claude-opus-5.5,3,lots"),
]


@pytest.mark.parametrize("name,old,new", DAMAGE)
def test_a_damaged_kiro_export_is_refused(tmp_path: Path, name: str, old: str, new: str) -> None:
    folder = fixture_copy(tmp_path)
    edit(folder, name, old, new)
    with pytest.raises(ValueError):
        kiro(folder).fetch()


def test_a_spec_row_with_no_file_is_refused(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    edit(folder, "spec-files.csv", "deploy/stack.yaml,beta", ",beta")
    with pytest.raises(ValueError, match="no file"):
        specs(folder).fetch()


def test_a_tracked_file_listed_twice_is_refused(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    edit(folder, "tracked-files.csv", "src/extra.py", "src/match.py")
    with pytest.raises(ValueError, match="listed twice"):
        tracked(folder).fetch()


def test_tracked_files_of_two_commits_are_refused(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    edit(folder, "tracked-files.csv", "README.md,0123456789abcdef0123456789abcdef01234567", "README.md,deadbeef")
    with pytest.raises(ValueError, match="more than one commit"):
        tracked(folder).fetch()


def test_a_damaged_ledger_makes_the_night_incomplete_and_names_the_source(tmp_path: Path) -> None:
    folder = fixture_copy(tmp_path)
    edit(folder, "kiro-files.csv", "src/report.py,sess_a1,1.5", "src/report.py,sess_a1,abc")
    result = run_in(folder, tmp_path / "work")
    assert result.complete is False and result.missing_ledgers == ["billed"]
    assert result.findings == []
    assert "ValueError" in result.ledger_errors["billed"] and "abc" in result.ledger_errors["billed"]

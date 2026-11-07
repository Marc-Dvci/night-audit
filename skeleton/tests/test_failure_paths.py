"""Damaged inputs, through the runner. Each degrades as documented (Req 9.4, ghosts design §4):

* a control, exclusion or scope file that cannot be read refuses the audit and leaves no run;
* a ledger file that cannot be read, or a connector that fails or is not read-only, makes that ledger missing: the run
  is written, is incomplete, names the ledger and has no findings.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import RunResult
from nightaudit.runner import list_run_ids, run_control
from nightkit import CONTROL, RUN_TIME, write_account
from pydantic import ValidationError

pytestmark = pytest.mark.integration


def _run(control: Path, tmp_path: Path) -> RunResult:
    return run_control(control, tmp_path / "runs", run_time=RUN_TIME)


def _assert_missing(result: RunResult, ledger: str, says: str) -> None:
    assert not result.complete
    assert result.missing_ledgers == [ledger]
    assert says in result.ledger_errors[ledger]
    assert result.findings == []


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("id: [unclosed\nledgers: {", yaml.YAMLError),
        ("- just\n- a list\n", ValidationError),
        (CONTROL.replace("  billed:", "  paid:"), ValueError),  # not the three ledgers
        (CONTROL.replace("[strip, lower]", "[strip, shout]", 1), ValueError),  # unknown normaliser
        (CONTROL.replace("grace_hours: 24", "grace_hours: soon"), ValidationError),
    ],
)
def test_a_refused_audit_leaves_no_run(tmp_path: Path, text: str, error: type[Exception]) -> None:
    control = write_account(tmp_path)
    control.write_text(text, encoding="utf-8")
    with pytest.raises(error):
        _run(control, tmp_path)
    assert list_run_ids(tmp_path / "runs") == []


def test_a_control_file_that_is_not_utf_8_is_refused_and_leaves_no_run(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    control.write_bytes(CONTROL.encode("utf-16"))
    with pytest.raises(UnicodeDecodeError):
        _run(control, tmp_path)
    assert list_run_ids(tmp_path / "runs") == []


@pytest.mark.parametrize("text", ["keys: {a: 1}\n", "just text\n", "keys: [unclosed\n"])
def test_a_malformed_exclusion_file_refuses_the_audit_rather_than_excluding_nothing(tmp_path: Path, text: str) -> None:
    control = write_account(tmp_path)
    (tmp_path / "exclusions.local.yaml").write_text(text, encoding="utf-8")
    with pytest.raises((ValueError, yaml.YAMLError)):
        _run(control, tmp_path)
    assert list_run_ids(tmp_path / "runs") == []


def test_a_missing_exclusion_file_excludes_nothing(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    (tmp_path / "exclusions.local.yaml").unlink()
    result = _run(control, tmp_path)
    assert result.complete
    assert result.regions["i-0other"] == "OB"


def test_a_scope_file_that_is_not_a_mapping_refuses_the_audit(tmp_path: Path) -> None:
    control = write_account(tmp_path, CONTROL + "include_keys_file: scope.local.yaml\n")
    (tmp_path / "scope.local.yaml").write_text("- i-0aa1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must hold a mapping"):
        _run(control, tmp_path)
    assert list_run_ids(tmp_path / "runs") == []


@pytest.mark.parametrize(
    ("damage", "says"),
    [
        (lambda p: p.unlink(), "FileNotFoundError"),
        (lambda p: (p.unlink(), p.mkdir()), "Error"),  # a folder where the file should be: unreadable
        (lambda p: p.write_bytes(b"row_id,resource,amount\nb1,\xff\xfe,1.00\n"), "UnicodeDecodeError"),
    ],
    ids=["missing", "unreadable", "not-utf-8"],
)
def test_a_billed_file_that_cannot_be_read_makes_the_ledger_missing(
    tmp_path: Path, damage: Callable[[Path], object], says: str
) -> None:
    control = write_account(tmp_path)
    damage(tmp_path / "billed.csv")
    result = _run(control, tmp_path)
    _assert_missing(result, "billed", says)
    assert verify_evidence_pack(tmp_path / "runs" / result.run_id / "evidence").ok


def test_regression_an_incomplete_run_whose_billed_ledger_was_read_verifies_against_its_page(tmp_path: Path) -> None:
    """Bug, found by the first Crew run: an observed ledger that could not be read left a run whose page states no
    amount (``billed_total`` 0), while its chain holds the billed rows that were read. ``nightaudit verify`` compared
    the page with the sum of those rows and failed: "billed total: the page shows $0.00, the evidence has $6,683.00"."""
    control = write_account(tmp_path)
    (tmp_path / "observed.csv").unlink()
    result = _run(control, tmp_path)
    assert not result.complete and result.missing_ledgers == ["observed"]
    run_dir = tmp_path / "runs" / result.run_id
    displayed = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert displayed["billed_total"] == "0"
    verdict = verify_evidence_pack(run_dir / "evidence", displayed)
    assert verdict.ok, verdict.detail
    displayed["billed_total"] = "41.20"  # an amount on the page of a run that matched nothing is still refused
    assert not verify_evidence_pack(run_dir / "evidence", displayed).ok


@pytest.mark.parametrize("amount", ["1,234.50", "$3.10", "three", "3.10.1"])
def test_regression_a_billed_amount_that_is_not_a_number_makes_the_ledger_missing(tmp_path: Path, amount: str) -> None:
    """Bug: the CSV connector read an amount it could not parse as no amount, and the run reported a smaller bill."""
    control = write_account(tmp_path)
    billed = (tmp_path / "billed.csv").read_text(encoding="utf-8").replace(",41.20", f',"{amount}"')
    (tmp_path / "billed.csv").write_text(billed, encoding="utf-8")
    _assert_missing(_run(control, tmp_path), "billed", "amount")


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_a_billed_amount_that_is_not_finite_makes_the_ledger_missing(tmp_path: Path, amount: str) -> None:
    control = write_account(tmp_path)
    billed = (tmp_path / "billed.csv").read_text(encoding="utf-8").replace(",41.20", f",{amount}")
    (tmp_path / "billed.csv").write_text(billed, encoding="utf-8")
    _assert_missing(_run(control, tmp_path), "billed", "billed")


def test_regression_an_observed_timestamp_that_is_not_a_date_makes_the_ledger_missing(tmp_path: Path) -> None:
    """Bug: an unparseable timestamp was read as no timestamp, so a young record skipped the grace window."""
    control = write_account(tmp_path)
    observed = (tmp_path / "observed.csv").read_text(encoding="utf-8").replace("2026-11-02T21:14:00Z", "yesterday")
    (tmp_path / "observed.csv").write_text(observed, encoding="utf-8")
    _assert_missing(_run(control, tmp_path), "observed", "timestamp")


def test_an_empty_amount_and_an_empty_timestamp_are_absent_not_damaged(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    (tmp_path / "billed.csv").write_text("row_id,resource,amount\nb1,i-0aa1,\n", encoding="utf-8")
    (tmp_path / "observed.csv").write_text("row_id,id,ts\no1,i-0aa1,\n", encoding="utf-8")
    result = _run(control, tmp_path)
    assert result.complete
    assert result.regions["i-0aa1"] == "IOB"


@pytest.mark.parametrize(
    "lines",
    ['{"row_id": "g1", "id": "AKIA1"}\n{not json\n', '{"row_id": "g1", "id": "AKIA1"}\n[1, 2]\n'],
    ids=["broken-line", "not-an-object"],
)
def test_a_jsonl_source_with_a_broken_line_makes_its_ledger_missing(tmp_path: Path, lines: str) -> None:
    control = write_account(tmp_path)
    (tmp_path / "observed-global.jsonl").write_text(lines, encoding="utf-8")
    result = _run(control, tmp_path)
    assert result.missing_ledgers == ["observed"]
    assert "observed-global.jsonl" in result.ledger_errors["observed"]
    assert result.findings == []


def test_blank_lines_in_a_jsonl_source_are_skipped(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    jsonl = tmp_path / "observed-global.jsonl"
    jsonl.write_text("\n" + jsonl.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    assert _run(control, tmp_path).regions["akiaexample0001"] == "O"


def _with_billed_source(source: str) -> str:
    return CONTROL.replace("connector: {type: csv, path: billed.csv}", f"connector: {source}")


def test_a_connector_that_raises_midway_keeps_none_of_its_rows(tmp_path: Path) -> None:
    control = write_account(tmp_path, _with_billed_source("{type: python, entry: 'second_app_steps:BreaksMidway'}"))
    result = _run(control, tmp_path)
    _assert_missing(result, "billed", "ConnectionResetError: connection reset after 2 rows")
    billed = next(s for s in result.snapshots if s.name.value == "billed")
    assert billed.records == []


def test_a_connector_that_is_not_read_only_is_refused_before_it_fetches(tmp_path: Path) -> None:
    control = write_account(tmp_path, _with_billed_source("{type: python, entry: 'second_app_steps:Writes'}"))
    _assert_missing(_run(control, tmp_path), "billed", "refused, connector is not read-only")


@pytest.mark.parametrize(
    ("source", "says"),
    [
        ("{type: python, entry: 'second_app_steps'}", "must look like 'package.module:ClassName'"),
        ("{type: python, entry: 'second_app_steps:say'}", "is not a Connector subclass"),
        ("{type: python, entry: 'no_such_module:Thing'}", "No module named 'no_such_module'"),
        ("{type: python}", "has no entry"),
        ("{type: csv}", "has no path"),
        ("{type: ftp, path: billed.csv}", "unknown connector type 'ftp'"),
    ],
)
def test_a_connector_that_cannot_be_built_makes_its_ledger_missing(tmp_path: Path, source: str, says: str) -> None:
    control = write_account(tmp_path, _with_billed_source(source))
    _assert_missing(_run(control, tmp_path), "billed", says)


def test_a_corrupt_state_file_refuses_the_audit_rather_than_resetting_every_age(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    first = _run(control, tmp_path)
    (tmp_path / "runs" / "_state" / "demo-account.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        run_control(control, tmp_path / "runs", run_time=RUN_TIME.replace(day=5))
    assert list_run_ids(tmp_path / "runs") == [first.run_id]


def test_a_run_with_a_missing_ledger_keeps_the_state_of_the_last_complete_night(tmp_path: Path) -> None:
    control = write_account(tmp_path)
    _run(control, tmp_path)
    (tmp_path / "billed.csv").unlink()
    run_control(control, tmp_path / "runs", run_time=RUN_TIME.replace(day=5))
    write_account(tmp_path)
    third = run_control(control, tmp_path / "runs", run_time=RUN_TIME.replace(day=6))
    vampire = next(f for f in third.findings if f.region_code == "OB")
    assert (vampire.status, vampire.nights_persisted) == ("persisting", 2)

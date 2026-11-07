"""Casebook runner. The Night Audit `add-control` skill copies this file to `tests/test_casebook.py`.

It reads every `casebook/*.yaml`, builds the three ledgers of each case from the rows written there, runs the matcher
with the rules of the control file the casebook names, and compares the result with the expectations a person wrote
beforehand. It never writes an expectation. A casebook that is too small, or that has no healthy case, fails here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record, RunResult
from nightaudit.runner import load_control_file

CASEBOOK_DIR = Path(__file__).resolve().parents[1] / "casebook"
CASEBOOKS = sorted(CASEBOOK_DIR.glob("*.yaml"))
LEDGERS = ("intended", "observed", "billed")
MIN_CASES = 5
#: What a case may expect. A misspelt name fails the test instead of being ignored.
EXPECT_NAMES = frozenset(
    {
        "regions",
        "findings",
        "informational",
        "pending",
        "unkeyed",
        "billed_total",
        "billed_unkeyed",
        "billed_by_region",
        "duplicates",
        "complete",
        "missing_ledgers",
    }
)


@cache
def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: a casebook is a mapping with `control` and `cases`"
    return data


def _cases(path: Path) -> list[dict[str, Any]]:
    cases = _load(path).get("cases")
    assert isinstance(cases, list), f"{path.name}: `cases` must be a list"
    return cases


def _parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value)
    parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _snapshots(case: dict[str, Any]) -> list[LedgerSnapshot]:
    ledgers = case["ledgers"]
    snapshots: list[LedgerSnapshot] = []
    for name in LEDGERS:
        ledger = LedgerName(name)
        rows = ledgers[name]
        if rows is None:  # `null` means the source could not be read
            snapshots.append(LedgerSnapshot(name=ledger, source=f"casebook:{name}", missing=True))
            continue
        records = [
            Record(
                ledger=ledger,
                source=f"casebook:{name}",
                row_id=str(row["row"]),
                raw_key=str(row.get("key", "")),
                attrs={str(k): str(v) for k, v in (row.get("attrs") or {}).items()},
                amount=Decimal(str(row["amount"])) if "amount" in row else None,
                timestamp=_parse_ts(row.get("ts")),
            )
            for row in rows
        ]
        snapshots.append(LedgerSnapshot(name=ledger, source=f"casebook:{name}", records=records))
    return snapshots


def _differences(result: RunResult, expect: dict[str, Any]) -> list[str]:
    found: dict[str, Any] = {
        "regions": result.regions,
        "findings": sum(1 for f in result.findings if not f.informational),
        "informational": sum(1 for f in result.findings if f.informational),
        "pending": sorted(result.pending_keys),
        "unkeyed": sorted(u.row_id for u in result.unkeyed),
        "billed_total": result.billed_total,
        "billed_unkeyed": result.billed_unkeyed,
        "billed_by_region": {code: s.billed_amount for code, s in result.region_summaries.items()},
        "duplicates": result.duplicates,
        "complete": result.complete,
        "missing_ledgers": sorted(result.missing_ledgers),
    }
    problems: list[str] = []
    for name, wanted in expect.items():
        if name in ("billed_total", "billed_unkeyed"):
            wanted = Decimal(str(wanted))
        elif name == "billed_by_region":
            wanted = {code: Decimal(str(amount)) for code, amount in wanted.items()}
        elif name in ("pending", "unkeyed", "missing_ledgers"):
            wanted = sorted(wanted)
        if found[name] != wanted:
            problems.append(f"{name}: expected {wanted!r}, the matcher gave {found[name]!r}")
    return problems


def test_there_is_a_casebook() -> None:
    assert CASEBOOKS, f"no casebook in {CASEBOOK_DIR}: write casebook/<control>.yaml before running the matcher"


@pytest.mark.parametrize("path", CASEBOOKS, ids=lambda p: p.name)
def test_casebook_has_at_least_five_labelled_cases(path: Path) -> None:
    cases = _cases(path)
    assert len(cases) >= MIN_CASES, f"{path.name}: {len(cases)} cases, at least {MIN_CASES} are required"
    ids = [case.get("id") for case in cases]
    assert all(isinstance(i, str) and i for i in ids), f"{path.name}: every case needs an `id`"
    assert len(set(ids)) == len(ids), f"{path.name}: case ids must be unique"
    for case in cases:
        label = f"{path.name}/{case['id']}"
        assert str(case.get("note", "")).strip(), f"{label}: a case needs a `note` saying what it shows"
        assert set(case.get("ledgers") or {}) == set(LEDGERS), f"{label}: `ledgers` needs intended, observed, billed"
        assert case.get("expect"), f"{label}: a case needs `expect`"
        unknown = set(case["expect"]) - EXPECT_NAMES
        assert not unknown, f"{label}: unknown expectation {sorted(unknown)}; allowed {sorted(EXPECT_NAMES)}"
        assert case.get("now") or _load(path).get("now"), f"{label}: set `now` on the case or the casebook"


@pytest.mark.parametrize("path", CASEBOOKS, ids=lambda p: p.name)
def test_casebook_plants_a_healthy_case_that_expects_nothing(path: Path) -> None:
    healthy = [case for case in _cases(path) if case.get("healthy") is True]
    assert healthy, f"{path.name}: flag one case `healthy: true`; a healthy account must produce zero findings"
    for case in healthy:
        expect = case["expect"]
        label = f"{path.name}/{case['id']}"
        assert expect.get("findings") == 0, f"{label}: a healthy case expects `findings: 0`"
        assert not expect.get("informational"), f"{label}: a healthy case expects no informational items"
        assert not expect.get("pending"), f"{label}: a healthy case expects nothing pending"
        regions = expect.get("regions")
        assert regions, f"{label}: a healthy case lists the keys it expects, all `IOB`"
        assert set(regions.values()) == {"IOB"}, f"{label}: every key of a healthy case is `IOB`"


CASE_PARAMS = [
    pytest.param(path, case, id=f"{path.stem}/{case.get('id', '?')}") for path in CASEBOOKS for case in _cases(path)
]


@pytest.mark.parametrize(("path", "case"), CASE_PARAMS)
def test_case_matches_what_was_written_before_the_run(path: Path, case: dict[str, Any]) -> None:
    book = _load(path)
    control = load_control_file(path.parent / book["control"]).to_config()
    run_time = _parse_ts(case.get("now") or book["now"])
    assert run_time is not None
    result = match(_snapshots(case), control, run_time)
    problems = _differences(result, case["expect"])
    assert not problems, f"{case['id']}: " + "; ".join(problems)

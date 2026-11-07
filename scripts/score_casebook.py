#!/usr/bin/env python3
"""Casebook scorer: load cases, run the matcher, compare against expectations.

Usage::

    python scripts/score_casebook.py --set dev [--quiet]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record, RunResult

# --- Default controls -------------------------------------------------------


def _cloud_default() -> ControlConfig:
    """Cloud default control (vampires app)."""
    return ControlConfig(
        normalisers={
            "intended": ["strip", "lower"],
            "observed": ["strip", "lower"],
            "billed": ["arn_resource_id", "strip", "lower"],
        },
        grace_hours=24,
    )


def _people_default() -> ControlConfig:
    """People default control (ghosts app)."""
    return ControlConfig(
        normalisers={
            "intended": ["email_canonical"],
            "observed": ["email_canonical"],
            "billed": ["email_canonical"],
        },
        alias_domains={"hollowpines.org": "hollowpines.com"},
        grace_hours=24,
    )


def build_control(case: dict[str, Any]) -> ControlConfig:
    """Build a ControlConfig from default + per-case overrides (shallow merge)."""
    if case.get("people"):
        base = _people_default()
    else:
        base = _cloud_default()

    override = case.get("control")
    if not override:
        return base

    config_data: dict[str, Any] = base.model_dump()
    config_data.update(override)
    return ControlConfig(**config_data)


# --- Snapshot building ------------------------------------------------------


def _parse_ts(ts: str | datetime | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (handles ``Z`` suffix)."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts
    ts_str = ts
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def build_snapshots(case: dict[str, Any]) -> list[LedgerSnapshot]:
    """Build LedgerSnapshot objects from inline casebook data."""
    snapshots: list[LedgerSnapshot] = []
    ledgers = case.get("ledgers", {})
    for name in ("intended", "observed", "billed"):
        ledger_name = LedgerName(name)
        source = f"casebook:{name}"
        data = ledgers.get(name)

        if data is None:
            # null ledger — connector failed.
            snapshots.append(
                LedgerSnapshot(
                    name=ledger_name,
                    source=source,
                    records=[],
                    dropped=0,
                    missing=True,
                )
            )
            continue

        records: list[Record] = []
        for row in data:
            records.append(
                Record(
                    ledger=ledger_name,
                    source=source,
                    row_id=str(row.get("row", "")),
                    raw_key=row.get("key", ""),
                    attrs=row.get("attrs", {}),
                    amount=Decimal(str(row["amount"])) if "amount" in row else None,
                    timestamp=_parse_ts(row.get("ts")),
                )
            )
        snapshots.append(
            LedgerSnapshot(
                name=ledger_name,
                source=source,
                records=records,
                dropped=0,
                missing=False,
            )
        )
    return snapshots


# --- Result comparison ------------------------------------------------------


def compare_result(result: RunResult, expect: dict[str, Any]) -> list[str]:
    """Compare a RunResult against expectations.  Returns a list of failures."""
    failures: list[str] = []

    if "regions" in expect:
        if result.regions != expect["regions"]:
            failures.append(f"regions: expected {expect['regions']}, got {result.regions}")

    if "findings" in expect:
        actual = sum(1 for f in result.findings if not f.informational)
        if actual != expect["findings"]:
            failures.append(f"findings: expected {expect['findings']}, got {actual}")

    if "informational" in expect:
        actual = sum(1 for f in result.findings if f.informational)
        if actual != expect["informational"]:
            failures.append(f"informational: expected {expect['informational']}, got {actual}")

    if "billed_total" in expect:
        expected_total = Decimal(expect["billed_total"])
        if result.billed_total != expected_total:
            failures.append(f"billed_total: expected {expected_total}, got {result.billed_total}")

    if "billed_by_region" in expect:
        expected_by_region = {k: Decimal(v) for k, v in expect["billed_by_region"].items()}
        actual_by_region = {k: v.billed_amount for k, v in result.region_summaries.items()}
        if actual_by_region != expected_by_region:
            failures.append(f"billed_by_region: expected {expected_by_region}, got {actual_by_region}")

    if "billed_unkeyed" in expect:
        expected_unkeyed = Decimal(expect["billed_unkeyed"])
        if result.billed_unkeyed != expected_unkeyed:
            failures.append(f"billed_unkeyed: expected {expected_unkeyed}, got {result.billed_unkeyed}")

    if "pending" in expect:
        expected_pending = sorted(expect["pending"])
        actual_pending = sorted(result.pending_keys)
        if actual_pending != expected_pending:
            failures.append(f"pending: expected {expected_pending}, got {actual_pending}")

    if "unkeyed" in expect:
        expected_unkeyed = sorted(expect["unkeyed"])
        actual_unkeyed = sorted(u.row_id for u in result.unkeyed)
        if actual_unkeyed != expected_unkeyed:
            failures.append(f"unkeyed: expected {expected_unkeyed}, got {actual_unkeyed}")

    if "duplicates" in expect:
        if result.duplicates != expect["duplicates"]:
            failures.append(f"duplicates: expected {expect['duplicates']}, got {result.duplicates}")

    if "dropped" in expect:
        if result.dropped != expect["dropped"]:
            failures.append(f"dropped: expected {expect['dropped']}, got {result.dropped}")

    if "complete" in expect:
        if result.complete != expect["complete"]:
            failures.append(f"complete: expected {expect['complete']}, got {result.complete}")

    if "missing_ledgers" in expect:
        expected_missing = sorted(expect["missing_ledgers"])
        actual_missing = sorted(result.missing_ledgers)
        if actual_missing != expected_missing:
            failures.append(f"missing_ledgers: expected {expected_missing}, got {actual_missing}")

    return failures


# --- Main -------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the Night Audit casebook.")
    parser.add_argument("--set", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    casebook_path = Path(f"casebook/{args.set}/cases.yaml")
    if not casebook_path.exists():
        print(f"Casebook not found: {casebook_path}")
        return 1

    with open(casebook_path, encoding="utf-8") as f:
        cases = yaml.safe_load(f)

    passed = 0
    failed = 0
    for case in cases:
        control = build_control(case)
        snapshots = build_snapshots(case)
        now = _parse_ts(case["now"])
        if now is None:
            print(f"ERROR {case['id']}: missing 'now'")
            failed += 1
            continue
        result = match(snapshots, control, now)
        failures = compare_result(result, case.get("expect", {}))

        if not failures:
            passed += 1
            if not args.quiet:
                print(f"PASS  {case['id']}")
        else:
            failed += 1
            if not args.quiet:
                print(f"FAIL  {case['id']}")
                for msg in failures:
                    print(f"      {msg}")

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Matching engine: partition keys into regions, produce findings.

``match(snapshots, control, run_time)`` takes three ``LedgerSnapshot`` objects,
a ``ControlConfig``, and a ``datetime`` run time, and returns a ``RunResult``.
The algorithm follows design §6.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Any

from .control import ControlConfig
from .grace import find_pending
from .models import (
    DEFAULT_REGION_MEANINGS,
    DEFAULT_REGION_NAMES,
    DEFAULT_REGION_SEVERITIES,
    INFORMATIONAL_REGIONS,
    Finding,
    LedgerName,
    LedgerSnapshot,
    Record,
    RegionSummary,
    RunResult,
    UnkeyedRow,
)
from .normalisers import normalise
from .scope import apply_scope


def _region_code(present: set[LedgerName]) -> str:
    """Join the present ledger initials in I-O-B order."""
    code = ""
    if LedgerName.intended in present:
        code += "I"
    if LedgerName.observed in present:
        code += "O"
    if LedgerName.billed in present:
        code += "B"
    return code


def _derive_run_id(run_time: datetime, control_hash: str) -> str:
    """Deterministic run id derived from run_time + control_hash."""
    raw = f"{run_time.isoformat()!s}:{control_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _resolve_region(
    code: str, control: ControlConfig
) -> tuple[str, str, str]:
    """Resolve (name, severity, meaning) from overrides or defaults (Req 1.4)."""
    override = control.regions.get(code)
    if override is not None:
        name = override.name if override.name is not None else DEFAULT_REGION_NAMES[code]
        severity = (
            override.severity
            if override.severity is not None
            else DEFAULT_REGION_SEVERITIES[code]
        )
        meaning = (
            override.meaning
            if override.meaning is not None
            else DEFAULT_REGION_MEANINGS[code]
        )
    else:
        name = DEFAULT_REGION_NAMES[code]
        severity = DEFAULT_REGION_SEVERITIES[code]
        meaning = DEFAULT_REGION_MEANINGS[code]
    return name, severity, meaning


def match(
    snapshots: list[LedgerSnapshot],
    control: ControlConfig,
    run_time: datetime,
) -> RunResult:
    """Run the three-way match and return a ``RunResult``."""
    # Step 0 — Missing-ledger check (Req 9.4).
    missing = [s.name.value for s in snapshots if s.missing]
    if missing:
        control_hash = control.canonical_hash()
        return RunResult(
            run_id=_derive_run_id(run_time, control_hash),
            run_time=run_time,
            control_hash=control_hash,
            complete=False,
            missing_ledgers=missing,
            snapshots=snapshots,
            dropped={s.name.value: 0 for s in snapshots},
        )

    # Step 1 — Normalise keys.
    ctx: dict[str, Any] = {"alias_domains": control.alias_domains}
    normalised_snapshots: list[LedgerSnapshot] = []
    unkeyed: list[UnkeyedRow] = []

    for snapshot in snapshots:
        chain = control.normalisers.get(snapshot.name.value, [])
        new_records: list[Record] = []
        for record in snapshot.records:
            normalised_key = normalise(record.raw_key, chain, ctx)
            if normalised_key == "":
                unkeyed.append(
                    UnkeyedRow(
                        row_id=record.row_id,
                        ledger=record.ledger,
                        source=record.source,
                        amount=record.amount,
                    )
                )
                new_record = record.model_copy(update={"key": None})
            else:
                new_record = record.model_copy(update={"key": normalised_key})
            new_records.append(new_record)
        normalised_snapshots.append(
            snapshot.model_copy(update={"records": new_records})
        )

    # Step 2 — Scope filtering.
    filtered_snapshots, dropped = apply_scope(normalised_snapshots, control.scope)

    # Step 3 — Group by key.
    records_by_key: dict[str, list[Record]] = {}
    for snapshot in filtered_snapshots:
        for record in snapshot.records:
            if record.key is not None:
                records_by_key.setdefault(record.key, []).append(record)

    # Build keys_in_ledger and observed_records_by_key from records_by_key.
    keys_in_ledger: dict[LedgerName, set[str]] = {name: set() for name in LedgerName}
    observed_records_by_key: dict[str, list[Record]] = {}
    for key, key_records in records_by_key.items():
        for record in key_records:
            keys_in_ledger[record.ledger].add(key)
            if record.ledger == LedgerName.observed:
                observed_records_by_key.setdefault(key, []).append(record)

    # Step 4 — Grace window (Req 4.1).
    pending_keys = find_pending(
        keys_in_ledger[LedgerName.observed],
        keys_in_ledger[LedgerName.billed],
        observed_records_by_key,
        control.grace_hours,
        run_time,
    )

    # Remove pending keys entirely from the region assignment.
    for key in pending_keys:
        records_by_key.pop(key, None)

    # Rebuild keys_in_ledger after grace removal.
    keys_in_ledger = {name: set() for name in LedgerName}
    for key, key_records in records_by_key.items():
        for record in key_records:
            keys_in_ledger[record.ledger].add(key)

    # Step 5 — Compute regions (Req 3.1).
    regions: dict[str, str] = {}
    for key in records_by_key:
        present: set[LedgerName] = set()
        for ledger_name in LedgerName:
            if key in keys_in_ledger[ledger_name]:
                present.add(ledger_name)
        regions[key] = _region_code(present)

    # Step 6 — Produce findings.
    findings: list[Finding] = []
    duplicates: dict[str, dict[str, int]] = {}

    for key, code in regions.items():
        if code == "IOB":
            continue

        key_records = records_by_key[key]

        # Billed amount for this key.
        billed_amount = Decimal("0")
        for record in key_records:
            if record.ledger == LedgerName.billed and record.amount is not None:
                billed_amount += record.amount

        # Duplicate counts (Req 3.4).
        duplicate_counts: dict[str, int] = {}
        for ledger_name in LedgerName:
            count = sum(1 for r in key_records if r.ledger == ledger_name)
            if count > 1:
                duplicate_counts[ledger_name.value] = count
        if duplicate_counts:
            duplicates[key] = duplicate_counts

        name, severity, meaning = _resolve_region(code, control)
        informational = code in INFORMATIONAL_REGIONS

        findings.append(
            Finding(
                key=key,
                region_code=code,
                name=name,
                severity=severity,
                meaning=meaning,
                informational=informational,
                records=key_records,
                billed_amount=billed_amount,
                duplicate_counts=duplicate_counts,
                status="new",
                nights_persisted=None,
                first_seen=run_time,
            )
        )

    # Step 7 — Compute summaries (Req 3.5).
    region_summaries: dict[str, RegionSummary] = {}
    for code in set(regions.values()):
        keys_in_region = [k for k, c in regions.items() if c == code]
        billed_amount = Decimal("0")
        for k in keys_in_region:
            for record in records_by_key[k]:
                if record.ledger == LedgerName.billed and record.amount is not None:
                    billed_amount += record.amount
        region_summaries[code] = RegionSummary(
            code=code,
            key_count=len(keys_in_region),
            billed_amount=billed_amount,
        )

    # Step 8 — Amount conservation (Req 3.5).
    billed_total = Decimal("0")
    billed_unkeyed = Decimal("0")
    for snapshot in filtered_snapshots:
        if snapshot.name == LedgerName.billed:
            for record in snapshot.records:
                if record.amount is not None:
                    billed_total += record.amount
                    if record.key is None:
                        billed_unkeyed += record.amount

    region_sum = Decimal("0")
    for rs in region_summaries.values():
        region_sum += rs.billed_amount

    assert region_sum + billed_unkeyed == billed_total, (
        f"Amount conservation failed: {region_sum} + {billed_unkeyed} != {billed_total}"
    )

    # Step 9 — Assemble RunResult.
    control_hash = control.canonical_hash()
    return RunResult(
        run_id=_derive_run_id(run_time, control_hash),
        run_time=run_time,
        control_hash=control_hash,
        complete=True,
        missing_ledgers=[],
        snapshots=filtered_snapshots,
        regions=regions,
        pending_keys=sorted(pending_keys),
        unkeyed=unkeyed,
        findings=findings,
        region_summaries=region_summaries,
        duplicates=duplicates,
        billed_total=billed_total,
        billed_unkeyed=billed_unkeyed,
        dropped=dropped,
    )

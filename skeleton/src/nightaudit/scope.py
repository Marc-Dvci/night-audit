"""Scope filtering: drop out-of-scope records before matching (Req 4.2).

A ``ScopeFilter`` declares an attribute name and a required value.  A record is
in scope when ``record.attrs.get(attr) == equals``.  Records missing the
attribute are out of scope.  Dropped records are counted per ledger.
"""

from __future__ import annotations

from .control import ScopeFilter
from .models import LedgerSnapshot, Record


def apply_scope(
    snapshots: list[LedgerSnapshot], scope: ScopeFilter | None
) -> tuple[list[LedgerSnapshot], dict[str, int]]:
    """Drop out-of-scope records and count dropped per ledger.

    Returns the filtered snapshots and a dict of dropped counts keyed by
    ledger name.
    """
    if scope is None:
        return snapshots, {s.name.value: 0 for s in snapshots}

    result_snapshots: list[LedgerSnapshot] = []
    dropped: dict[str, int] = {}

    for snapshot in snapshots:
        if snapshot.missing:
            result_snapshots.append(snapshot)
            dropped[snapshot.name.value] = 0
            continue

        kept: list[Record] = []
        count = 0
        for record in snapshot.records:
            if record.attrs.get(scope.attr) == scope.equals:
                kept.append(record)
            else:
                count += 1

        new_snapshot = snapshot.model_copy(update={"records": kept, "dropped": count})
        result_snapshots.append(new_snapshot)
        dropped[snapshot.name.value] = count

    return result_snapshots, dropped

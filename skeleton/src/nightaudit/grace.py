"""Grace window: suppress young unbilled keys as pending (Req 4.1).

A key is pending when:
1. It has at least one observed record with a timestamp.
2. Its most recent observed timestamp is within ``grace_hours`` of ``run_time``.
3. It does not appear in the billed ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import Record


def find_pending(
    keys_in_observed: set[str],
    billed_keys: set[str],
    observed_records_by_key: dict[str, list[Record]],
    grace_hours: int,
    run_time: datetime,
) -> set[str]:
    """Return the set of keys to suppress as pending."""
    pending: set[str] = set()
    for key in keys_in_observed:
        if key in billed_keys:
            continue
        records = observed_records_by_key.get(key, [])
        timestamps = [r.timestamp for r in records if r.timestamp is not None]
        if not timestamps:
            continue
        max_ts = max(timestamps)
        if run_time - max_ts < timedelta(hours=grace_hours):
            pending.add(key)
    return pending

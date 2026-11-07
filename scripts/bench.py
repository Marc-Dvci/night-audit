"""Matcher throughput: n keys in each ledger, 1% of them made into each kind of finding.

uv run python scripts/bench.py 100000
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    old = datetime(2026, 9, 1, tzinfo=UTC)
    keys = [f"i-{k:010x}" for k in range(n)]
    cut = n // 100
    intended = [
        Record(ledger=LedgerName.intended, source="i", row_id=f"i{k}", raw_key=key) for k, key in enumerate(keys[cut:])
    ]  # first 1% never declared
    observed = [
        Record(ledger=LedgerName.observed, source="o", row_id=f"o{k}", raw_key=key.upper(), timestamp=old)
        for k, key in enumerate(keys[: n - cut])
    ]  # last 1% gone
    billed = [
        Record(
            ledger=LedgerName.billed,
            source="b",
            row_id=f"b{k}",
            raw_key=f"arn:aws:ec2:us-east-1:111122223333:instance/{key}",
            amount=Decimal("0.0104"),
        )
        for k, key in enumerate(keys)
    ]
    chain = ["arn_resource_id", "strip", "lower"]
    control = ControlConfig(normalisers={"intended": chain, "observed": chain, "billed": chain}, grace_hours=36)
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i", records=intended),
        LedgerSnapshot(name=LedgerName.observed, source="o", records=observed),
        LedgerSnapshot(name=LedgerName.billed, source="b", records=billed),
    ]
    records = len(intended) + len(observed) + len(billed)
    start = time.perf_counter()
    result = match(snapshots, control, datetime(2026, 11, 6, 2, tzinfo=UTC))
    elapsed = time.perf_counter() - start
    counts = {code: s.key_count for code, s in result.region_summaries.items()}
    print(f"{records:,} records, {n:,} keys matched in {elapsed:.2f} s ({records / elapsed:,.0f} records/s)")
    print(f"regions: {counts}; findings: {len(result.findings):,}; billed total {result.billed_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

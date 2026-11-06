"""Write an exclusion file from the current inventory: the audit's scope starts at onboarding.

Every resource created before ``--before`` (or with no creation time) is listed, except names that start with
``--keep-prefix``. The file is local and untracked; runs only report how many keys it excluded.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml
from nightaudit.models import LedgerName
from nightaudit.normalisers import normalise

from .aws import CostAndUsage, Inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vampires-baseline")
    parser.add_argument("--before", required=True, help="ISO-8601 UTC cut-off, e.g. 2026-11-04T12:00:00Z")
    parser.add_argument("--keep-prefix", action="append", default=["night-audit"], help="names never excluded")
    parser.add_argument("--profile", default="night-audit")
    parser.add_argument("--out", default="apps/vampires/controls/exclusions.local.yaml")
    parser.add_argument("--cur-bucket", help="also exclude billed resources whose first usage is before the cut-off")
    parser.add_argument("--cur-prefix", default="cur2")
    parser.add_argument("--cur-export", default="night-audit-cur2")
    args = parser.parse_args(argv)

    cutoff = datetime.fromisoformat(args.before.replace("Z", "+00:00"))
    records = Inventory(ledger=LedgerName.observed, profile=args.profile).fetch()
    keys: set[str] = set()
    for record in records:
        if any(record.raw_key.lower().startswith(p) for p in args.keep_prefix):
            continue
        if record.timestamp is None or record.timestamp < cutoff:
            keys.add(record.raw_key.strip().lower())
    billed_count = 0
    if args.cur_bucket:
        billed = CostAndUsage(
            ledger=LedgerName.billed, profile=args.profile, bucket=args.cur_bucket,
            prefix=args.cur_prefix, export=args.cur_export,
        ).fetch()
        billed_count = len(billed)
        chain = ["arn_resource_id", "strip", "lower"]
        for record in billed:
            key = normalise(record.raw_key, chain, {})
            if not key or any(key.startswith(p) for p in args.keep_prefix):
                continue
            if record.timestamp is not None and record.timestamp < cutoff:
                keys.add(key)
    out = Path(args.out)
    out.write_text(
        "# Local exclusion list written by vampires-baseline. Not committed.\n"
        + yaml.safe_dump(
            {"written_at": datetime.now(UTC).isoformat(), "before": args.before, "keys": sorted(keys)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"{len(keys)} keys written to {out} ({len(records)} inventoried, {billed_count} billed groups read)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

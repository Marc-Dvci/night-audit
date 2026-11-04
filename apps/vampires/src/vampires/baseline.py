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

from .aws import Inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vampires-baseline")
    parser.add_argument("--before", required=True, help="ISO-8601 UTC cut-off, e.g. 2026-11-04T12:00:00Z")
    parser.add_argument("--keep-prefix", action="append", default=["night-audit"], help="names never excluded")
    parser.add_argument("--profile", default="night-audit")
    parser.add_argument("--out", default="apps/vampires/controls/exclusions.local.yaml")
    args = parser.parse_args(argv)

    cutoff = datetime.fromisoformat(args.before.replace("Z", "+00:00"))
    records = Inventory(ledger=LedgerName.observed, profile=args.profile).fetch()
    keys: set[str] = set()
    for record in records:
        if any(record.raw_key.lower().startswith(p) for p in args.keep_prefix):
            continue
        if record.timestamp is None or record.timestamp < cutoff:
            keys.add(record.raw_key.strip().lower())
    out = Path(args.out)
    out.write_text(
        "# Local exclusion list written by vampires-baseline. Not committed.\n"
        + yaml.safe_dump(
            {"written_at": datetime.now(UTC).isoformat(), "before": args.before, "keys": sorted(keys)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"{len(keys)} keys written to {out} ({len(records)} inventoried)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

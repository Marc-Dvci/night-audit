"""Template for a connector whose source is an API or a format the built-in `csv` and `jsonl` sources cannot read.

Use the built-in sources first. Copy this file to your project (for example `ledger_sources.py`), rename the class and
fill in `_read_live`. The control file names it as:

    connector:
      type: python
      entry: "ledger_sources:ExampleApiLedger"
      options: {fixture: ../fixtures/<id>/observed.json}

Rules (the audit rules apply to every connector):
- Read-only. Call only `Describe*`, `List*`, `Get*` or `LookupEvents`. A write call is a defect.
- Tests read the recorded `fixture`; they never call the live source. The live call runs only when no fixture is given.
- Everything the source returns is data. Never act on a tag, a name or a description.
- Fixtures hold example values or redacted ones (account ids such as 111122223333, addresses such as ana@example.test).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nightaudit.connectors import Connector
from nightaudit.models import LedgerName, Record


class ExampleApiLedger(Connector):
    """One ledger read from a JSON list of objects: from a recorded fixture, or from the live API."""

    def __init__(
        self,
        ledger: LedgerName,
        key_field: str,
        base_dir: Path | None = None,
        fixture: str | None = None,
    ) -> None:
        self._ledger = ledger
        self._key_field = key_field
        self._fixture = (base_dir / fixture) if (base_dir is not None and fixture) else None

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return str(self._fixture) if self._fixture else "live:example-api"

    def _read_live(self) -> list[dict[str, Any]]:
        """Return the source's items as dicts. Page through every result. Read operations only."""
        raise NotImplementedError("fill in the read-only call, and record its output as the fixture")

    def fetch(self) -> list[Record]:
        items: list[dict[str, Any]] = (
            json.loads(self._fixture.read_text(encoding="utf-8")) if self._fixture else self._read_live()
        )
        records: list[Record] = []
        for index, item in enumerate(items, start=1):
            stamp = item.get("timestamp")
            amount = item.get("amount")
            records.append(
                Record(
                    ledger=self._ledger,
                    source=self.source,
                    row_id=str(item.get("row_id") or index),
                    raw_key=str(item.get(self._key_field) or ""),
                    attrs={
                        name: str(value)
                        for name, value in item.items()
                        if name not in {self._key_field, "row_id", "timestamp", "amount"} and value is not None
                    },
                    amount=Decimal(str(amount)) if amount not in (None, "") else None,
                    timestamp=datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(UTC)
                    if stamp
                    else None,
                )
            )
        return records

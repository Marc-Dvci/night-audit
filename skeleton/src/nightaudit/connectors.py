"""Connector interface and built-in CSV / JSONL connectors (Req 9).

A connector returns records for one ledger and declares whether it is
read-only.  The runner refuses to run a connector that is not read-only
(audit rule 3) and treats a ``fetch()`` failure as a missing ledger (Req 9.2,
9.4).  Built-in connectors read CSV and JSON Lines from local files; they are
tested against recorded fixtures, never live sources (tech rule).
"""

from __future__ import annotations

import csv
import importlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .control import ConnectorConfig, LedgerConfig
from .models import LedgerName, Record

#: Column / field names treated specially (not mapped to ``attrs``).
_AMOUNT_FIELDS = {"amount"}
_TS_FIELDS = {"ts", "timestamp"}
_ID_FIELDS = {"row_id", "id"}


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp; naive values are assumed UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _parse_amount(value: object) -> Decimal | None:
    """Parse a money value as ``Decimal``; empty/None becomes ``None``."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class Connector(ABC):
    """Returns records for one ledger and declares whether it is read-only.

    The runner calls ``bind_run_time`` before ``fetch()`` (Req 10.1). A connector that needs the run date reads
    ``self.run_time``; one that does not needs no change, because neither member is abstract.
    """

    _bound_run_time: datetime | None = None

    def bind_run_time(self, when: datetime) -> None:
        """Record the run's time (UTC). Called by the runner just before ``fetch()``."""
        self._bound_run_time = when if when.tzinfo is not None else when.replace(tzinfo=UTC)

    @property
    def run_time(self) -> datetime | None:
        """The run's time, or ``None`` when the connector is used outside a run."""
        return self._bound_run_time

    @property
    @abstractmethod
    def ledger(self) -> LedgerName: ...

    @property
    @abstractmethod
    def read_only(self) -> bool: ...

    @property
    @abstractmethod
    def source(self) -> str: ...

    @abstractmethod
    def fetch(self) -> list[Record]: ...


class CSVConnector(Connector):
    """Reads a CSV file, mapping ``key_field`` to ``raw_key`` (Req 9.3)."""

    def __init__(
        self,
        path: Path,
        ledger: LedgerName,
        key_field: str,
        source: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._ledger = ledger
        self._key_field = key_field
        self._source = source if source is not None else str(self._path)

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return self._source

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        with self._path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for index, row in enumerate(reader, start=1):
                raw_key = str(row.get(self._key_field, "") or "")
                row_id = str(row.get("row_id") or row.get("id") or index)
                amount = _parse_amount(next(
                    (row.get(name) for name in _AMOUNT_FIELDS if name in row), None
                ))
                ts_value = next((row.get(name) for name in _TS_FIELDS if name in row), None)
                timestamp = _parse_ts(ts_value)
                excluded = (
                    {self._key_field}
                    | _AMOUNT_FIELDS
                    | _TS_FIELDS
                    | _ID_FIELDS
                )
                attrs = {
                    name: str(value)
                    for name, value in row.items()
                    if name is not None and name not in excluded and value is not None and value != ""
                }
                records.append(
                    Record(
                        ledger=self._ledger,
                        source=self._source,
                        row_id=row_id,
                        raw_key=raw_key,
                        attrs=attrs,
                        amount=amount,
                        timestamp=timestamp,
                    )
                )
        return records


class JSONLConnector(Connector):
    """Reads a JSON Lines file, mapping ``key_field`` to ``raw_key`` (Req 9.3)."""

    def __init__(
        self,
        path: Path,
        ledger: LedgerName,
        key_field: str,
        source: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._ledger = ledger
        self._key_field = key_field
        self._source = source if source is not None else str(self._path)

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return self._source

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        with self._path.open(encoding="utf-8") as f:
            for index, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                row: dict[str, Any] = json.loads(line)
                raw_key = str(row.get(self._key_field, "") or "")
                row_id = str(row.get("row_id") or row.get("id") or index)
                amount = _parse_amount(next(
                    (row.get(name) for name in _AMOUNT_FIELDS if name in row), None
                ))
                ts_value = next((row.get(name) for name in _TS_FIELDS if name in row), None)
                timestamp = _parse_ts(ts_value)
                excluded = (
                    {self._key_field}
                    | _AMOUNT_FIELDS
                    | _TS_FIELDS
                    | _ID_FIELDS
                )
                attrs = {
                    name: str(value)
                    for name, value in row.items()
                    if name not in excluded and value is not None
                }
                records.append(
                    Record(
                        ledger=self._ledger,
                        source=self._source,
                        row_id=row_id,
                        raw_key=raw_key,
                        attrs=attrs,
                        amount=amount,
                        timestamp=timestamp,
                    )
                )
        return records


def _resolve_path(path: str, base_dir: Path | None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or base_dir is None:
        return candidate
    return base_dir / candidate


def _load_entry(entry: str) -> type[Connector]:
    """Import ``package.module:ClassName`` and check it is a connector class."""
    module_name, _, class_name = entry.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"connector entry '{entry}' must look like 'package.module:ClassName'")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if not isinstance(cls, type) or not issubclass(cls, Connector):
        raise ValueError(f"connector entry '{entry}' is not a Connector subclass")
    return cls


def make_source(
    ledger: LedgerName,
    source: ConnectorConfig,
    key_field: str,
    base_dir: Path | None = None,
) -> Connector:
    """Build one connector for one configured source of a ledger."""
    field = source.key_field or key_field
    if source.type in ("csv", "jsonl"):
        if source.path is None:
            raise ValueError(f"{source.type} source for ledger '{ledger.value}' has no path")
        path = _resolve_path(source.path, base_dir)
        cls: type[CSVConnector] | type[JSONLConnector] = (
            CSVConnector if source.type == "csv" else JSONLConnector
        )
        return cls(path, ledger, field, source=source.path)
    if source.type == "python":
        if source.entry is None:
            raise ValueError(f"python source for ledger '{ledger.value}' has no entry")
        connector_cls = _load_entry(source.entry)
        return connector_cls(  # type: ignore[call-arg]
            ledger=ledger, key_field=field, base_dir=base_dir, **source.options
        )
    raise ValueError(f"unknown connector type '{source.type}' for ledger '{ledger.value}'")


def make_connectors(
    ledger: LedgerName, config: LedgerConfig, base_dir: Path | None = None
) -> list[Connector]:
    """Build every connector configured for a ledger."""
    sources = config.all_sources()
    if not sources:
        raise ValueError(f"no connector configured for ledger '{ledger.value}'")
    return [make_source(ledger, source, config.key_field, base_dir) for source in sources]


def make_connector(ledger: LedgerName, config: LedgerConfig) -> Connector:
    """Build the single connector of a one-source ledger (kept for simple callers)."""
    return make_connectors(ledger, config)[0]

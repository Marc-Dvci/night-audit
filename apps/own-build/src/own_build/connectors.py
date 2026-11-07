"""Read-only file connectors for the own-build control: the specs' promises, the tracked files, Kiro's work.

Each connector reads a recorded CSV and returns the records of one ledger, keyed by repository file path. A damaged
export raises, so the skeleton marks the ledger missing and the run produces no findings from damaged data
(skeleton Req 9.4). None of them touches git, Kiro or the network: the snapshot script and the export are the only
places those are read, and they write the CSVs these connectors load.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from nightaudit.connectors import Connector
from nightaudit.models import LedgerName, Record

from .paths import canonical_path


def resolve_path(path: str | Path, base_dir: Path | None) -> Path:
    """A relative path is relative to the control file's directory, as for the skeleton's CSV connector."""
    candidate = Path(path)
    if candidate.is_absolute() or base_dir is None:
        return candidate
    return base_dir / candidate


def read_csv(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    """Every row of a CSV file as a dict of stripped strings. A missing required column raises."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = [str(name).strip() for name in reader.fieldnames or []]
        missing = [name for name in required if name not in header]
        if missing:
            raise ValueError(f"{path.name}: no column {', '.join(missing)}")
        return [{str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None} for row in reader]


def parse_time(value: str, what: str) -> datetime | None:
    """An ISO-8601 time, naive values in UTC, or ``None`` when empty. Anything else raises."""
    if not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{what}: '{value[:40]}' is not an ISO-8601 time") from None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def parse_credits(value: str, what: str) -> Decimal | None:
    """Credits as an exact decimal, or ``None`` when blank. Text that is not a finite number >= 0 raises."""
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{what}: '{value[:40]}' is not a number") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{what}: '{value[:40]}' must be a number that is not negative")
    return number


def credits_text(amount: Decimal) -> str:
    """Plain decimal notation (``str`` would write ``0E-4``, whose digits are not evidence)."""
    return format(amount, "f")


class _FileConnector(Connector):
    """Shared plumbing: the skeleton's constructor keywords, the read-only declaration and record building."""

    def __init__(self, ledger: LedgerName, key_field: str = "", base_dir: Path | None = None, **_: Any) -> None:
        self._ledger = ledger
        self._base_dir = base_dir

    @property
    def ledger(self) -> LedgerName:
        return self._ledger

    @property
    def read_only(self) -> bool:
        return True

    def _record(
        self,
        row_id: str,
        raw_key: str,
        attrs: dict[str, str],
        amount: Decimal | None = None,
        timestamp: datetime | None = None,
    ) -> Record:
        return Record(
            ledger=self._ledger,
            source=self.source,
            row_id=row_id,
            raw_key=raw_key,
            attrs={k: v for k, v in attrs.items() if v != ""},
            amount=amount,
            timestamp=timestamp,
        )


def _file_of(row: dict[str, str], index: int, name: str) -> str:
    path = canonical_path(row.get("file", ""))
    if not path:
        raise ValueError(f"{name} row {index}: no file")
    return path


class SpecFiles(_FileConnector):
    """Intended ledger: one record per file a spec names, keyed by repository path.

    The snapshot has one row per file, spec and document that names it; this folds them into one record per file, so
    a file promised twice is one promise with both specs on it.
    """

    def __init__(self, path: str = "spec-files.csv", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._path = path

    @property
    def source(self) -> str:
        return f"specs:{self._path}"

    def fetch(self) -> list[Record]:
        rows = read_csv(resolve_path(self._path, self._base_dir), ("file", "spec", "doc"))
        docs: dict[str, set[tuple[str, str]]] = {}
        for index, row in enumerate(rows, start=1):
            file = _file_of(row, index, "spec-files.csv")
            if not row["spec"] or not row["doc"]:
                raise ValueError(f"spec-files.csv row {index}: no spec or document")
            docs.setdefault(file, set()).add((row["spec"], row["doc"]))
        records: list[Record] = []
        for file in sorted(docs):
            pairs = sorted(docs[file])
            records.append(
                self._record(
                    f"spec:{file}",
                    file,
                    {
                        "specs": ", ".join(sorted({spec for spec, _ in pairs})),
                        "documents": ", ".join(f"{spec}/{doc}" for spec, doc in pairs),
                    },
                )
            )
        return records


class TrackedFiles(_FileConnector):
    """Observed ledger: one record per file git tracks at the recorded commit.

    Records carry no timestamp: a tracked file is not "new and still unbilled", so no grace window applies.
    """

    def __init__(self, path: str = "tracked-files.csv", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._path = path

    @property
    def source(self) -> str:
        return f"git:{self._path}"

    def fetch(self) -> list[Record]:
        rows = read_csv(resolve_path(self._path, self._base_dir), ("file", "commit"))
        commits = {row["commit"] for row in rows}
        if len(commits) > 1:
            raise ValueError("tracked-files.csv names more than one commit")
        seen: set[str] = set()
        records: list[Record] = []
        for index, row in enumerate(rows, start=1):
            file = _file_of(row, index, "tracked-files.csv")
            if file in seen:
                raise ValueError(f"tracked-files.csv row {index}: '{file[:80]}' is listed twice")
            seen.add(file)
            records.append(self._record(f"git:{file}", file, {"commit": row["commit"][:12]}))
        return records


class KiroFiles(_FileConnector):
    """Billed ledger: one record per file Kiro worked on, with the credit shares summed across sessions.

    The amount is Kiro credits, and a session's credits are split equally across the files it touched: an allocation
    chosen for this audit, not a measurement. A blank share (the run stopped before it reported credits) is zero and
    the line is kept, so the file is still on the billed ledger. A line with no file name becomes an unkeyed record,
    and its credits are kept apart.
    """

    def __init__(self, files: str = "kiro-files.csv", sessions: str = "kiro-sessions.csv", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._files = files
        self._sessions = sessions

    @property
    def source(self) -> str:
        return f"kiro:{self._files}"

    def _models(self) -> dict[str, str]:
        """Each session's model, from the sessions export. A share naming an unknown session raises in ``fetch``."""
        rows = read_csv(resolve_path(self._sessions, self._base_dir), ("session", "started", "model", "credits"))
        models: dict[str, str] = {}
        for index, row in enumerate(rows, start=1):
            parse_time(row["started"], f"kiro-sessions.csv row {index} started")
            parse_credits(row["credits"], f"kiro-sessions.csv row {index} credits")
            models[row["session"]] = row["model"]
        return models

    def fetch(self) -> list[Record]:
        models = self._models()
        rows = read_csv(resolve_path(self._files, self._base_dir), ("file", "session", "credit_share", "started"))
        by_file: dict[str, list[tuple[str, Decimal | None, datetime | None]]] = {}
        unkeyed: list[Record] = []
        for index, row in enumerate(rows, start=1):
            where = f"kiro-files.csv row {index}"
            share = parse_credits(row["credit_share"], f"{where} credit_share")
            started = parse_time(row["started"], f"{where} started")
            if row["session"] not in models:
                raise ValueError(f"{where}: session '{row['session'][:60]}' is not in kiro-sessions.csv")
            file = canonical_path(row["file"])
            if not file:
                unkeyed.append(
                    self._record(
                        f"kiro:line-{index}",
                        "",
                        {"sessions": "1"},
                        amount=share if share is not None else Decimal(0),
                        timestamp=started,
                    )
                )
                continue
            by_file.setdefault(file, []).append((row["session"], share, started))
        records: list[Record] = []
        for file in sorted(by_file):
            lines = by_file[file]
            total = sum((share for _, share, _ in lines if share is not None), Decimal(0))
            starts = [s for _, _, s in lines if s is not None]
            last = max(starts) if starts else None
            used = sorted({models[session] for session, _, _ in lines if models[session]})
            unreported = sum(1 for _, share, _ in lines if share is None)
            records.append(
                self._record(
                    f"kiro:{file}",
                    file,
                    {
                        "sessions": str(len({session for session, _, _ in lines})),
                        "credits": credits_text(total),
                        "unreported_lines": str(unreported) if unreported else "",
                        "last_session_on": last.date().isoformat() if last else "",
                        "models": ", ".join(used),
                    },
                    amount=total,
                    timestamp=last,
                )
            )
        return records + unkeyed

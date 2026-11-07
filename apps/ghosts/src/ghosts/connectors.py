"""Read-only file connectors for the Ghosts app: the HR roster, the identity export and the paid seats.

Each connector reads a local CSV export and returns records for one ledger. A malformed export raises, so the skeleton
marks the ledger missing and the run produces no findings from damaged data (skeleton Req 9.4).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from nightaudit.connectors import Connector
from nightaudit.models import LedgerName, Record

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    """The real clock, the only place the app reads it. Tests inject their own."""
    return datetime.now(UTC)


def resolve_path(path: str | Path, base_dir: Path | None) -> Path:
    """A relative path is relative to the control file's directory, as for the skeleton's CSV connector."""
    candidate = Path(path)
    if candidate.is_absolute() or base_dir is None:
        return candidate
    return base_dir / candidate


def read_csv(path: Path) -> list[dict[str, str]]:
    """Every row of a CSV file as a dict of stripped strings."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None}
            for row in csv.DictReader(handle)
        ]


def parse_date(value: str, what: str) -> date | None:
    """An ISO date, or ``None`` when empty. Anything else raises: a roster with a bad date is not read."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{what}: '{value[:40]}' is not an ISO date") from None


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


def belongs_on(start: date | None, leaving: date | None, today: date) -> bool:
    """Whether a person belongs in the intended ledger on *today* (Req 2.1).

    A person belongs from their start date (inclusive) until their leaving date (exclusive): someone whose leaving date
    is today has left, and a joiner whose start date is after today has not started. No start date means started.
    """
    started = start is None or start <= today
    still_here = leaving is None or leaving > today
    return started and still_here


class _FileConnector(Connector):
    """Shared plumbing: the skeleton's constructor keywords, read-only declaration and record building."""

    def __init__(
        self,
        ledger: LedgerName,
        key_field: str = "",
        base_dir: Path | None = None,
        **_: Any,
    ) -> None:
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


class HrRoster(_FileConnector):
    """Intended ledger: one record per person who belongs on the run date, keyed by work email (Req 2).

    The run date is the UTC date of the run's time, which the skeleton gives every connector before ``fetch()``
    (skeleton Req 10.1). Used outside a run, it is the UTC date of the injected clock.
    """

    def __init__(self, path: str = "hr_roster.csv", clock: Clock = system_clock, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._path = path
        self._clock = clock
        #: Emails of people on the roster who do not belong on the run date (left, or not started).
        self.not_on_roster_today: list[str] = []

    @property
    def today(self) -> date:
        when = self.run_time if self.run_time is not None else self._clock()
        return when.astimezone(UTC).date()

    @property
    def source(self) -> str:
        return f"hr:{self._path}"

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        self.not_on_roster_today = []
        today = self.today
        for index, row in enumerate(read_csv(resolve_path(self._path, self._base_dir)), start=1):
            email = row.get("email", "")
            where = f"HR roster row {index}"
            start = parse_date(row.get("start_date", ""), f"{where} start_date")
            leaving = parse_date(row.get("leaving_date", ""), f"{where} leaving_date")
            if not belongs_on(start, leaving, today):
                self.not_on_roster_today.append(email)
                continue
            name = " ".join(p for p in (row.get("given_name", ""), row.get("family_name", "")) if p)
            records.append(
                self._record(
                    f"hr:{row.get('employee_id') or index}",
                    email,
                    {
                        "name": name,
                        "department": row.get("department", ""),
                        "title": row.get("title", ""),
                        "manager": row.get("manager_email", ""),
                        "employment_type": row.get("employment_type", ""),
                        "location": row.get("location", ""),
                        "start_date": row.get("start_date", ""),
                        "leaving_date": row.get("leaving_date", ""),
                    },
                )
            )
        return records


class IdentityExport(_FileConnector):
    """Observed ledger: one record per active account, keyed by email (Req 3.1).

    The timestamp is the account's creation time, so a new account whose seat is not billed yet is pending during the
    grace window instead of a finding.
    """

    def __init__(self, path: str = "identity_export.csv", system: str = "identity provider", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._path = path
        self._system = system

    @property
    def source(self) -> str:
        return f"identity:{self._path}"

    def fetch(self) -> list[Record]:
        records: list[Record] = []
        for index, row in enumerate(read_csv(resolve_path(self._path, self._base_dir)), start=1):
            status = row.get("status", "")
            if status.lower() != "active":
                continue
            where = f"identity export row {index}"
            created = parse_time(row.get("created", ""), f"{where} created")
            last_sign_in = row.get("last_sign_in", "")
            parse_time(last_sign_in, f"{where} last_sign_in")
            records.append(
                self._record(
                    f"identity:{row.get('account_id') or index}",
                    row.get("email", ""),
                    {
                        "system": self._system,
                        "status": status.lower(),
                        "last_sign_in": last_sign_in,
                        "display_name": row.get("display_name", ""),
                    },
                    timestamp=created,
                )
            )
        return records


def slug(name: str) -> str:
    """``Lantern Chat`` -> ``lantern-chat``."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True)
class Invoice:
    """The invoice that prices a vendor's seats."""

    invoice_id: str
    vendor: str
    period: str
    seats: int
    unit_price: Decimal
    currency: str


_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def latest_invoice(rows: list[dict[str, str]], vendor: str, where: str) -> Invoice:
    """The vendor's invoice with the latest period. Every row must name the vendor and parse."""
    invoices: list[Invoice] = []
    for index, row in enumerate(rows, start=1):
        at = f"{where} row {index}"
        if row.get("vendor", "") != vendor:
            raise ValueError(f"{at}: invoice is for '{row.get('vendor', '')[:60]}', not '{vendor}'")
        period = row.get("period", "")
        if not _PERIOD.match(period):
            raise ValueError(f"{at}: period '{period[:20]}' is not YYYY-MM")
        try:
            seats = int(row.get("seat_quantity", ""))
            price = Decimal(row.get("unit_price", ""))
        except (ValueError, InvalidOperation):
            raise ValueError(f"{at}: seat_quantity and unit_price must be numbers") from None
        if seats < 0 or not price.is_finite() or price < 0:
            raise ValueError(f"{at}: seat_quantity and unit_price must not be negative")
        invoices.append(Invoice(row.get("invoice_id", ""), vendor, period, seats, price, row.get("currency", "")))
    if not invoices:
        raise ValueError(f"{where}: no invoice for '{vendor}'")
    periods = [i.period for i in invoices]
    latest = max(periods)
    if periods.count(latest) > 1:
        raise ValueError(f"{where}: more than one invoice for period {latest}")
    return next(i for i in invoices if i.period == latest)


class SeatAssignments(_FileConnector):
    """Billed ledger for one vendor: each licence assignment at the invoice's unit price (Req 4.1).

    Seats on the invoice beyond the assignments are unkeyed records, paid for nobody named (Req 4.2). Fewer seats on
    the invoice than assignments is reported by the seat summary (Req 4.3); every record carries the counts it needs.
    """

    def __init__(self, vendor: str, assignments: str, invoice: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._vendor = vendor
        self._assignments = assignments
        self._invoice = invoice

    @property
    def source(self) -> str:
        return f"seats:{slug(self._vendor)}"

    def fetch(self) -> list[Record]:
        invoice = latest_invoice(
            read_csv(resolve_path(self._invoice, self._base_dir)), self._vendor, f"invoice {self._invoice}"
        )
        assigned = read_csv(resolve_path(self._assignments, self._base_dir))
        prefix = slug(self._vendor)
        common = {
            "vendor": self._vendor,
            "invoice_id": invoice.invoice_id,
            "period": invoice.period,
            "invoice_seats": str(invoice.seats),
            "assigned_seats": str(len(assigned)),
            # The gaps themselves, so a note that cites them cites evidence (skeleton Req 10.2, audit rule 2).
            "unnamed_seats": str(max(0, invoice.seats - len(assigned))),
            "short_seats": str(max(0, len(assigned) - invoice.seats)),
            "unit_price": str(invoice.unit_price),
        }
        records: list[Record] = []
        for index, row in enumerate(assigned, start=1):
            attrs = dict(common)
            attrs["assigned_on"] = row.get("assigned_on", "")
            records.append(
                self._record(f"{prefix}:{row.get('seat_id') or index}", row.get("email", ""), attrs,
                             amount=invoice.unit_price)
            )
        for n in range(1, invoice.seats - len(assigned) + 1):
            records.append(self._record(f"{prefix}:unnamed-{n}", "", dict(common), amount=invoice.unit_price))
        return records

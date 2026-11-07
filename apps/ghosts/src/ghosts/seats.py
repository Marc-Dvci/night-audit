"""Seat summary: each vendor's invoice against its licence assignments (Req 4.2, 4.3).

The summary is computed only from the run's billed records, whose attributes carry the invoice and assignment counts,
so the evidence pack alone is enough to recompute it. ``seat_notes`` is the control's summariser: it states each gap
as a sentence, and the skeleton adds those sentences to the run as notes, inside the evidence chain (skeleton
Req 10.2). Every number a note cites is an attribute of a billed record.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from nightaudit.models import LedgerName, RunResult
from pydantic import BaseModel, Field


class VendorSeats(BaseModel):
    """One vendor's invoice against its assignments."""

    vendor: str
    invoice_id: str
    period: str
    unit_price: Decimal
    invoice_seats: int
    assigned_seats: int
    #: Seats on the invoice that no assignment names (emitted as unkeyed billed records).
    unnamed_seats: int
    #: Assignments beyond the invoice quantity.
    short_seats: int


class SeatSummary(BaseModel):
    """The seat summary of one run."""

    run_id: str
    vendors: list[VendorSeats] = Field(default_factory=list)

    @property
    def below_assignments(self) -> list[VendorSeats]:
        """Vendors whose invoice is lower than their number of assignments."""
        return [v for v in self.vendors if v.short_seats > 0]


def seat_summary(result: RunResult) -> SeatSummary:
    """Rebuild each vendor's invoice and assignment counts from the run's billed records."""
    seen: dict[tuple[str, str], VendorSeats] = {}
    for snapshot in result.snapshots:
        if snapshot.name != LedgerName.billed:
            continue
        for record in snapshot.records:
            attrs = record.attrs
            if "invoice_seats" not in attrs or "assigned_seats" not in attrs:
                continue
            vendor_key = (attrs.get("vendor", ""), attrs.get("invoice_id", ""))
            if vendor_key in seen:
                continue
            invoice, assigned = int(attrs["invoice_seats"]), int(attrs["assigned_seats"])
            seen[vendor_key] = VendorSeats(
                vendor=vendor_key[0],
                invoice_id=vendor_key[1],
                period=attrs.get("period", ""),
                unit_price=Decimal(attrs.get("unit_price", record.amount or 0)),
                invoice_seats=invoice,
                assigned_seats=assigned,
                unnamed_seats=max(0, invoice - assigned),
                short_seats=max(0, assigned - invoice),
            )
    vendors = [seen[k] for k in sorted(seen)]
    return SeatSummary(run_id=result.run_id, vendors=vendors)


def _seats(n: int) -> str:
    return f"{n} more seat" if n == 1 else f"{n} more seats"


def _names(vendors: list[str]) -> str:
    return vendors[0] if len(vendors) == 1 else ", ".join(vendors[:-1]) + " and " + vendors[-1]


def summary_lines(summary: SeatSummary) -> list[str]:
    """The seat summary as plain sentences: one per vendor with a gap, then the vendors whose invoice matches."""
    lines: list[str] = []
    for v in summary.vendors:
        if v.unnamed_seats:
            lines.append(
                f"{v.vendor} invoices {_seats(v.unnamed_seats)} than it assigns "
                f"({v.invoice_seats} invoiced, {v.assigned_seats} assigned)."
            )
        if v.short_seats:
            lines.append(
                f"{v.vendor} assigns {_seats(v.short_seats)} than its invoice pays for "
                f"({v.invoice_seats} invoiced, {v.assigned_seats} assigned)."
            )
    exact = [v.vendor for v in summary.vendors if not v.unnamed_seats and not v.short_seats]
    if exact:
        verb = "invoices" if len(exact) == 1 else "invoice"
        lines.append(f"{_names(exact)} {verb} exactly the seats {'it assigns' if len(exact) == 1 else 'they assign'}.")
    return lines


def seat_notes(result: RunResult, options: dict[str, Any]) -> list[str]:
    """Summariser (skeleton Req 10.2): the seat summary as run notes."""
    return summary_lines(seat_summary(result))

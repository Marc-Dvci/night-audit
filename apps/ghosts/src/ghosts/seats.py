"""Seat summary: each vendor's invoice against its licence assignments (Req 4.2, 4.3).

``RunResult`` has no field for an application's own run-level notes, so the summary is a file written beside the run,
``runs/<run_id>/seats.json``. It is computed only from the run's billed records, whose attributes carry the invoice
and assignment counts, so the evidence pack alone is enough to recompute it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from nightaudit.models import LedgerName, RunResult
from pydantic import BaseModel, Field

SUMMARY_FILE = "seats.json"


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
    """The seat summary of one run, bound to its evidence chain."""

    run_id: str
    evidence_chain_hash: str | None
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
    return SeatSummary(run_id=result.run_id, evidence_chain_hash=result.evidence_chain_hash, vendors=vendors)


def write_seat_summary(result: RunResult, run_dir: Path) -> Path:
    """Write ``seats.json`` beside the run and return its path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / SUMMARY_FILE
    path.write_text(seat_summary(result).model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def summary_lines(summary: SeatSummary) -> list[str]:
    """The seat summary as sentences for the terminal."""
    lines: list[str] = []
    for v in summary.vendors:
        line = f"{v.vendor} {v.period}: invoice for {v.invoice_seats} seats, {v.assigned_seats} assigned"
        if v.unnamed_seats:
            line += f"; {v.unnamed_seats} paid for nobody named"
        if v.short_seats:
            line += f"; {v.short_seats} assigned beyond the invoice"
        lines.append(line)
    return lines

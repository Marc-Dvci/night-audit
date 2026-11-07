"""Seats are conserved and an invoice below its assignments is reported beside the run (Req 4.1, 4.2, 4.3)."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ghosts.connectors import SeatAssignments
from ghosts.run import main as run_main
from ghosts.seats import seat_summary
from ghosts_testkit import FIXTURES, control_for
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.evidence import verify_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot
from nightaudit.runner import load_run

PEOPLE = ControlConfig(normalisers={n: ["email_canonical"] for n in ("intended", "observed", "billed")})


def test_an_invoice_below_its_assignments_is_a_note_in_the_run_and_its_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control = control_for(FIXTURES, tmp_path)
    code = run_main([str(control), "--runs", str(tmp_path / "runs"), "--at", "2026-11-04T02:00:00Z"])
    out = capsys.readouterr().out
    assert code == 0
    (run_dir,) = [p for p in (tmp_path / "runs").iterdir() if (p / "result.json").exists()]
    result = load_run(tmp_path / "runs", run_dir.name)
    assert result.ledger_errors == {}
    notes = [n.text for n in result.notes]
    assert notes == [
        "Crypt Docs assigns 1 more seat than its invoice pays for (2 invoiced, 3 assigned).",
        "Lantern Chat invoices 3 more seats than it assigns (5 invoiced, 2 assigned).",
        "Belfry CRM invoices exactly the seats it assigns.",
    ]
    assert all(n.source == "ghosts.seats:seat_notes" for n in result.notes)
    rows = [json.loads(line) for line in (run_dir / "evidence" / "evidence.jsonl").read_text("utf-8").splitlines()]
    assert [r["text"] for r in rows if r["type"] == "note"] == notes
    assert verify_evidence_pack(run_dir / "evidence").ok
    assert not (run_dir / "seats.json").exists()
    assert {"review.csv", "review.html"} <= {p.name for p in run_dir.iterdir()}
    for note in notes:
        assert note in out


def write_vendor(folder: Path, assigned: int, invoiced: int, price: Decimal) -> SeatAssignments:
    (folder / "a.csv").write_text(
        "seat_id,email,assigned_on\n" + "".join(f"S{i},p{i}@hollowpines.com,2026-01-01\n" for i in range(assigned)),
        encoding="utf-8",
    )
    (folder / "i.csv").write_text(
        f"invoice_id,vendor,period,seat_quantity,unit_price,currency\nINV,Crypt Docs,2026-10,{invoiced},{price},USD\n",
        encoding="utf-8",
    )
    return SeatAssignments(ledger=LedgerName.billed, base_dir=folder, vendor="Crypt Docs", assignments="a.csv",
                           invoice="i.csv")


@pytest.mark.property
@given(
    assigned=st.integers(min_value=0, max_value=40),
    invoiced=st.integers(min_value=0, max_value=40),
    price=st.decimals(min_value=Decimal("0"), max_value=Decimal("999.99"), places=2),
)
def test_property_seats_are_conserved(assigned: int, invoiced: int, price: Decimal) -> None:
    """G3 (Req 4.1-4.3): a keyed records, max(0, q-a) unkeyed, each at the unit price; the summary reports both gaps."""
    with tempfile.TemporaryDirectory() as folder:
        records = write_vendor(Path(folder), assigned, invoiced, price).fetch()
    keyed = [r for r in records if r.raw_key]
    unkeyed = [r for r in records if not r.raw_key]
    assert len(keyed) == assigned
    assert len(unkeyed) == max(0, invoiced - assigned)
    assert {r.amount for r in records} <= {price}

    result = match(
        [
            LedgerSnapshot(name=LedgerName.intended, source="i"),
            LedgerSnapshot(name=LedgerName.observed, source="o"),
            LedgerSnapshot(name=LedgerName.billed, source="b", records=records),
        ],
        PEOPLE,
        datetime(2026, 11, 4, 2, 0, tzinfo=UTC),
    )
    assert result.billed_total == price * max(assigned, invoiced)
    assert result.billed_unkeyed == price * max(0, invoiced - assigned)
    assert len([u for u in result.unkeyed if u.ledger == LedgerName.billed]) == max(0, invoiced - assigned)
    summary = seat_summary(result)
    if records:
        (vendor,) = summary.vendors
        assert vendor.unnamed_seats == max(0, invoiced - assigned)
        assert vendor.short_seats == max(0, assigned - invoiced)
        assert [v.vendor for v in summary.below_assignments] == (["Crypt Docs"] if assigned > invoiced else [])
    else:
        assert summary.vendors == []  # nothing invoiced and nothing assigned

"""Contract tests: each Ghosts file connector loads its recorded fixture (Req 2, 3.1, 4.1, 4.2)."""

from __future__ import annotations

import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from ghosts.connectors import HrRoster, IdentityExport, SeatAssignments, belongs_on
from ghosts_testkit import on
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.models import LedgerName

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RUN_DATE = date(2026, 11, 4)


def roster(today: str | None = "2026-11-04", **kwargs: Any) -> HrRoster:
    connector = HrRoster(ledger=LedgerName.intended, base_dir=FIXTURES, path="hr_roster.csv", **kwargs)
    return on(today, connector) if today else connector


def seats(vendor: str) -> SeatAssignments:
    name = vendor.lower().replace(" ", "-")
    return SeatAssignments(
        ledger=LedgerName.billed,
        base_dir=FIXTURES,
        vendor=vendor,
        assignments=f"licences/{name}.csv",
        invoice=f"invoices/{name}.csv",
    )


def write_roster(tmp_path: Path, start: str, leaving: str) -> Path:
    path = tmp_path / "roster.csv"
    path.write_text(
        "employee_id,email,given_name,family_name,start_date,leaving_date\n"
        f"E1,x.person@hollowpines.com,X,Person,{start},{leaving}\n",
        encoding="utf-8",
    )
    return path


# --- HR roster (Req 2) ------------------------------------------------------------------------------------------------


def test_the_roster_emits_everyone_who_belongs_on_the_run_date_keyed_by_work_email() -> None:
    connector = roster()
    records = connector.fetch()
    assert [r.raw_key for r in records] == [
        "a.thornfield@hollowpines.com",
        "b.quill@hollowpines.com",
        "e.ashby@hollowpines.com",
        "f.lowe@hollowpines.com",
    ]
    assert connector.read_only and connector.ledger == LedgerName.intended
    assert all(r.ledger == LedgerName.intended and r.timestamp is None for r in records)
    bram = records[1]
    assert bram.row_id == "hr:E0002"
    assert bram.attrs["name"] == "Bram Quill"
    assert bram.attrs["manager"] == "a.thornfield@hollowpines.com"
    assert bram.attrs["department"] == "IT"


def test_people_who_do_not_belong_are_not_emitted_and_are_listed() -> None:
    connector = roster()
    connector.fetch()
    assert connector.not_on_roster_today == [
        "c.wren@hollowpines.com",  # contract ended 2026-06-30
        "d.marlow@hollowpines.com",  # leaves on the run date
        "g.okoro@hollowpines.com",  # starts the day after
        "h.vale@hollowpines.com",  # started and left before
    ]


def test_a_future_leaving_date_keeps_the_person_and_their_leaving_date() -> None:
    (esme,) = [r for r in roster().fetch() if r.raw_key == "e.ashby@hollowpines.com"]
    assert esme.attrs["leaving_date"] == "2026-11-05"


@pytest.mark.parametrize(
    ("leaving", "belongs"),
    [("2026-11-03", False), ("2026-11-04", False), ("2026-11-05", True)],
    ids=["leaving-before", "leaving-at", "leaving-after"],
)
def test_leaving_date_boundary(tmp_path: Path, leaving: str, belongs: bool) -> None:
    path = write_roster(tmp_path, "2020-01-01", leaving)
    records = on("2026-11-04", HrRoster(ledger=LedgerName.intended, path=str(path))).fetch()
    assert bool(records) is belongs


@pytest.mark.parametrize(
    ("start", "belongs"),
    [("2026-11-03", True), ("2026-11-04", True), ("2026-11-05", False)],
    ids=["start-before", "start-at", "start-after"],
)
def test_start_date_boundary(tmp_path: Path, start: str, belongs: bool) -> None:
    path = write_roster(tmp_path, start, "")
    records = on("2026-11-04", HrRoster(ledger=LedgerName.intended, path=str(path))).fetch()
    assert bool(records) is belongs


def test_outside_a_run_the_run_date_comes_from_the_clock() -> None:
    connector = roster(today=None, clock=lambda: datetime(2026, 11, 5, 23, 30, tzinfo=UTC))
    assert connector.today == date(2026, 11, 5)
    assert "e.ashby@hollowpines.com" not in [r.raw_key for r in connector.fetch()]


def test_the_run_time_wins_over_the_clock() -> None:
    connector = on("2026-11-04", roster(today=None, clock=lambda: datetime(2031, 1, 1, tzinfo=UTC)))
    assert connector.today == date(2026, 11, 4)
    assert "e.ashby@hollowpines.com" in [r.raw_key for r in connector.fetch()]


def test_a_roster_with_a_bad_date_is_not_read(tmp_path: Path) -> None:
    path = write_roster(tmp_path, "2020-01-01", "12/09/2026")
    with pytest.raises(ValueError, match="leaving_date"):
        on("2026-11-04", HrRoster(ledger=LedgerName.intended, path=str(path))).fetch()


dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))


@pytest.mark.property
@given(start=st.none() | dates, leaving=st.none() | dates, today=dates)
def test_property_intended_membership_follows_the_run_date(
    start: date | None, leaving: date | None, today: date
) -> None:
    """G1 (Req 2.1, 2.2): the roster connector emits a person if and only if the run date lies in [start, leaving)."""
    with tempfile.TemporaryDirectory() as folder:
        path = write_roster(Path(folder), start.isoformat() if start else "", leaving.isoformat() if leaving else "")
        connector = on(today.isoformat(), HrRoster(ledger=LedgerName.intended, path=str(path)))
        emitted = bool(connector.fetch())
    first_day = start or date.min
    after_last_day = leaving or date.max
    assert emitted is (first_day <= today < after_last_day)
    assert emitted is belongs_on(start, leaving, today)
    assert emitted is not bool(connector.not_on_roster_today)


# --- Identity export (Req 3.1) ----------------------------------------------------------------------------------------


def test_the_identity_export_emits_active_accounts_with_system_status_and_last_sign_in() -> None:
    connector = IdentityExport(
        ledger=LedgerName.observed, base_dir=FIXTURES, path="identity_export.csv", system="Hollow Pines directory"
    )
    records = connector.fetch()
    assert connector.read_only and connector.ledger == LedgerName.observed
    assert [r.raw_key for r in records] == [
        "a.thornfield@hollowpines.com",
        "B.Quill+admin@HollowPines.org",
        "svc-backup@hollowpines.com",
    ]
    ada = records[0]
    assert ada.row_id == "identity:u-1001"
    assert ada.attrs == {
        "system": "Hollow Pines directory",
        "status": "active",
        "last_sign_in": "2026-11-03T08:12:00Z",
        "display_name": "Ada Thornfield",
    }
    assert ada.timestamp == datetime(2019, 2, 28, 9, 0, tzinfo=UTC)
    assert records[2].timestamp == datetime(2024, 4, 10, tzinfo=UTC)  # naive time is UTC
    assert "last_sign_in" not in records[2].attrs  # never signed in


def test_a_malformed_creation_time_stops_the_ledger(tmp_path: Path) -> None:
    path = tmp_path / "ids.csv"
    path.write_text("account_id,email,status,created,last_sign_in\nu1,a@b.c,active,yesterday,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="created"):
        IdentityExport(ledger=LedgerName.observed, path=str(path)).fetch()


# --- Seats (Req 4.1, 4.2) ---------------------------------------------------------------------------------------------


def test_each_assignment_is_billed_at_the_latest_invoices_unit_price() -> None:
    records = seats("Lantern Chat").fetch()
    named = [r for r in records if r.raw_key]
    assert [(r.row_id, r.raw_key, r.amount) for r in named] == [
        ("lantern-chat:LC-0001", "a.thornfield@hollowpines.com", Decimal("8.00")),
        ("lantern-chat:LC-0002", "b.quill@hollowpines.org", Decimal("8.00")),
    ]
    assert named[0].attrs["vendor"] == "Lantern Chat"
    assert named[0].attrs["invoice_id"] == "LC-2026-10"  # the latest period, not September
    assert named[0].attrs["invoice_seats"] == "5"
    assert named[0].attrs["assigned_seats"] == "2"


def test_seats_on_the_invoice_beyond_the_assignments_are_unkeyed_records() -> None:
    unnamed = [r for r in seats("Lantern Chat").fetch() if not r.raw_key]
    assert [r.row_id for r in unnamed] == ["lantern-chat:unnamed-1", "lantern-chat:unnamed-2", "lantern-chat:unnamed-3"]
    assert {r.amount for r in unnamed} == {Decimal("8.00")}
    assert all(r.ledger == LedgerName.billed for r in unnamed)


def test_an_invoice_below_its_assignments_still_bills_every_assignment() -> None:
    records = seats("Crypt Docs").fetch()
    assert len(records) == 3 and all(r.raw_key for r in records)
    assert {r.attrs["invoice_seats"] for r in records} == {"2"}
    assert {r.attrs["assigned_seats"] for r in records} == {"3"}


def test_an_invoice_equal_to_its_assignments_has_no_unnamed_seat() -> None:
    records = seats("Belfry CRM").fetch()
    assert [(r.raw_key, r.amount) for r in records] == [("e.ashby@hollowpines.com", Decimal("45.00"))]


def test_an_invoice_for_another_vendor_stops_the_ledger() -> None:
    connector = SeatAssignments(
        ledger=LedgerName.billed,
        base_dir=FIXTURES,
        vendor="Crypt Docs",
        assignments="licences/crypt-docs.csv",
        invoice="invoices/belfry-crm.csv",
    )
    with pytest.raises(ValueError, match="not 'Crypt Docs'"):
        connector.fetch()

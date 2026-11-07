"""The Hollow Pines generator is seeded, deterministic and plants exactly the written findings (Req 6.1, 6.2)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from ghosts.acceptance import load_planted
from ghosts.connectors import HrRoster
from ghosts.generate import (
    DEFAULT_SEED,
    FAMILY_NAMES,
    GIVEN_NAMES,
    VENDORS,
    build_company,
    main,
)
from ghosts_testkit import APP, DATA, on
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.models import LedgerName

PLANTED = load_planted(APP / "planted.yaml")
PLANTED_NAMES = {
    ("Jonah", "Marsh"),
    ("Petra", "Lindqvist"),
    ("Rowan", "Voss"),
    ("Elena", "Castell"),
    ("Noor", "Haddad"),
    ("Nadia", "Haddad"),
}


def rows(files: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(files[name].decode("utf-8"))))


FILES = build_company()
ROSTER = {r["email"]: r for r in rows(FILES, "hr_roster.csv")}
IDENTITY = rows(FILES, "identity_export.csv")
SEATS = {v.name: rows(FILES, f"licences/{v.slug}.csv") for v in VENDORS}
INVOICES = {v.name: rows(FILES, f"invoices/{v.slug}.csv")[-1] for v in VENDORS}


def accounts_of(email: str) -> list[dict[str, str]]:
    return [a for a in IDENTITY if a["email"].lower().replace("+old", "").replace(".org", ".com") == email]


def seats_of(email: str) -> set[str]:
    return {vendor for vendor, held in SEATS.items() if any(s["email"] == email for s in held)}


def test_the_committed_data_is_the_generators_output_for_the_default_seed() -> None:
    committed = {str(p.relative_to(DATA)).replace("\\", "/"): p.read_bytes() for p in DATA.rglob("*.csv")}
    assert committed == FILES, f"run: uv run python -m ghosts.generate --seed {DEFAULT_SEED}"


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_property_the_same_seed_gives_the_same_bytes(seed: int) -> None:
    """G6 (Req 6.2): two builds with one seed are byte-identical, healthy or planted."""
    assert build_company(seed) == build_company(seed)
    assert build_company(seed, plant=False) == build_company(seed, plant=False)


def test_180_people_belong_on_the_run_date() -> None:
    records = on(PLANTED["run_date"], HrRoster(ledger=LedgerName.intended, path=str(DATA / "hr_roster.csv"))).fetch()
    assert len(records) == PLANTED["staff_total"] == 180
    assert len({r.raw_key for r in records}) == 180


def test_every_department_has_a_head_and_every_manager_is_on_the_roster() -> None:
    for person in ROSTER.values():
        if person["manager_email"]:
            assert person["manager_email"] in ROSTER
    heads = [p for p in ROSTER.values() if p["title"].startswith("Head of ")]
    assert len(heads) == 10
    assert sum(1 for p in ROSTER.values() if not p["manager_email"]) == 1  # the chief executive


def test_every_name_and_vendor_is_from_the_fictional_pools() -> None:
    for person in ROSTER.values():
        pair = (person["given_name"], person["family_name"])
        assert pair in PLANTED_NAMES or (pair[0] in GIVEN_NAMES and pair[1] in FAMILY_NAMES)
    assert [(v.name, v.unit_price) for v in VENDORS] == [(v["name"], v["unit_price"]) for v in PLANTED["vendors"]]
    assert {i["vendor"] for i in INVOICES.values()} == {v["name"] for v in PLANTED["vendors"]}
    domains = {r["email"].lower().split("@")[1] for r in IDENTITY} | {e.split("@")[1] for e in ROSTER}
    assert domains == {"hollowpines.com", "hollowpines.org"}


def test_the_ghosts_are_planted_as_their_stories_say() -> None:
    marsh = ROSTER["j.marsh@hollowpines.com"]
    assert marsh["leaving_date"] == "2026-09-12"
    (account,) = accounts_of("j.marsh@hollowpines.com")
    assert (account["status"], account["last_sign_in"]) == ("active", "2026-10-30T19:42:00Z")
    assert seats_of("j.marsh@hollowpines.com") == {"Crypt Docs", "Belfry CRM"}

    lindqvist = ROSTER["p.lindqvist@hollowpines.com"]
    assert (lindqvist["employment_type"], lindqvist["leaving_date"]) == ("contractor", "2026-06-30")
    assert [a["status"] for a in accounts_of("p.lindqvist@hollowpines.com")] == ["active"]
    assert seats_of("p.lindqvist@hollowpines.com") == {"Lantern Chat"}

    assert ROSTER["r.voss@hollowpines.com"]["leaving_date"] == "2026-08-01"
    assert [a["email"] for a in IDENTITY if "voss" in a["email"].lower()] == ["R.Voss+old@hollowpines.org"]
    assert seats_of("r.voss@hollowpines.com") == {"Ossuary Design"}


def test_the_other_planted_findings_are_planted_as_their_stories_say() -> None:
    for service in ("svc-reporting@hollowpines.com", "test.admin@hollowpines.com"):
        assert service not in ROSTER and seats_of(service) == set()
        assert [a["status"] for a in accounts_of(service)] == ["active"]
    assert accounts_of("test.admin@hollowpines.com")[0]["created"].startswith("2025-")

    assert seats_of("temp.contractor@hollowpines.com") == {"Belfry CRM"}
    assert "temp.contractor@hollowpines.com" not in ROSTER and not accounts_of("temp.contractor@hollowpines.com")

    assert ROSTER["noor.haddad@hollowpines.com"]["start_date"] == "2026-11-02"
    assert not accounts_of("noor.haddad@hollowpines.com") and seats_of("noor.haddad@hollowpines.com") == set()

    assert ROSTER["e.castell@hollowpines.com"]["leaving_date"] == ""
    assert not accounts_of("e.castell@hollowpines.com") and seats_of("e.castell@hollowpines.com") == {"Crypt Docs"}


def test_only_lantern_chat_invoices_seats_nobody_is_assigned() -> None:
    gaps = {vendor: int(INVOICES[vendor]["seat_quantity"]) - len(SEATS[vendor]) for vendor in SEATS}
    expected = {row["vendor"]: row["quantity"] for row in PLANTED["unnamed_phantom_seats"]}
    assert gaps == {v.name: expected.get(v.name, 0) for v in VENDORS}


def test_the_healthy_company_plants_nothing() -> None:
    healthy = build_company(plant=False)
    text = b"".join(healthy.values())
    for key in (p["key"] for p in PLANTED["planted"]):
        assert key.split("@")[0].encode() not in text.lower()
    for vendor in VENDORS:
        seats = rows(healthy, f"licences/{vendor.slug}.csv")
        assert int(rows(healthy, f"invoices/{vendor.slug}.csv")[-1]["seat_quantity"]) == len(seats)


@pytest.mark.integration
def test_healthy_output_needs_an_explicit_folder(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--healthy"])
    assert "--healthy needs --out" in capsys.readouterr().err


@pytest.mark.integration
def test_the_cli_writes_the_files(tmp_path: Path) -> None:
    assert main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / "hr_roster.csv").read_bytes() == FILES["hr_roster.csv"]

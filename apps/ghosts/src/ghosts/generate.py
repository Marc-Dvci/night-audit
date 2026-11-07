"""Seeded generator for Hollow Pines Credit Union, the demo company (Req 6).

``python -m ghosts.generate [--seed N] [--out DIR] [--healthy]`` writes the HR roster, the identity export, the
licence assignments and the invoices. The same seed gives the same bytes: the generator uses ``random.Random(seed)``,
never the clock, and writes UTF-8 CSV with ``\\n`` line endings. It depends only on the standard library.

The planted findings of ``apps/ghosts/planted.yaml`` (written before this generator) are planted here explicitly, with
the dates, systems and seats their stories give. Everything else is a healthy company that must produce no finding:
the healthy mode (``plant=False``) writes the same company without the planted cases, with a seat for everyone.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

RUN_DATE = date(2026, 11, 4)
RUN_TIME = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
DEFAULT_SEED = 20261104
DOMAIN = "hollowpines.com"
ALIAS_DOMAIN = "hollowpines.org"
APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT = APP_DIR / "data"
PERIOD = "2026-10"
PREVIOUS_PERIOD = "2026-09"


@dataclass(frozen=True)
class Vendor:
    name: str
    slug: str
    prefix: str
    unit_price: str


VENDORS: tuple[Vendor, ...] = (
    Vendor("Lantern Chat", "lantern-chat", "LC", "8.00"),
    Vendor("Crypt Docs", "crypt-docs", "CD", "12.00"),
    Vendor("Belfry CRM", "belfry-crm", "BC", "45.00"),
    Vendor("Ossuary Design", "ossuary-design", "OD", "22.00"),
)
LANTERN, CRYPT, BELFRY, OSSUARY = (v.name for v in VENDORS)

#: Lantern Chat invoices this many seats more than it has assignments (planted.yaml: unnamed_phantom_seats).
UNNAMED_LANTERN_SEATS = 3

GIVEN_NAMES: tuple[str, ...] = (
    "Aaron",
    "Abby",
    "Adele",
    "Alma",
    "Amir",
    "Anika",
    "Ben",
    "Bianca",
    "Caleb",
    "Carmen",
    "Chloe",
    "Colin",
    "Dalia",
    "Daniel",
    "Dara",
    "Eamon",
    "Edith",
    "Elias",
    "Ellen",
    "Farah",
    "Felix",
    "Fiona",
    "Gareth",
    "Greta",
    "Hamid",
    "Hannah",
    "Hugo",
    "Ines",
    "Ivan",
    "Jada",
    "Jasper",
    "Joanna",
    "Kai",
    "Karin",
    "Kofi",
    "Lara",
    "Leon",
    "Lina",
    "Lucas",
    "Maeve",
    "Malik",
    "Marta",
    "Mateo",
    "Mila",
    "Nadine",
    "Nikhil",
    "Nora",
    "Oliver",
    "Omar",
    "Orla",
    "Pablo",
    "Priya",
    "Quentin",
    "Rafael",
    "Rhea",
    "Rosa",
    "Samir",
    "Sanna",
    "Simon",
    "Sofia",
    "Tariq",
    "Tessa",
    "Theo",
    "Uma",
    "Victor",
    "Wanda",
    "Wes",
    "Yara",
    "Yusuf",
    "Zoe",
)
FAMILY_NAMES: tuple[str, ...] = (
    "Abbott",
    "Adeyemi",
    "Alder",
    "Arden",
    "Ashdown",
    "Bale",
    "Barrow",
    "Beck",
    "Birch",
    "Blackwood",
    "Bramley",
    "Brook",
    "Calder",
    "Carrow",
    "Chandra",
    "Colby",
    "Crane",
    "Dale",
    "Darrow",
    "Delacroix",
    "Dunmore",
    "Ellery",
    "Fairley",
    "Farrant",
    "Fenn",
    "Finch",
    "Garland",
    "Glenn",
    "Greaves",
    "Hale",
    "Harlow",
    "Hartley",
    "Heath",
    "Holloway",
    "Hurst",
    "Ingram",
    "Jarvis",
    "Keane",
    "Kestrel",
    "Kimura",
    "Lang",
    "Larkin",
    "Lomax",
    "Lund",
    "Maddox",
    "Mercer",
    "Moreau",
    "Nakamura",
    "Nash",
    "Nolan",
    "Oakley",
    "Okafor",
    "Orme",
    "Pace",
    "Pell",
    "Pryor",
    "Quarry",
    "Radley",
    "Reyes",
    "Rook",
    "Rowe",
    "Sable",
    "Santos",
    "Sedge",
    "Shaw",
    "Sorensen",
    "Stroud",
    "Tamsin",
    "Teague",
    "Thorne",
    "Tilly",
    "Upton",
    "Vance",
    "Varga",
    "Wade",
    "Warrick",
    "Weller",
    "Whitlock",
    "Wilde",
    "Yates",
    "Yoon",
    "Zeller",
)
BRANCHES: tuple[str, ...] = ("Mossbank Branch", "Fernhollow Branch", "Old Quarry Branch", "Larkspur Branch")
HEAD_OFFICE = "Head Office"


@dataclass(frozen=True)
class Department:
    name: str
    size: int
    titles: tuple[str, ...]
    chief: str
    branch_based: bool
    seats: tuple[str, ...]


#: 180 people on the run date across eleven departments. ``chief`` is the executive the head reports to.
DEPARTMENTS: tuple[Department, ...] = (
    Department(
        "Member Services",
        40,
        ("Member Advisor", "Senior Member Advisor", "Contact Centre Agent"),
        "COO",
        True,
        (LANTERN, BELFRY),
    ),
    Department("Branch Operations", 35, ("Teller", "Senior Teller"), "COO", True, (LANTERN,)),
    Department(
        "Lending",
        30,
        ("Loan Officer", "Mortgage Advisor", "Underwriter", "Lending Assistant"),
        "COO",
        True,
        (LANTERN, CRYPT, BELFRY),
    ),
    Department("Card Services", 8, ("Card Operations Analyst", "Disputes Specialist"), "COO", False, (LANTERN, BELFRY)),
    Department("Collections", 10, ("Collections Specialist",), "COO", False, (LANTERN, BELFRY)),
    Department("Finance", 12, ("Accountant", "Financial Analyst", "Payroll Officer"), "CFO", False, (LANTERN, CRYPT)),
    Department(
        "Risk and Compliance",
        12,
        ("Compliance Analyst", "Risk Analyst", "Internal Auditor"),
        "CRO",
        False,
        (LANTERN, CRYPT),
    ),
    Department(
        "IT",
        14,
        ("Systems Engineer", "Service Desk Analyst", "Network Engineer", "Security Analyst", "Developer"),
        "CIO",
        False,
        (LANTERN, CRYPT),
    ),
    Department(
        "Marketing", 8, ("Marketing Specialist", "Designer", "Content Writer"), "COO", False, (LANTERN, CRYPT, OSSUARY)
    ),
    Department("People", 6, ("HR Advisor", "Recruiter"), "COO", False, (LANTERN, CRYPT)),
)
EXECUTIVES: tuple[tuple[str, str], ...] = (
    ("CEO", "Chief Executive Officer"),
    ("COO", "Chief Operating Officer"),
    ("CFO", "Chief Financial Officer"),
    ("CRO", "Chief Risk Officer"),
    ("CIO", "Chief Information Officer"),
)
EXECUTIVE_SEATS = (LANTERN, CRYPT)
PART_TIME_TELLERS = 4


@dataclass(frozen=True)
class Preset:
    """A person the story needs, placed in a department's staff before the random ones."""

    given: str
    family: str
    email: str
    title: str
    start: date
    #: ``None`` means the department's seats.
    seats: tuple[str, ...] | None = None
    has_account: bool = True


@dataclass
class Person:
    employee_id: str
    given: str
    family: str
    email: str
    department: str
    title: str
    manager_email: str
    employment_type: str
    location: str
    start: date
    leaving: date | None = None
    github_login: str = ""
    seats: list[str] = field(default_factory=list)
    #: How this person's address is written in the identity export and in seat assignments, when not canonical.
    identity_email: str = ""
    seat_email: str = ""


@dataclass
class Account:
    email: str
    display_name: str
    status: str
    created: datetime
    last_sign_in: datetime | None


@dataclass
class Company:
    people: list[Person] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    #: Seat holders who are not people on the roster: (vendor, email, assigned_on).
    loose_seats: list[tuple[str, str, date]] = field(default_factory=list)
    extra_invoice_seats: dict[str, int] = field(default_factory=dict)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(rng: random.Random, first: date, last: date) -> date:
    return first + timedelta(days=rng.randint(0, (last - first).days))


def _moment(rng: random.Random, first: datetime, last: datetime) -> datetime:
    return first + timedelta(seconds=rng.randint(0, int((last - first).total_seconds())))


class _Builder:
    def __init__(self, seed: int, plant: bool) -> None:
        self.rng = random.Random(seed)
        self.plant = plant
        self.company = Company()
        self.emails: set[str] = set()
        self.next_id = 1
        self.no_account: set[str] = set()
        self.leavers: list[Person] = []
        self.planted_last_sign_in: dict[str, datetime] = {}

    # --- people ---------------------------------------------------------------------------------------------------

    def reserve(self, email: str) -> None:
        self.emails.add(email)

    def new_email(self, given: str, family: str) -> str | None:
        for local in (f"{given[0]}.{family}", f"{given}.{family}"):
            email = f"{local.lower()}@{DOMAIN}"
            if email not in self.emails:
                self.emails.add(email)
                return email
        return None

    def random_name(self) -> tuple[str, str, str]:
        while True:
            given, family = self.rng.choice(GIVEN_NAMES), self.rng.choice(FAMILY_NAMES)
            email = self.new_email(given, family)
            if email is not None:
                return given, family, email

    def employee_id(self) -> str:
        value = f"E{self.next_id:04d}"
        self.next_id += 1
        return value

    def person(
        self,
        department: str,
        title: str,
        manager: str,
        location: str,
        start: date,
        given: str | None = None,
        family: str | None = None,
        email: str | None = None,
        employment_type: str = "employee",
        leaving: date | None = None,
        seats: tuple[str, ...] = (),
    ) -> Person:
        if given is None or family is None or email is None:
            given, family, email = self.random_name()
        else:
            self.reserve(email)
        p = Person(
            self.employee_id(),
            given,
            family,
            email,
            department,
            title,
            manager,
            employment_type,
            location,
            start,
            leaving,
            seats=list(seats),
        )
        if department == "IT":
            p.github_login = email.split("@")[0].replace(".", "-") + "-hp"
        self.company.people.append(p)
        return p

    def staff_start(self) -> date:
        return _day(self.rng, date(2012, 1, 9), date(2026, 10, 19))

    def location(self, dept: Department) -> str:
        return self.rng.choice(BRANCHES) if dept.branch_based else HEAD_OFFICE

    def build_people(self) -> None:
        chiefs: dict[str, Person] = {}
        for code, title in EXECUTIVES:
            manager = chiefs["CEO"].email if chiefs else ""
            chiefs[code] = self.person(
                "Executive",
                title,
                manager,
                HEAD_OFFICE,
                _day(self.rng, date(2010, 1, 4), date(2020, 12, 14)),
                seats=EXECUTIVE_SEATS,
            )

        # People who must exist on the run date: planted.yaml names two of them; Nadia Haddad holds n.haddad, which is
        # why the planted joiner's address is noor.haddad.
        forced: dict[str, list[Preset]] = {
            "Lending": [Preset("Nadia", "Haddad", f"n.haddad@{DOMAIN}", "Underwriter", date(2018, 5, 14))],
        }
        if self.plant:
            # planted.yaml: the Unprovisioned joiner (I) and the Wraith (IB). Neither has an account.
            forced["Member Services"] = [
                Preset(
                    "Noor",
                    "Haddad",
                    f"noor.haddad@{DOMAIN}",
                    "Member Advisor",
                    date(2026, 11, 2),
                    seats=(),
                    has_account=False,
                )
            ]
            forced["Finance"] = [
                Preset(
                    "Elena",
                    "Castell",
                    f"e.castell@{DOMAIN}",
                    "Accountant",
                    date(2022, 10, 3),
                    seats=(CRYPT,),
                    has_account=False,
                )
            ]

        self.heads: dict[str, Person] = {}
        for dept in DEPARTMENTS:
            head = self.person(
                dept.name,
                f"Head of {dept.name}",
                chiefs[dept.chief].email,
                HEAD_OFFICE,
                _day(self.rng, date(2011, 1, 3), date(2022, 6, 6)),
                seats=dept.seats,
            )
            self.heads[dept.name] = head
            lead_count = (dept.size - 1) // 12
            leads = [
                self.person(
                    dept.name,
                    "Team Lead",
                    head.email,
                    self.location(dept),
                    _day(self.rng, date(2012, 1, 9), date(2024, 3, 4)),
                    seats=dept.seats,
                )
                for _ in range(lead_count)
            ]
            managers = leads or [head]
            staff_count = dept.size - 1 - lead_count
            presets = forced.get(dept.name, [])
            for index in range(staff_count):
                manager = managers[index % len(managers)].email
                if index < len(presets):
                    pre = presets[index]
                    p = self.person(
                        dept.name,
                        pre.title,
                        manager,
                        self.location(dept),
                        pre.start,
                        given=pre.given,
                        family=pre.family,
                        email=pre.email,
                        seats=dept.seats if pre.seats is None else pre.seats,
                    )
                    if not pre.has_account:
                        self.no_account.add(p.email)
                    continue
                title = self.rng.choice(dept.titles)
                employment = "contractor" if dept.name == "IT" and index % 5 == 4 else "employee"
                p = self.person(
                    dept.name,
                    title,
                    manager,
                    self.location(dept),
                    self.staff_start(),
                    employment_type=employment,
                    seats=dept.seats,
                )
                if dept.name == "Branch Operations" and index >= staff_count - PART_TIME_TELLERS:
                    p.title = "Part-time Teller"
                    if self.plant:
                        p.seats = []  # Unlicensed user (IO): an account and no paid seat. Informational.

    def build_boundaries(self) -> None:
        """People whose dates sit on the edges of the run date and who must produce no finding."""
        current = [
            p
            for p in self.company.people
            if p.title not in ("Head of " + p.department, "Team Lead")
            and p.department != "Executive"
            and p.leaving is None
            and p.email not in self.no_account
            and p.seats
        ]
        for p, leaving in zip(self.rng.sample(current, 2), (date(2026, 11, 20), date(2026, 12, 31)), strict=True):
            p.leaving = leaving  # still here on the run date: Living
        for leaving in [date(2026, 11, 4)] + sorted(
            _day(self.rng, date(2026, 1, 9), date(2026, 10, 23)) for _ in range(6)
        ):
            dept = self.rng.choice(DEPARTMENTS)
            p = self.person(
                dept.name,
                self.rng.choice(dept.titles),
                self.heads[dept.name].email,
                self.location(dept),
                _day(self.rng, date(2014, 1, 6), date(2025, 6, 2)),
                leaving=leaving,
            )
            self.leavers.append(p)  # account disabled, no seats: correctly off-boarded
        dept = DEPARTMENTS[0]
        joiner = self.person(
            dept.name, "Member Advisor", self.heads[dept.name].email, self.location(dept), date(2026, 11, 16)
        )
        self.no_account.add(joiner.email)  # starts after the run date; not provisioned yet

    def build_planted_leavers(self) -> None:
        """planted.yaml: the three Ghosts (OB)."""
        heads = self.heads
        marsh = self.person(
            "Lending",
            "Loan Officer",
            heads["Lending"].email,
            BRANCHES[0],
            date(2021, 4, 12),
            given="Jonah",
            family="Marsh",
            email=f"j.marsh@{DOMAIN}",
            leaving=date(2026, 9, 12),
            seats=(CRYPT, BELFRY),
        )
        lindqvist = self.person(
            "IT",
            "Systems Engineer",
            heads["IT"].email,
            HEAD_OFFICE,
            date(2025, 9, 1),
            given="Petra",
            family="Lindqvist",
            email=f"p.lindqvist@{DOMAIN}",
            employment_type="contractor",
            leaving=date(2026, 6, 30),
            seats=(LANTERN,),
        )
        voss = self.person(
            "Marketing",
            "Designer",
            heads["Marketing"].email,
            HEAD_OFFICE,
            date(2023, 2, 6),
            given="Rowan",
            family="Voss",
            email=f"r.voss@{DOMAIN}",
            leaving=date(2026, 8, 1),
            seats=(OSSUARY,),
        )
        voss.identity_email = f"R.Voss+old@{ALIAS_DOMAIN}"
        self.planted_last_sign_in = {
            marsh.email: datetime(2026, 10, 30, 19, 42, tzinfo=UTC),
            lindqvist.email: datetime(2026, 10, 21, 8, 5, tzinfo=UTC),
            voss.email: datetime(2026, 7, 31, 16, 58, tzinfo=UTC),
        }

    def build_variants(self) -> None:
        """Living people whose address is written differently in one export; the normaliser must join them."""
        candidates = [
            p
            for p in self.company.people
            if p.leaving is None and p.email not in self.no_account and LANTERN in p.seats and not p.identity_email
        ]
        a, b, c, d, e = self.rng.sample(candidates, 5)

        def local(p: Person) -> str:
            return p.email.split("@")[0]

        a.identity_email = f"{local(a).title()}@HollowPines.com"
        b.identity_email = f"{local(b)}+sso@{DOMAIN}"
        c.identity_email = f"{local(c)}@{ALIAS_DOMAIN}"
        d.seat_email = f"{local(d)}@{ALIAS_DOMAIN}"
        e.seat_email = f"{local(e).upper()}+chat@{DOMAIN}"

    # --- accounts and seats ---------------------------------------------------------------------------------------

    def build_accounts(self) -> None:
        recent_first = datetime(2026, 10, 1, tzinfo=UTC)
        recent_last = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)
        for p in self.company.people:
            if p.email in self.no_account:
                continue
            created = datetime.combine(
                p.start - timedelta(days=self.rng.randint(1, 10)), datetime.min.time(), tzinfo=UTC
            ) + timedelta(hours=9)
            name = f"{p.given} {p.family}"
            if p.leaving is None or p.leaving > RUN_DATE:
                first = max(recent_first, created + timedelta(days=1))
                status, signed_in = "active", _moment(self.rng, first, recent_last)
            elif p.email in self.planted_last_sign_in:
                status, signed_in = "active", self.planted_last_sign_in[p.email]  # planted Ghost: never disabled
            else:
                status = "disabled"
                signed_in = datetime.combine(p.leaving, datetime.min.time(), tzinfo=UTC) - timedelta(
                    minutes=self.rng.randint(60, 600)
                )
            self.company.accounts.append(Account(p.identity_email or p.email, name, status, created, signed_in))
        if self.plant:
            # planted.yaml: the two Poltergeists (O). Never on the roster, no seat.
            self.company.accounts.append(
                Account(
                    f"svc-reporting@{DOMAIN}",
                    "Reporting service",
                    "active",
                    datetime(2024, 3, 18, 10, 20, tzinfo=UTC),
                    datetime(2026, 11, 3, 23, 15, tzinfo=UTC),
                )
            )
            self.company.accounts.append(
                Account(
                    f"test.admin@{DOMAIN}",
                    "Test Administrator",
                    "active",
                    datetime(2025, 5, 20, 14, 5, tzinfo=UTC),
                    datetime(2025, 6, 2, 11, 30, tzinfo=UTC),
                )
            )
            # planted.yaml: the Phantom seat (B), and the Lantern Chat seats paid for nobody named.
            self.company.loose_seats.append((BELFRY, f"temp.contractor@{DOMAIN}", date(2026, 7, 14)))
            self.company.extra_invoice_seats[LANTERN] = UNNAMED_LANTERN_SEATS

    def build(self) -> Company:
        self.build_people()
        if self.plant:
            self.build_planted_leavers()
        self.build_boundaries()
        self.build_variants()
        self.build_accounts()
        return self.company


# --- files --------------------------------------------------------------------------------------------------------


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def company_files(company: Company) -> dict[str, bytes]:
    """The company as export files, by path relative to the data folder."""
    files: dict[str, bytes] = {}
    files["hr_roster.csv"] = _csv(
        [
            "employee_id",
            "email",
            "given_name",
            "family_name",
            "department",
            "title",
            "manager_email",
            "employment_type",
            "location",
            "start_date",
            "leaving_date",
            "github_login",
        ],
        [
            [
                p.employee_id,
                p.email,
                p.given,
                p.family,
                p.department,
                p.title,
                p.manager_email,
                p.employment_type,
                p.location,
                p.start.isoformat(),
                p.leaving.isoformat() if p.leaving else "",
                p.github_login,
            ]
            for p in company.people
        ],
    )
    accounts = sorted(company.accounts, key=lambda a: (a.email.lower(), a.email))
    files["identity_export.csv"] = _csv(
        ["account_id", "email", "display_name", "status", "created", "last_sign_in"],
        [
            [
                f"u-{10000 + i}",
                a.email,
                a.display_name,
                a.status,
                _iso(a.created),
                _iso(a.last_sign_in) if a.last_sign_in else "",
            ]
            for i, a in enumerate(accounts, start=1)
        ],
    )
    for vendor in VENDORS:
        holders: list[tuple[str, date]] = [
            (p.seat_email or p.email, max(p.start, date(2019, 1, 7))) for p in company.people if vendor.name in p.seats
        ]
        holders += [(email, on) for name, email, on in company.loose_seats if name == vendor.name]
        files[f"licences/{vendor.slug}.csv"] = _csv(
            ["seat_id", "email", "assigned_on"],
            [[f"{vendor.prefix}-{n:04d}", email, on.isoformat()] for n, (email, on) in enumerate(holders, start=1)],
        )
        october = len(holders) + company.extra_invoice_seats.get(vendor.name, 0)
        september = october - sum(1 for _, on in holders if on >= date(2026, 10, 1))
        files[f"invoices/{vendor.slug}.csv"] = _csv(
            ["invoice_id", "vendor", "period", "seat_quantity", "unit_price", "currency"],
            [
                [
                    f"{vendor.prefix}-INV-{PREVIOUS_PERIOD}",
                    vendor.name,
                    PREVIOUS_PERIOD,
                    str(september),
                    vendor.unit_price,
                    "USD",
                ],
                [f"{vendor.prefix}-INV-{PERIOD}", vendor.name, PERIOD, str(october), vendor.unit_price, "USD"],
            ],
        )
    return files


def build_company(seed: int = DEFAULT_SEED, plant: bool = True) -> dict[str, bytes]:
    """Hollow Pines as ``{relative path: bytes}``. Pure: the same arguments give the same bytes."""
    return company_files(_Builder(seed, plant).build())


def write_company(out: Path, seed: int = DEFAULT_SEED, plant: bool = True) -> list[Path]:
    """Write the company into *out* and return the files written."""
    written: list[Path] = []
    for relative, data in sorted(build_company(seed, plant).items()):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ghosts.generate", description="Generate Hollow Pines.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"random seed (default {DEFAULT_SEED})")
    parser.add_argument("--out", type=Path, help=f"output folder (default {DEFAULT_OUT})")
    parser.add_argument("--healthy", action="store_true", help="no planted findings; needs --out")
    args = parser.parse_args(argv)
    if args.healthy and args.out is None:
        parser.error("--healthy needs --out, so the committed data is never replaced by the healthy company")
    out: Path = args.out or DEFAULT_OUT
    for path in write_company(out, args.seed, plant=not args.healthy):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

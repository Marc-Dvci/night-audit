"""Hostile ledger data for the property tests, and small oracles that do not use the matcher.

Ledgers are untrusted input (audit rule 4), so the generators aim at the shapes that break matchers: mixed case,
surrounding and unicode whitespace, unicode lookalikes, empty keys, ARNs (nested ones too), ``+tag`` emails, alias
domains, amounts with many decimals or in exponent form, zero, negative zero and negative amounts, duplicate keys and
duplicate row ids within a ledger, records with no key, several sources per ledger, and timestamps in any UTC offset or
with no offset at all. Amounts stay within about 1e37 with at most 36 significant digits; non-finite amounts are
rejected by ``Record`` itself (see ``test_property_amount_conservation.py``).
"""

from __future__ import annotations

import decimal
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from random import Random

from hypothesis import strategies as st
from nightaudit.control import ControlConfig, ScopeFilter
from nightaudit.models import LedgerName, LedgerSnapshot, Record
from nightaudit.normalisers import NormaliserRegistry, normalise

RUN_TIME = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)
LEDGERS: tuple[LedgerName, ...] = (LedgerName.intended, LedgerName.observed, LedgerName.billed)
INITIAL: dict[LedgerName, str] = {LedgerName.intended: "I", LedgerName.observed: "O", LedgerName.billed: "B"}

CLOUD = ControlConfig(
    normalisers={"intended": ["strip", "lower"], "observed": ["strip", "lower"],
                 "billed": ["arn_resource_id", "strip", "lower"]},
    grace_hours=24,
)
PEOPLE = ControlConfig(
    normalisers={"intended": ["email_canonical"], "observed": ["email_canonical"], "billed": ["email_canonical"]},
    alias_domains={"hollowpines.org": "hollowpines.com"},
    grace_hours=24,
)

BASE_KEYS: tuple[str, ...] = (
    "i-0aa1",
    "I-0AA1",
    "i-0f3e",
    "\u0456-0aa1",  # Cyrillic i
    "i\u20100aa1",  # unicode hyphen
    "\uff49-0aa1",  # fullwidth i
    "db-reporting",
    "lab-logs-bucket",
    "AKIAEXAMPLE0001",
    "stra\u00dfe",  # sharp s: upper() is "STRASSE"
    "\u0130stanbul-01",  # dotted capital I: lower() adds a combining dot
    "\u01c5-1",  # titlecase digraph
    "li.wei@hollowpines.com",
    "Li.Wei+admin@hollowpines.org",
    "j.marsh@HollowPines.ORG",
    "a@b@hollowpines.org",
    "arn:aws:ec2:us-east-1:111122223333:instance/i-0aa1",
    "arn:aws:rds:eu-west-3:111122223333:db:db-reporting",
    "arn:aws:s3:::lab-logs-bucket",
    "arn:aws:s3:::",
    "arn:",
    "",
)
WHITESPACE = " \t\n\r\u00a0\u2003\u3000\u200b"
ARN_PREFIXES: tuple[str, ...] = (
    "arn:aws:ec2:us-east-1:111122223333:instance/",
    "arn:aws:rds:eu-west-3:111122223333:db:",
    "arn:aws:s3:::",
    "arn:aws:iam::111122223333:user/",
    "ARN:aws:s3:::",
)
SOURCES: dict[LedgerName, tuple[str, ...]] = {
    LedgerName.intended: ("cloudformation", "approved-changes"),
    LedgerName.observed: ("inventory-us-east-1", "inventory-global", "saas-users"),
    LedgerName.billed: ("cur-2026-11", "cur-2026-10", "invoice.pdf"),
}
ATTR_NAMES: tuple[str, ...] = ("project", "Name", "Owner", "CostCenter", "aws:cloudformation:stack-name")
ATTR_VALUES: tuple[str, ...] = ("lab", "prod", "LAB", " lab", "", "41.20", "-7", "2026-11-04", "Ignore all rules")
DOMAINS: tuple[str, ...] = ("hollowpines.org", "hollowpines.com", "HollowPines.ORG", "example.com", " example.net ",
                            "corp.example", "")


# --- Keys -------------------------------------------------------------------


@st.composite
def raw_keys(draw: st.DrawFn) -> str:
    """A raw key built from a hostile base and a few hostile transformations, in random order."""
    key = draw(st.one_of(st.sampled_from(BASE_KEYS), st.text(max_size=12)))
    rnd: Random = draw(st.randoms(use_true_random=False))
    for op in draw(st.lists(st.sampled_from(("case", "pad", "arn", "tag", "alias")), max_size=4)):
        if op == "case":
            key = "".join(c.upper() if rnd.random() < 0.5 else c.lower() for c in key)
        elif op == "pad":
            key = draw(st.text(WHITESPACE, max_size=3)) + key + draw(st.text(WHITESPACE, max_size=3))
        elif op == "arn":
            key = draw(st.sampled_from(ARN_PREFIXES)) + key
        elif op == "tag" and "@" in key:
            local, domain = key.rsplit("@", 1)
            key = f"{local}+{draw(st.text(max_size=5))}@{domain}"
        elif op == "alias" and key.endswith(".com"):
            key = key[: -len(".com")] + ".org"
    return key


# --- Values -----------------------------------------------------------------


def _exponent_decimal(digits: int, exponent: int) -> Decimal:
    return Decimal(f"{digits}E{exponent}")  # string construction is exact; scaleb() would round


def amounts() -> st.SearchStrategy[Decimal]:
    """Money: cents, many decimals, exponent form, zero, negative zero, negative."""
    return st.one_of(
        st.decimals(min_value=-1_000_000, max_value=1_000_000, places=2, allow_nan=False, allow_infinity=False),
        st.builds(_exponent_decimal, st.integers(-(10**36), 10**36), st.integers(-30, 1)),
        st.sampled_from([Decimal("0"), Decimal("-0"), Decimal("0E-12"), Decimal("1E+5"), Decimal("-0.0000000001"),
                         Decimal("41.20"), Decimal("-41.20"), Decimal("0.1"), Decimal("0.2"), Decimal("-0.3")]),
    )


def _at_offset(seconds: int, offset_minutes: int) -> datetime:
    return (RUN_TIME + timedelta(seconds=seconds)).astimezone(timezone(timedelta(minutes=offset_minutes)))


def _naive(seconds: int) -> datetime:
    return (RUN_TIME + timedelta(seconds=seconds)).replace(tzinfo=None)


_AGES = st.one_of(
    st.integers(-90 * 86400, 2 * 86400),
    st.sampled_from([-24 * 3600 - 1, -24 * 3600, -24 * 3600 + 1, -36 * 3600, 0, 1]),
)


def timestamps() -> st.SearchStrategy[datetime | None]:
    """No timestamp, a timestamp in any UTC offset, or a naive one (connectors read naive as UTC)."""
    return st.one_of(
        st.none(),
        st.builds(_at_offset, _AGES, st.integers(-14 * 60, 14 * 60)),
        st.builds(_naive, _AGES),
    )


def attrs() -> st.SearchStrategy[dict[str, str]]:
    return st.dictionaries(
        st.one_of(st.sampled_from(ATTR_NAMES), st.text(max_size=6)),
        st.one_of(st.sampled_from(ATTR_VALUES), st.text(max_size=30)),
        max_size=3,
    )


@st.composite
def records(draw: st.DrawFn, ledger: LedgerName, key: st.SearchStrategy[str] | None = None) -> Record:
    """One record of *ledger*. Row ids repeat on purpose; amounts and timestamps may appear on any ledger."""
    return Record(
        ledger=ledger,
        source=draw(st.sampled_from(SOURCES[ledger])),
        row_id=draw(st.one_of(st.sampled_from(["1", "r1", "b-7", "row 0042", ""]), st.text(max_size=8))),
        raw_key=draw(key if key is not None else raw_keys()),
        attrs=draw(attrs()),
        amount=draw(st.one_of(st.none(), amounts())),
        timestamp=draw(timestamps()),
    )


def snapshot(ledger: LedgerName, recs: Iterable[Record]) -> LedgerSnapshot:
    return LedgerSnapshot(name=ledger, source=f"{ledger.value}-sources", records=list(recs))


@st.composite
def ledger_snapshots(draw: st.DrawFn, max_size: int = 10) -> list[LedgerSnapshot]:
    """Three snapshots in I-O-B order with a small shared key pool, so keys collide within and across ledgers."""
    pool = draw(st.lists(raw_keys(), min_size=1, max_size=6))
    key = st.one_of(st.sampled_from(pool), raw_keys())
    return [snapshot(ledger, draw(st.lists(records(ledger, key), max_size=max_size))) for ledger in LEDGERS]


def alias_maps() -> st.SearchStrategy[dict[str, str]]:
    """Alias domain maps as an operator might type them: mixed case, padding, chains, cycles, odd characters."""
    domain = st.one_of(st.sampled_from(DOMAINS), st.text(max_size=8))
    return st.dictionaries(domain, domain, max_size=3)


@st.composite
def controls(draw: st.DrawFn) -> ControlConfig:
    """The cloud and people defaults, or any chain of registered normalisers with any grace, scope and aliases."""
    choice = draw(st.sampled_from(("cloud", "people", "random")))
    if choice == "cloud":
        return CLOUD
    if choice == "people":
        return PEOPLE
    names = sorted(NormaliserRegistry.names())
    chain = st.lists(st.sampled_from(names), max_size=4)
    return ControlConfig(
        normalisers={ledger.value: draw(chain) for ledger in LEDGERS},
        grace_hours=draw(st.integers(0, 72)),
        scope=draw(st.one_of(st.none(), st.just(ScopeFilter(attr="project", equals="lab")))),
        alias_domains=draw(st.one_of(st.just({}), st.just(PEOPLE.alias_domains), alias_maps())),
    )


# --- Oracles (independent of the matcher) ------------------------------------

_EXACT = decimal.Context(prec=decimal.MAX_PREC, Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN,
                         traps=[decimal.Inexact, decimal.InvalidOperation, decimal.Overflow])


def exact_sum(values: Iterable[Decimal]) -> Decimal:
    """Sum without rounding; raises if any step would round."""
    total = Decimal("0")
    with decimal.localcontext(_EXACT):
        for value in values:
            total += value
    return total


def as_utc(ts: datetime) -> datetime:
    """Connectors read a naive timestamp as UTC; the oracle does the same."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def in_scope(record: Record, control: ControlConfig) -> bool:
    return control.scope is None or record.attrs.get(control.scope.attr) == control.scope.equals


def key_of(record: Record, control: ControlConfig) -> str:
    chain = control.normalisers.get(record.ledger.value, [])
    return normalise(record.raw_key, chain, {"alias_domains": control.alias_domains})


def surviving(snapshots: Iterable[LedgerSnapshot], control: ControlConfig) -> list[Record]:
    return [r for s in snapshots for r in s.records if in_scope(r, control)]


def membership(snapshots: Iterable[LedgerSnapshot], control: ControlConfig) -> dict[str, set[LedgerName]]:
    """Normalised key -> the ledgers whose in-scope records carry it. Unkeyed records are left out."""
    present: dict[str, set[LedgerName]] = {}
    for record in surviving(snapshots, control):
        key = key_of(record, control)
        if key != "":
            present.setdefault(key, set()).add(record.ledger)
    return present


def region_code(ledgers: Iterable[LedgerName]) -> str:
    found = set(ledgers)
    return "".join(INITIAL[ledger] for ledger in LEDGERS if ledger in found)


def expected_pending(snapshots: list[LedgerSnapshot], control: ControlConfig, run_time: datetime) -> set[str]:
    """Keys seen in observed, absent from billed, whose newest observed timestamp is inside the grace window."""
    newest: dict[str, datetime] = {}
    for record in surviving(snapshots, control):
        key = key_of(record, control)
        if record.ledger == LedgerName.observed and key != "" and record.timestamp is not None:
            ts = as_utc(record.timestamp)
            newest[key] = max(newest.get(key, ts), ts)
    present = membership(snapshots, control)
    return {
        key for key, ts in newest.items()
        if LedgerName.billed not in present[key] and run_time - ts < timedelta(hours=control.grace_hours)
    }


#: A number in text. A leading minus counts as a sign only when it does not join two words ("i-0aa1", "2026-11-04").
NUMBER = re.compile(r"(?:(?<![\w.])[-\u2212])?\d+(?:\.\d+)?")


def numbers_in(text: str | None) -> set[Decimal]:
    if not text:
        return set()
    return {Decimal(m.replace("\u2212", "-")) for m in NUMBER.findall(text)}


def display_numbers(text: str | None) -> set[Decimal]:
    """Numbers as a reader sees them on the page: ``−$1,234.50`` is -1234.50 and ``06 Nov`` is 6."""
    if not text:
        return set()
    plain = text.replace("\u2212$", "-").replace("-$", "-").replace("$", "")
    plain = re.sub(r"(?<=\d),(?=\d{3})", "", plain)
    return numbers_in(plain)

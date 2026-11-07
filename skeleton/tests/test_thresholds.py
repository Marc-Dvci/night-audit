"""The decision core at and around each of its thresholds: below, at and above, and the healthy case that gives nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from nightaudit.control import ControlConfig, ControlFile, ScopeFilter
from nightaudit.grace import find_pending
from nightaudit.matcher import match
from nightaudit.models import Finding, LedgerName, LedgerSnapshot, Record
from nightaudit.normalisers import NormaliserRegistry, UnknownNormaliserError
from nightaudit.scope import apply_scope
from nightaudit.state import FindingState, compare_findings

RUN = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)


def _observed(key: str, ts: datetime | None) -> Record:
    return Record(ledger=LedgerName.observed, source="o", row_id=key, raw_key=key, key=key, timestamp=ts)


@pytest.mark.parametrize(
    ("age", "pending"),
    [
        (timedelta(hours=23, minutes=59, seconds=59), True),
        (timedelta(hours=24), False),  # the window is open at its far end: exactly 24 hours old is a finding
        (timedelta(hours=24, seconds=1), False),
        (timedelta(0), True),
        (-timedelta(hours=1), True),  # a clock ahead of the run is still young
    ],
    ids=["below", "at", "above", "now", "future"],
)
def test_an_unbilled_observed_key_is_pending_only_while_younger_than_the_grace_window(
    age: timedelta, pending: bool
) -> None:
    record = _observed("k", RUN - age)
    assert (find_pending({"k"}, set(), {"k": [record]}, 24, RUN) == {"k"}) is pending


def test_a_billed_key_is_never_pending_however_young() -> None:
    assert find_pending({"k"}, {"k"}, {"k": [_observed("k", RUN)]}, 24, RUN) == set()


def test_a_key_with_no_timestamp_is_never_pending() -> None:
    assert find_pending({"k"}, set(), {"k": [_observed("k", None)]}, 24, RUN) == set()


def test_the_newest_observed_timestamp_of_a_key_decides() -> None:
    records = [_observed("k", RUN - timedelta(days=30)), _observed("k", RUN - timedelta(hours=1))]
    assert find_pending({"k"}, set(), {"k": records}, 24, RUN) == {"k"}


@pytest.mark.parametrize(("grace", "pending"), [(0, False), (1, True)])
def test_a_zero_hour_window_makes_nothing_pending(grace: int, pending: bool) -> None:
    record = _observed("k", RUN - timedelta(minutes=30))
    assert (find_pending({"k"}, set(), {"k": [record]}, grace, RUN) == {"k"}) is pending


def test_a_pending_key_is_reported_as_pending_and_is_not_a_finding() -> None:
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i", records=[]),
        LedgerSnapshot(name=LedgerName.observed, source="o", records=[_observed("new", RUN - timedelta(hours=2))]),
        LedgerSnapshot(name=LedgerName.billed, source="b", records=[]),
    ]
    result = match(snapshots, ControlConfig(grace_hours=24), RUN)
    assert (result.pending_keys, result.findings) == (["new"], [])


def _finding(key: str, code: str = "OB") -> Finding:
    return Finding(key=key, region_code=code, name="Vampire", severity="high", meaning="m", informational=False)


@pytest.mark.parametrize(
    ("first_seen", "nights"),
    [
        (datetime(2026, 11, 3, 23, 59, tzinfo=UTC), 1),  # one midnight between, though only minutes apart
        (datetime(2026, 11, 4, 0, 0, tzinfo=UTC), 0),  # the same UTC date
        (datetime(2026, 11, 1, 2, 0, tzinfo=UTC), 3),
        (datetime(2026, 11, 4, 0, 30, tzinfo=timezone(timedelta(hours=1))), 1),  # 3 Nov 23:30 in UTC
    ],
    ids=["just-before-midnight", "same-date", "three-nights", "offset-across-midnight"],
)
def test_a_persisting_finding_counts_the_utc_midnights_since_it_was_first_seen(
    first_seen: datetime, nights: int
) -> None:
    previous = {"k:OB": FindingState(first_seen=first_seen, region_code="OB")}
    updated, resolved, state = compare_findings([_finding("k")], previous, RUN, ControlConfig())
    assert (updated[0].status, updated[0].nights_persisted, resolved) == ("persisting", nights, [])
    assert state["k:OB"].first_seen == first_seen


def test_a_key_that_changes_region_is_new_in_its_new_region_and_resolved_in_its_old_one() -> None:
    previous = {"k:OB": FindingState(first_seen=RUN - timedelta(days=2), region_code="OB")}
    updated, resolved, state = compare_findings([_finding("k", "B")], previous, RUN, ControlConfig())
    assert (updated[0].status, updated[0].nights_persisted) == ("new", 0)
    assert [(f.key, f.region_code, f.status, f.nights_persisted) for f in resolved] == [("k", "OB", "resolved", 2)]
    assert sorted(state) == ["k:B"]


def test_a_resolved_key_that_holds_colons_keeps_its_whole_key() -> None:
    arn = "arn:aws:iam::111122223333:user/old"
    previous = {f"{arn}:O": FindingState(first_seen=RUN - timedelta(days=1), region_code="O")}
    _, resolved, _ = compare_findings([], previous, RUN, ControlConfig())
    assert [(f.key, f.region_code) for f in resolved] == [(arn, "O")]


def test_a_healthy_night_after_a_healthy_night_has_no_state() -> None:
    assert compare_findings([], {}, RUN, ControlConfig()) == ([], [], {})


def _snapshot(name: LedgerName, attrs: list[dict[str, str]], missing: bool = False) -> LedgerSnapshot:
    records = [Record(ledger=name, source="s", row_id=str(n), raw_key=f"k{n}", attrs=a) for n, a in enumerate(attrs)]
    return LedgerSnapshot(name=name, source="s", records=[] if missing else records, missing=missing)


@pytest.mark.parametrize(
    ("attrs", "kept"),
    [
        ({"env": "prod"}, 1),
        ({"env": "Prod"}, 0),  # compared exactly
        ({"env": "prod "}, 0),
        ({}, 0),  # no attribute: out of scope
        ({"other": "prod"}, 0),
    ],
)
def test_a_record_is_in_scope_only_when_its_attribute_equals_the_value(attrs: dict[str, str], kept: int) -> None:
    filtered, dropped = apply_scope([_snapshot(LedgerName.observed, [attrs])], ScopeFilter(attr="env", equals="prod"))
    assert (len(filtered[0].records), dropped, filtered[0].dropped) == (kept, {"observed": 1 - kept}, 1 - kept)


def test_no_scope_keeps_every_record_and_drops_none() -> None:
    snapshots = [_snapshot(LedgerName.observed, [{}, {"env": "dev"}])]
    assert apply_scope(snapshots, None) == (snapshots, {"observed": 0})


def test_a_missing_ledger_passes_through_the_scope_untouched() -> None:
    missing = _snapshot(LedgerName.billed, [], missing=True)
    filtered, dropped = apply_scope([missing], ScopeFilter(attr="env", equals="prod"))
    assert (filtered, dropped) == ([missing], {"billed": 0})


def _ledgers(*names: str, normaliser: str = "strip") -> dict[str, object]:
    return {"ledgers": {n: {"key_field": "id", "normalisers": [normaliser]} for n in names}}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_ledgers("intended", "observed"), "missing ledgers: billed"),
        (_ledgers("intended", "observed", "billed", "paid"), "extra ledgers: paid"),
        (_ledgers("intended", "observed", "paid"), "missing ledgers: billed; extra ledgers: paid"),
    ],
)
def test_a_control_must_declare_exactly_the_three_ledgers(raw: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ControlFile.model_validate(raw).validate_ledgers()


def test_a_control_with_exactly_the_three_ledgers_is_accepted() -> None:
    ControlFile.model_validate(_ledgers("intended", "observed", "billed")).validate_ledgers()


def test_an_unknown_normaliser_is_named_with_its_ledger() -> None:
    control = ControlFile.model_validate(_ledgers("intended", "observed", "billed", normaliser="shout"))
    with pytest.raises(ValueError, match="Unknown normaliser 'shout' in ledger 'intended'"):
        control.validate_normalisers()


def test_the_registry_refuses_a_name_it_does_not_hold() -> None:
    with pytest.raises(UnknownNormaliserError):
        NormaliserRegistry.get("shout")
    assert {"strip", "lower", "arn_resource_id"} <= NormaliserRegistry.names()

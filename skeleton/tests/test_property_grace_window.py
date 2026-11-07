"""P6: a young, unbilled observed key is pending, not a finding (Req 4.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hostile import RUN_TIME, controls, key_of, ledger_snapshots, membership, raw_keys, records, region_code
from hypothesis import assume, given
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record


@st.composite
def grace_case(draw: st.DrawFn, young: bool) -> tuple[ControlConfig, list[LedgerSnapshot], str]:
    """Hostile ledgers plus one target key with no surviving billed record and 1-3 in-scope observed records.

    When *young*, the newest observed timestamp is inside the grace window (possibly in the future); otherwise every
    timestamped observed record for the key is at least ``grace_hours`` old.
    """
    control = draw(controls())
    snapshots = draw(ledger_snapshots())
    raw = draw(raw_keys())
    target = key_of(Record(ledger=LedgerName.observed, source="s", row_id="t", raw_key=raw), control)
    assume(target != "")
    grace = timedelta(hours=control.grace_hours)

    def age(young_record: bool) -> datetime:
        seconds = int(grace.total_seconds())
        if young_record:
            delta = draw(st.integers(-86400, seconds - 1)) if seconds > 0 else draw(st.integers(-86400, -1))
        else:
            delta = draw(st.integers(seconds, seconds + 90 * 86400))
        offset = timezone(timedelta(minutes=draw(st.integers(-14 * 60, 14 * 60))))
        return (RUN_TIME - timedelta(seconds=delta)).astimezone(offset)

    def in_scope(record: Record) -> Record:
        if control.scope is None:
            return record
        return record.model_copy(update={"attrs": {**record.attrs, control.scope.attr: control.scope.equals}})

    targets = [in_scope(draw(records(LedgerName.observed, st.just(raw)))).model_copy(update={"timestamp": age(young)})]
    for _ in range(draw(st.integers(0, 2))):
        extra = in_scope(draw(records(LedgerName.observed, st.just(raw))))
        stamp = draw(st.one_of(st.none(), st.just(age(False)))) if not young else extra.timestamp
        targets.append(extra.model_copy(update={"timestamp": stamp}))

    rebuilt: list[LedgerSnapshot] = []
    for s in snapshots:
        recs = list(s.records)
        if s.name == LedgerName.billed:
            # Only out-of-scope billed lines may carry the target key: those never count as "billed".
            recs = [
                r
                for r in recs
                if key_of(r, control) != target
                or (control.scope is not None and r.attrs.get(control.scope.attr) != control.scope.equals)
            ]
        if s.name == LedgerName.observed:
            if young:
                recs = recs + targets
            else:
                recs = [r for r in recs if key_of(r, control) != target] + targets
        rebuilt.append(s.model_copy(update={"records": recs}))
    return control, rebuilt, target


@pytest.mark.property
@given(case=grace_case(young=True))
def test_property_a_young_unbilled_observed_key_is_pending_and_produces_no_finding(
    case: tuple[ControlConfig, list[LedgerSnapshot], str],
) -> None:
    """P6 (Req 4.1): "For any observed record whose age is less than the grace window and whose key does not appear in
    the billed ledger, the key is reported in ``pending_keys`` and no finding is produced for it."
    """
    control, snapshots, target = case
    result = match(snapshots, control, RUN_TIME)
    assert target in result.pending_keys
    assert target not in result.regions
    assert all(f.key != target for f in result.findings)


@pytest.mark.property
@given(case=grace_case(young=False))
def test_property_an_unbilled_observed_key_older_than_the_grace_window_gets_its_normal_region(
    case: tuple[ControlConfig, list[LedgerSnapshot], str],
) -> None:
    """P6, other side (Req 4.1, design §7): "When the observed record ages past the grace window, the key gets its
    normal region": ``IO`` (Familiar) when also intended, ``O`` (Poltergeist) otherwise.
    """
    control, snapshots, target = case
    result = match(snapshots, control, RUN_TIME)
    assert target not in result.pending_keys
    assert result.regions[target] == region_code(membership(snapshots, control)[target])
    assert result.regions[target] in {"IO", "O"}
    assert [f.region_code for f in result.findings if f.key == target] == [result.regions[target]]
